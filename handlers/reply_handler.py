"""Route LLM responses back to Discord channels."""

import asyncio
import logging
import random
import re

from plugins.leona_discord.lib.context_cache import clear_pending_payload, mark_reacted
from plugins.leona_discord.lib.history import append_bot_reply
from plugins.leona_discord.lib.mentions import apply_mention_map
from plugins.leona_discord.lib.messages import (
    BULLET_SPLIT_EACH_CHANCE,
    parse_discord_snowflake,
    split_message,
)
from plugins.leona_discord.lib.reply_style import (
    maybe_append_casual_emoji,
    plan_explicit_edit,
    plan_post_send_edit,
    should_quote_reply,
    SHORT_REPLY_EMOJI_MAX_CHARS,
)
from plugins.leona_discord.lib.send import edit_message, send_message
from plugins.leona_discord.lib.settings import get_effective_settings
from plugins.leona_discord.lib.think_tags import strip_think_tags
from plugins.leona_discord.lib.typing_indicator import (
    hold_typing_sync,
    human_pause_seconds,
    read_delay_seconds,
    typing_duration_seconds,
    INTER_CHUNK_MIN,
    INTER_CHUNK_MAX,
)
from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)


_PLACEHOLDER_EMOJI_MAP = {
    "flame": "🔥",
    "fire": "🔥",
    "thumbs up": "👍",
    "thumbsup": "👍",
    "thumb up": "👍",
    "heart": "❤️",
    "smile": "😊",
    "grin": "😄",
    "laugh": "😂",
    "cry": "😭",
    "sad": "😢",
    "eyes": "👀",
    "sparkles": "✨",
    "moon": "🌙",
    "wave": "👋",
}


def _normalize_placeholder_emoji(text: str) -> str:
    """Convert common LLM emoji placeholders like <flame emoji> to real emoji."""
    if not text:
        return text

    def repl(match):
        inner = (match.group(1) or "").strip().lower()
        inner = re.sub(r"\s+", " ", inner)
        inner = inner.replace("emoji:", "").replace("emote:", "").strip()
        inner = inner.replace(" emoji", "").strip()
        return _PLACEHOLDER_EMOJI_MAP.get(inner, match.group(0))

    return re.sub(r"<\s*([^<>]{1,40}?)\s*>", repl, text)


def _strip_unknown_emoji_placeholders(text: str) -> str:
    """Remove unresolved angle-bracket emoji placeholders from model output."""
    if not text:
        return text

    def repl(match):
        inner = (match.group(1) or "").strip().lower()
        if inner.startswith("@") or inner.startswith("#"):
            return match.group(0)
        if "emoji" in inner or "emote" in inner:
            return ""
        return match.group(0)

    return re.sub(r"<\s*([^<>]{1,60}?)\s*>", repl, text)


def _strip_malformed_react_tag(text: str) -> str:
    """Drop trailing malformed [react:... fragments missing closing bracket."""
    if not text:
        return text
    # Handles cases like "... text [react:👍" at end of output.
    return re.sub(r"\s*\[react:[^\]\n]{1,64}$", "", text, flags=re.IGNORECASE).rstrip()


def _strip_malformed_gif_tag(text: str) -> str:
    """Drop trailing malformed [gif:... fragments missing closing bracket."""
    if not text:
        return text
    return re.sub(r"\s*\[gif:[^\]\n]{1,120}$", "", text, flags=re.IGNORECASE).rstrip()


def _strip_malformed_edit_tag(text: str) -> str:
    """Drop trailing malformed [edit:... fragments missing closing bracket."""
    if not text:
        return text
    return re.sub(r"\s*\[edit:[^\]\n]{1,1900}$", "", text, flags=re.IGNORECASE).rstrip()


def reply_handler(task, event_data: dict, response_text: str):
    from plugins.leona_discord.tools.discord_tools import (
        was_tool_sent,
        clear_tool_sent,
        was_gif_sent,
        clear_gif_sent,
    )

    # Capture LLM output early (even if auto_reply is off).
    try:
        from plugins.leona_discord.lib import llm_debug
        llm_debug.record_response(
            event_data,
            response_raw=response_text or "",
            response_clean=strip_think_tags((response_text or "").strip()),
            task=task,
        )
    except Exception:
        pass

    trigger_config = task.get("trigger_config", {}) or {}
    if not trigger_config.get("auto_reply", False):
        logger.info(
            f"[DISCORD] auto_reply OFF — skipping reply to "
            f"#{event_data.get('channel_name', event_data.get('channel_id'))} "
            f"(task '{task.get('name', '?')}')"
        )
        return

    channel_id = event_data.get("channel_id")
    account = event_data.get("account", "")

    event_message_id = str(event_data.get("message_id", ""))
    if event_message_id and was_tool_sent(event_message_id):
        logger.info("[DISCORD] Reply handler skipped — tool already sent message for this event")
        clear_tool_sent(event_message_id)
        return

    if not channel_id or not account:
        logger.warning("[DISCORD] Reply handler missing channel_id or account")
        return

    channel_key = state.channel_key(account, channel_id)

    # --- Read delay: pause before "reading" the incoming message ---
    import time as _time
    trigger_content = event_data.get("content", "")
    read_delay = read_delay_seconds(len(trigger_content))
    _time.sleep(read_delay)

    clean = response_text.strip()

    clean = strip_think_tags(clean)
    clean = _normalize_placeholder_emoji(clean)
    clean = _strip_unknown_emoji_placeholders(clean)
    clean = _strip_malformed_react_tag(clean)
    clean = _strip_malformed_gif_tag(clean)
    clean = _strip_malformed_edit_tag(clean)

    from plugins.leona_discord.lib.sleep_forced_wake import (
        forced_wake_fallback_text,
        is_forced_wake_event,
    )
    from plugins.leona_discord.lib.settings import get_plugin_settings

    forced_wake = is_forced_wake_event(event_data)

    react_tags = re.findall(r'\[react:([^\]]{1,64})\]', clean)
    clean = re.sub(r'\[react:[^\]]{1,64}\]', '', clean).strip()

    gif_tags = re.findall(r'\[gif:([^\]]{1,120})\]', clean)
    clean = re.sub(r'\[gif:[^\]]{1,120}\]', '', clean).strip()
    inline_gif_query = gif_tags[0].strip() if gif_tags else ""

    edit_tags = re.findall(r'\[edit:([^\]]{1,1900})\]', clean, flags=re.IGNORECASE)
    clean = re.sub(r'\[edit:[^\]]{1,1900}\]', '', clean, flags=re.IGNORECASE).strip()
    inline_edit_text = edit_tags[-1].strip() if edit_tags else ""

    if react_tags or gif_tags or edit_tags:
        logger.info(
            "[DISCORD] Parsed inline tags: react=%s gif=%s edit=%s in #%s",
            len(react_tags), len(gif_tags), len(edit_tags),
            event_data.get("channel_name", channel_id),
        )

    # --- Multi-message replies: split at [break] markers ---
    # The LLM can include [break] to indicate natural thought boundaries.
    # This produces 1-3 short messages instead of one paragraph.
    break_parts = [p.strip() for p in re.split(r'\[break\]', clean, flags=re.IGNORECASE) if p.strip()]
    if not break_parts:
        break_parts = [clean] if clean else []

    if not clean and not inline_gif_query and not react_tags:
        if forced_wake:
            clean = forced_wake_fallback_text(get_plugin_settings().get("global", {}) or {})
            break_parts = [clean] if clean else []
            logger.info(
                f"[DISCORD] Forced-wake fallback used in "
                f"#{event_data.get('channel_name', channel_id)} "
                f"(LLM reply empty after strip; raw {len(response_text)} chars)"
            )
        else:
            logger.warning(
                f"[DISCORD] Empty reply after think-tag strip — raw response was "
                f"{len(response_text)} chars"
            )
            return

    inline_emoji = None
    if react_tags:
        candidate = react_tags[0].strip()
        from plugins.leona_discord.lib.emoji_policy import emoji_is_allowed
        if not emoji_is_allowed(candidate, get_effective_settings(event_data.get("guild_id", "")), event_data.get("guild_id", "")):
            logger.info(
                "[DISCORD] Inline react tag rejected by emoji policy: %r in #%s",
                candidate,
                event_data.get("channel_name", channel_id),
            )
            candidate = ''
        inline_emoji = candidate or None

    if not clean and not inline_gif_query and not inline_emoji:
        if forced_wake and not react_tags:
            clean = forced_wake_fallback_text(get_plugin_settings().get("global", {}) or {})
            break_parts = [clean] if clean else []
            logger.info(
                f"[DISCORD] Forced-wake fallback used in "
                f"#{event_data.get('channel_name', channel_id)} (react-only LLM reply)"
            )
        else:
            logger.info(
                "[DISCORD] Skipping send: empty text after tag parsing and no inline gif/react in #%s",
                event_data.get("channel_name", channel_id),
            )
            return

    mention_map = dict(event_data.get("mention_map", {}))
    guild_id_for_mentions = event_data.get("guild_id", "")
    # Apply mention mapping to each break part
    break_parts = [apply_mention_map(p, mention_map, account, guild_id_for_mentions) for p in break_parts]

    if break_parts:
        joined_len = sum(len(p) for p in break_parts) + max(0, len(break_parts) - 1) * 2
        if joined_len <= SHORT_REPLY_EMOJI_MAX_CHARS:
            break_parts[-1] = maybe_append_casual_emoji(break_parts[-1])
        clean = "\n\n".join(break_parts)
    else:
        clean = maybe_append_casual_emoji(clean)

    # Flatten: split each break part into Discord-sized chunks
    split_bullets = random.random() < BULLET_SPLIT_EACH_CHANCE
    all_chunks = []
    for part in (break_parts if break_parts else [clean]):
        all_chunks.extend(split_message(part, split_bullets=split_bullets))
    chunks = [c for c in all_chunks if c.strip()]

    guild_id = event_data.get("guild_id", "")
    effective = get_effective_settings(
        guild_id,
        channel_id=str(channel_id),
        channel_name=event_data.get("channel_name", ""),
    )
    edits_enabled = effective.get("message_edits_enabled", True)

    if inline_edit_text:
        inline_edit_text = apply_mention_map(
            inline_edit_text, mention_map, account, guild_id_for_mentions,
        )

    if not state._loop or not state._loop.is_running():
        logger.warning("[DISCORD] Reply handler: daemon loop not running")
        return

    if chunks and clean:
        try:
            trigger_content = event_data.get("trigger_content") or event_data.get("content", "")
            final_reply_text = clean

            # --- Contextual quote-reply ---
            reply_id = None
            for key in ("reply_to_message_id", "message_id"):
                reply_id = parse_discord_snowflake(event_data.get(key))
                if reply_id:
                    break
            if reply_id and not should_quote_reply(
                event_data,
                trigger_content,
                clean,
                account=account,
                channel_id=str(channel_id),
            ):
                reply_id = None

            edit_plan = None
            if inline_edit_text and edits_enabled and len(chunks) == 1:
                edit_plan = plan_explicit_edit(chunks[0], inline_edit_text)
            elif edits_enabled and len(chunks) == 1:
                edit_plan = plan_post_send_edit(chunks[0])

            # --- Human pause: jitter after LLM finishes, before typing ---
            _time.sleep(human_pause_seconds())

            # --- Typing simulation: speed varies with reply tone/content ---
            total_chars = sum(len(c) for c in chunks)
            typing_dur = typing_duration_seconds(total_chars, text=clean)
            hold_typing_sync(account, int(channel_id), typing_dur)

            sent_message_id = None
            for i, chunk in enumerate(chunks):
                send_text = edit_plan[1] if (i == 0 and edit_plan) else chunk
                future = asyncio.run_coroutine_threadsafe(
                    send_message(
                        account, int(channel_id), send_text,
                        reply_to_message_id=reply_id if i == 0 else None,
                    ),
                    state._loop,
                )
                sent_msg = future.result(timeout=15)
                if i == 0 and sent_msg:
                    sent_message_id = sent_msg.id
                logger.info(
                    f"[DISCORD] Reply chunk {i+1}/{len(chunks)} sent to "
                    f"#{event_data.get('channel_name', channel_id)} via {account}"
                )
                # --- Inter-chunk pause: re-type between multi-chunk replies ---
                if i < len(chunks) - 1:
                    pause = __import__('random').uniform(INTER_CHUNK_MIN, INTER_CHUNK_MAX)
                    _time.sleep(pause)
                    hold_typing_sync(
                        account,
                        int(channel_id),
                        typing_duration_seconds(len(chunks[i + 1]), text=chunks[i + 1]),
                    )

            if edit_plan and sent_message_id:
                delay, sent_text, edited_text = edit_plan
                _time.sleep(delay)
                try:
                    edit_future = asyncio.run_coroutine_threadsafe(
                        edit_message(account, int(channel_id), sent_message_id, edited_text),
                        state._loop,
                    )
                    edit_future.result(timeout=15)
                    from plugins.leona_discord.lib.edit_history import record_edit
                    edit_kind = (
                        "thought"
                        if edited_text.startswith(sent_text.rstrip())
                        and len(edited_text) > len(sent_text)
                        else "typo"
                    )
                    record_edit(
                        channel_key,
                        sent_message_id,
                        sent_text,
                        edited_text,
                        kind=edit_kind,
                    )
                    if len(chunks) == 1:
                        final_reply_text = edited_text
                    logger.info(
                        f"[DISCORD] Post-send edit applied to {sent_message_id} "
                        f"in #{event_data.get('channel_name', channel_id)}"
                        f"{' (LLM)' if inline_edit_text else ''}"
                    )
                except Exception as edit_err:
                    logger.debug(f"[DISCORD] Post-send edit failed: {edit_err}")
            # Mark cooldown AFTER the reply is sent (not at queue time)
            # so slow LLM inference doesn't eat the cooldown window.
            from plugins.leona_discord.lib.gates import mark_reply_cooldown
            effective = get_effective_settings(
                event_data.get("guild_id", ""),
                channel_id=str(channel_id),
                channel_name=event_data.get("channel_name", ""),
            )
            mark_reply_cooldown(effective, account, event_data.get("guild_id", ""), str(channel_id))
            # --- Engagement window: stay responsive in this channel ---
            from plugins.leona_discord.lib.cooldowns import mark_engaged
            from plugins.leona_discord.lib.engagement import (
                record_reply_length,
                record_topics_on_reply,
            )
            mark_engaged(account, channel_id)
            record_topics_on_reply(
                channel_key,
                event_data.get("trigger_content") or event_data.get("content", ""),
            )
            record_reply_length(channel_key, len(final_reply_text))
        except Exception as e:
            logger.error(f"[DISCORD] Reply failed: {e}")
            return
        history_reply_text = final_reply_text
    else:
        if inline_emoji and not clean and not chunks:
            logger.info(
                "[DISCORD] React-only LLM reply path in #%s (emoji=%s)",
                event_data.get("channel_name", channel_id),
                inline_emoji,
            )
        history_reply_text = clean

    clear_pending_payload(channel_key)

    try:
        from plugins.leona_discord.lib.gifs import try_gif_followup
        if event_message_id and was_gif_sent(event_message_id):
            logger.info(
                "[DISCORD] GIF follow-up skipped — discord_send_gif already sent for this event"
            )
            clear_gif_sent(event_message_id)
        else:
            try_gif_followup(event_data, clean, inline_query=inline_gif_query)
    except Exception as e:
        logger.warning(f"[DISCORD] GIF follow-up error: {e}")

    if inline_emoji and state._loop and state._loop.is_running():
        trigger_message_id = parse_discord_snowflake(event_data.get("message_id", ""))
        guild_id = event_data.get("guild_id", "")
        if trigger_message_id and mark_reacted(account, channel_id, str(trigger_message_id), inline_emoji):
            logger.info(
                "[DISCORD] Applying inline reaction %s to message %s in #%s",
                inline_emoji,
                trigger_message_id,
                event_data.get("channel_name", channel_id),
            )
            async def _fire_inline_react(emoji=inline_emoji, gid=guild_id, msg_id=trigger_message_id):
                try:
                    from plugins.leona_discord.lib.reactions import add_reaction_humanized
                    client_ref = state._clients.get(account)
                    if not client_ref or not client_ref.is_ready():
                        return
                    ch = client_ref.get_channel(int(channel_id))
                    if not ch:
                        ch = await client_ref.fetch_channel(int(channel_id))
                    msg = await ch.fetch_message(msg_id)
                    await add_reaction_humanized(
                        msg, account, gid, emoji, str(channel_id),
                    )
                except Exception as e:
                    logger.debug(f"[DISCORD] Inline react failed: {e}")

            asyncio.run_coroutine_threadsafe(_fire_inline_react(), state._loop)
        elif not trigger_message_id:
            logger.info(
                "[DISCORD] Inline reaction skipped: invalid/non-snowflake trigger message id %r",
                event_data.get("message_id", ""),
            )
        else:
            logger.info(
                "[DISCORD] Inline reaction skipped: already reacted to message %s in #%s",
                trigger_message_id,
                event_data.get("channel_name", channel_id),
            )

    client = state._clients.get(account)
    bot_display = client.user.display_name if (client and client.is_ready()) else account
    append_bot_reply(
        channel_key,
        history_reply_text or (f"[gif:{inline_gif_query}]" if inline_gif_query else ""),
        account, bot_display,
        guild_id=event_data.get("guild_id", ""),
        guild_name=event_data.get("guild_name", ""),
        channel_name=event_data.get("channel_name", ""),
    )

    try:
        from plugins.leona_discord.lib import profile as user_profile
        user_profile.record_bot_reply(
            account,
            event_data.get("guild_id", ""),
            event_data.get("author_id", ""),
            is_dm=bool(event_data.get("is_dm")),
        )
    except Exception:
        pass
