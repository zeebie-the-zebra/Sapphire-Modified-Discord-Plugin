"""Message batching: accumulate channel messages before emitting daemon events."""

import asyncio
import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from plugins.leona_discord.lib import state
from plugins.leona_discord.lib.context_cache import (
    clear_pending_payload,
    set_pending_payload,
    set_reply_context,
)
from plugins.leona_discord.lib.history import (
    build_mention_map,
    format_recent_history,
    recent_message_ids,
    store_mention_map,
)
from plugins.leona_discord.lib.core_compat import ensure_execution_context_images_support
from plugins.leona_discord.lib.images import (
    blocks_to_event_images,
    describe_image,
    fetch_image_blocks,
    format_vision_description,
    image_unavailable_hint,
    is_vision_description_block,
    _attachment_kind,
)
from plugins.leona_discord.lib import memory
from plugins.leona_discord.lib.engagement import reply_length_hint
from plugins.leona_discord.lib.edit_history import build_edit_awareness_hint, build_message_edit_hint
from plugins.leona_discord.lib.reactions import build_reaction_hint
from plugins.leona_discord.lib.settings import get_batch_delay, get_effective_settings, get_image_settings
from plugins.leona_discord.lib.typing_indicator import fire_typing

logger = logging.getLogger(__name__)

# Occasional long "thinking" pause before replying (organic messages only)
DELAYED_REPLY_CHANCE = 0.075   # ~7.5% (midpoint of 5–10%)
DELAYED_REPLY_MIN_SECS = 30.0
DELAYED_REPLY_MAX_SECS = 60.0
BATCH_DELAY_JITTER = 3.0         # ± seconds on every batch wait
POST_TYPING_READ_MIN = 0.8       # pause after user stops typing
POST_TYPING_READ_MAX = 2.5


@dataclass
class MessageBatch:
    account: str
    guild_id: str
    guild_name: str
    channel_id: str
    channel_name: str
    is_dm: bool
    messages: list = field(default_factory=list)
    timer: Optional[threading.Timer] = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    had_typing: bool = False


def queue_message(batch: MessageBatch, msg_data: dict):
    channel_key = state.channel_key(batch.account, batch.channel_id)
    with batch.lock:
        batch.messages.append(msg_data)
        # Use shorter delay for direct questions / @mentions
        content = msg_data.get("content", "")
        _start_batch_timer(batch, delay_override=get_quick_delay(content))
    logger.info(
        f"[DISCORD] Queued message in #{batch.channel_name} "
        f"(batch size: {len(batch.messages)})"
    )


def get_or_create_batch(account_name: str, message) -> MessageBatch:
    channel_id_str = str(message.channel.id)
    channel_key = state.channel_key(account_name, channel_id_str)
    with state._batches_lock:
        if channel_key not in state._batches:
            state._batches[channel_key] = MessageBatch(
                account=account_name,
                guild_id=str(message.guild.id) if message.guild else "",
                guild_name=message.guild.name if message.guild else "DM",
                channel_id=channel_id_str,
                channel_name=getattr(message.channel, "name", "DM"),
                is_dm=message.guild is None,
            )
        return state._batches[channel_key]


def flush_all_pending():
    with state._batches_lock:
        batches = list(state._batches.items())
    for _, batch in batches:
        if batch.timer:
            batch.timer.cancel()
        with batch.lock:
            if batch.messages:
                try:
                    flush_batch(batch)
                except Exception:
                    pass
    with state._batches_lock:
        state._batches.clear()


def apply_batch_delay_jitter(delay: float) -> float:
    """Add per-message jitter so batch waits aren't perfectly uniform."""
    jittered = delay + random.uniform(-BATCH_DELAY_JITTER, BATCH_DELAY_JITTER)
    return max(1.0, jittered)


def _on_batch_timer(batch: MessageBatch):
    """Flush after an optional post-typing read pause."""
    if batch.had_typing:
        pause = random.uniform(POST_TYPING_READ_MIN, POST_TYPING_READ_MAX)
        logger.debug(
            f"[DISCORD] Post-typing read pause {pause:.1f}s in #{batch.channel_name}"
        )
        time.sleep(pause)
        batch.had_typing = False
    flush_batch(batch)


def _start_batch_timer(batch: MessageBatch, delay_override: float = None):
    if batch.timer is not None:
        batch.timer.cancel()
    delay = delay_override if delay_override is not None else get_batch_delay()
    delay = apply_batch_delay_jitter(delay)
    batch.timer = threading.Timer(delay, _on_batch_timer, args=(batch,))
    batch.timer.daemon = True
    batch.timer.start()
    fire_typing(batch.account, int(batch.channel_id))


def extend_batch_timer(account_name: str, channel_id: str):
    """Extend the batch window while the trigger author is still typing.

    Called from on_typing events — keeps the batch open so we collect
    the user's full message before flushing.
    """
    channel_key = state.channel_key(account_name, str(channel_id))
    with state._batches_lock:
        batch = state._batches.get(channel_key)
    if not batch or not batch.messages:
        return
    batch.had_typing = True
    # Reset the timer — give the user more time to finish typing
    _start_batch_timer(batch)
    logger.debug(f"[DISCORD] Batch timer extended for {channel_key}")


def get_quick_delay(content: str) -> float:
    """Return batch delay for a message, with urgency and occasional long pauses.

    Direct questions (? ending) and @mentions get a faster response.
    Organic messages sometimes get a 30–60s "thinking" bump.
    """
    if not content:
        return get_batch_delay()
    stripped = content.strip()
    # Direct question — respond quickly
    if stripped.endswith("?") or stripped.endswith("！"):
        return max(2.0, get_batch_delay() * 0.4)
    # Contains @ mention of the bot — respond quickly
    if "@" in stripped:
        return max(2.0, get_batch_delay() * 0.5)
    delay = get_batch_delay()
    if random.random() < DELAYED_REPLY_CHANCE:
        extra = random.uniform(DELAYED_REPLY_MIN_SECS, DELAYED_REPLY_MAX_SECS)
        delay += extra
        logger.debug(
            f"[DISCORD] Delayed reply mode — added {extra:.0f}s thinking pause "
            f"(total {delay:.0f}s)"
        )
    return delay


def flush_batch(batch: MessageBatch):
    if batch.timer is not None:
        batch.timer.cancel()
        batch.timer = None

    with batch.lock:
        if not batch.messages:
            return
        messages_to_send = list(batch.messages)
        batch.messages.clear()

    if not messages_to_send:
        return

    channel_key = state.channel_key(batch.account, batch.channel_id)
    last = messages_to_send[-1]

    image_description = ""
    image_urls = last.get("image_urls", [])
    image_enabled = get_image_settings(batch.guild_id).get("image_enabled", False)
    event_images = []  # core daemon payload: [{"data", "media_type"}, ...]

    if image_urls and image_enabled:
        image_url = image_urls[0]
        if state._loop and state._loop.is_running():
            try:
                future = asyncio.run_coroutine_threadsafe(
                    describe_image(image_url, batch.guild_id),
                    state._loop,
                )
                image_description = future.result(timeout=30)
            except Exception as e:
                logger.warning(f"[DISCORD] Image description error: {e}")
        if image_description:
            image_description = format_vision_description(image_description, image_urls)
        else:
            logger.warning(
                f"[DISCORD] Image description returned empty; using unavailable hint for {image_url}"
            )

    if image_urls and not image_enabled:
        # Native-vision path: download images and prepare multimodal blocks
        # so the main model can see the pixels directly.
        for url in image_urls:
            if state._loop and state._loop.is_running():
                try:
                    future = asyncio.run_coroutine_threadsafe(
                        fetch_image_blocks(url),
                        state._loop,
                    )
                    blocks = future.result(timeout=20)
                    event_images.extend(blocks_to_event_images(blocks))
                except Exception as e:
                    logger.warning(f"[DISCORD] Fetch image blocks error: {e}")

    if image_urls and not image_description and not event_images:
        image_description = image_unavailable_hint(image_urls)

    combined_content = "\n".join(m["content"] for m in messages_to_send)
    has_user_text = bool(combined_content.strip())
    image_described = is_vision_description_block(image_description)
    if image_description:
        combined_content = image_description + combined_content
    if image_urls and not has_user_text:
        if image_described:
            kind = _attachment_kind(image_urls)
            combined_content += (
                f"[The user sent this {kind} with no caption. Respond to the vision "
                f"description above — that is what the {kind} shows.]\n"
            )
    if image_urls and has_user_text and image_described:
        combined_content += (
            "[The user also attached media; the vision description above is what "
            "it shows — treat that as having seen their GIF/image.]\n"
        )

    if image_urls and not has_user_text and not image_described:
        combined_content += (
            "[The user sent this image/GIF with no text. "
            "You cannot see it — do not guess; ask them to describe it.]\n"
        )

    append_settings = get_effective_settings(
        batch.guild_id, channel_id=str(batch.channel_id), channel_name=batch.channel_name,
        channel_key=state.channel_key(batch.account, str(batch.channel_id)),
    )
    if append_settings.get("append_to_user_message_enabled") and append_settings.get("append_to_user_message"):
        append_text = append_settings["append_to_user_message"].strip()
        if append_text:
            combined_content = combined_content + "\n" + append_text

    # --- Style hint: channel vibe guidance for the LLM ---
    from plugins.leona_discord.lib.style_hint import build_style_hint
    style_hint = build_style_hint(
        batch.guild_name, batch.channel_name,
        batch_size=len(messages_to_send),
        is_dm=batch.is_dm,
    )
    length_hint = reply_length_hint(channel_key)
    if length_hint:
        style_hint = f"{style_hint}\n{length_hint}" if style_hint else length_hint
    edit_hint = build_edit_awareness_hint(channel_key)
    if edit_hint:
        style_hint = f"{style_hint}\n\n{edit_hint}" if style_hint else edit_hint
    if style_hint:
        combined_content = combined_content + "\n\n" + style_hint

    effective = get_effective_settings(
        batch.guild_id, channel_id=str(batch.channel_id), channel_name=batch.channel_name,
        channel_key=state.channel_key(batch.account, str(batch.channel_id)),
    )
    reaction_hint = build_reaction_hint(effective)
    from plugins.leona_discord.lib.gifs import build_gif_hint
    gif_hint = build_gif_hint(batch.guild_id)

    from plugins.leona_discord.lib.history import get_history_snapshot
    full_history = get_history_snapshot(channel_key)
    skip_ids = recent_message_ids(full_history, batch.guild_id)

    memory_context = memory.recall_context(
        batch.account,
        batch.guild_id,
        batch.channel_id,
        combined_content,
        batch.guild_name,
        batch.channel_name,
        exclude_message_ids=skip_ids,
    )
    if memory_context:
        combined_content = f"{memory_context}\n\n{combined_content}"

    if reaction_hint:
        combined_content = f"{combined_content}\n\n{reaction_hint}"

    if gif_hint:
        combined_content = f"{combined_content}\n\n{gif_hint}"

    edit_hint = build_message_edit_hint(effective.get("message_edits_enabled", True))
    if edit_hint:
        combined_content = f"{combined_content}\n\n{edit_hint}"

    recent_history = format_recent_history(full_history, batch.guild_id)
    mention_map = build_mention_map(full_history, messages_to_send)
    store_mention_map(channel_key, mention_map)

    trigger_content = "\n".join(m["content"] for m in messages_to_send)

    payload = {
        "account": batch.account,
        "guild_id": batch.guild_id,
        "guild_name": batch.guild_name,
        "channel_id": batch.channel_id,
        "channel_name": batch.channel_name,
        "message_id": last["message_id"],
        "content": combined_content,
        "trigger_content": trigger_content,
        "username": last["username"],
        "display_name": last["display_name"],
        "author_id": last["author_id"],
        "is_dm": batch.is_dm,
        "mentioned": last.get("mentioned", "False"),
        "recent_history": recent_history,
        "batch_size": len(messages_to_send),
        "history_size": len(full_history),
        "mention_map": mention_map,
        "memory_context": bool(memory_context),
        "image_urls": image_urls,
        "image_described": image_described,
        "images": event_images,
        "reply_to_message_id": last["message_id"],
    }

    from plugins.leona_discord.lib.bot_identity import enrich_payload_with_bot_identity
    enrich_payload_with_bot_identity(payload)

    logger.info(
        f"[DISCORD] Emitting batch of {len(messages_to_send)} messages "
        f"(history: {len(full_history)}) from {last.get('username')} in #{batch.channel_name}"
    )

    fire_typing(batch.account, int(batch.channel_id))

    if event_images:
        ensure_execution_context_images_support()
        logger.info(f"[DISCORD] Attaching {len(event_images)} image(s) to daemon event payload")

    set_reply_context(channel_key, batch.guild_id, batch.channel_id, last["message_id"])
    set_pending_payload(channel_key, payload)

    loader = state.get_plugin_loader()
    try:
        if loader:
            accepted = loader.emit_daemon_event("discord_message", json.dumps(payload))
        else:
            accepted = False
    except Exception as e:
        logger.error(f"[DISCORD] Emit failed for #{batch.channel_name}: {e}")
        accepted = False

    if not accepted:
        logger.info(
            f"[DISCORD] No task accepted batch in #{batch.channel_name} — "
            f"restoring messages for retry"
        )
        with batch.lock:
            batch.messages = messages_to_send + batch.messages
        clear_pending_payload(channel_key)
