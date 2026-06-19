"""Route LLM responses back to Discord channels."""

import asyncio
import logging
import random
import re

from plugins.leona_discord.lib.context_cache import clear_pending_payload, has_reacted, mark_reacted
from plugins.leona_discord.lib.history import append_bot_reply
from plugins.leona_discord.lib.mentions import apply_mention_map
from plugins.leona_discord.lib.messages import (
    BULLET_SPLIT_EACH_CHANCE,
    parse_discord_snowflake,
    split_message,
)
from plugins.leona_discord.lib.inline_tags import parse_inline_tags
from plugins.leona_discord.lib.reply_style import (
    maybe_append_casual_emoji,
    plan_explicit_edit,
    plan_post_send_edit,
    should_quote_reply,
    SHORT_REPLY_EMOJI_MAX_CHARS,
)
from plugins.leona_discord.lib.send import edit_message, send_message
from plugins.leona_discord.lib.settings import get_effective_settings
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


def reply_handler(task, event_data: dict, response_text: str):
    from plugins.leona_discord.tools.discord_tools import (
        was_tool_sent,
        clear_tool_sent,
        pop_tool_sent_text,
        was_gif_sent,
        clear_gif_sent,
    )

    parsed_preview = parse_inline_tags(response_text or "")
    delivery_path = ""
    discord_sent_text = ""

    # Capture LLM output early (even if auto_reply is off).
    try:
        from plugins.leona_discord.lib import llm_debug
        llm_debug.record_response(
            event_data,
            response_raw=response_text or "",
            response_clean=parsed_preview.clean,
            task=task,
        )
    except Exception:
        pass

    trigger_config = task.get("trigger_config", {}) or {}
    auto_reply = bool(task.get("auto_reply") or trigger_config.get("auto_reply"))
    if not auto_reply:
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
        discord_sent_text = pop_tool_sent_text(event_message_id)
        delivery_path = "tool"
        logger.info(
            "[DISCORD] Reply handler skipped — tool already sent message for this event"
            + (f" ({len(discord_sent_text)} chars)" if discord_sent_text else "")
        )
        try:
            from plugins.leona_discord.lib import llm_debug
            llm_debug.record_response(
                event_data,
                response_raw=response_text or "",
                response_clean=parsed_preview.clean,
                task=task,
                delivery_path=delivery_path,
                discord_sent_text=discord_sent_text,
            )
        except Exception:
            pass
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
    parsed = parse_inline_tags(clean)
    clean = parsed.clean
    react_tags = parsed.react_tags
    gif_tags = parsed.gif_tags
    edit_tags = parsed.edit_tags
    inline_gif_query = parsed.inline_gif_query
    inline_edit_text = parsed.inline_edit_text

    from plugins.leona_discord.lib.sleep_forced_wake import (
        forced_wake_fallback_text,
        is_forced_wake_event,
    )
    from plugins.leona_discord.lib.settings import get_plugin_settings

    forced_wake = is_forced_wake_event(event_data)

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
    split_bullets = False if (inline_edit_text or inline_gif_query) else None
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

    edit_chunk_idx = None
    edit_plan = None
    if inline_edit_text and edits_enabled and chunks:
        edit_chunk_idx = 0 if len(chunks) == 1 else len(chunks) - 1
        edit_plan = plan_explicit_edit(chunks[edit_chunk_idx], inline_edit_text)
        if not edit_plan:
            edit_chunk_idx = None

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

            if not edit_plan and edits_enabled and len(chunks) == 1 and not inline_edit_text:
                edit_plan = plan_post_send_edit(chunks[0])
                if edit_plan:
                    edit_chunk_idx = 0

            # --- Human pause: jitter after LLM finishes, before typing ---
            _time.sleep(human_pause_seconds())

            # --- Typing simulation: speed varies with reply tone/content ---
            total_chars = sum(len(c) for c in chunks)
            typing_dur = typing_duration_seconds(total_chars, text=clean)
            hold_typing_sync(account, int(channel_id), typing_dur)

            sent_message_ids: dict[int, int] = {}
            for i, chunk in enumerate(chunks):
                send_text = edit_plan[1] if (edit_plan and i == edit_chunk_idx) else chunk
                future = asyncio.run_coroutine_threadsafe(
                    send_message(
                        account, int(channel_id), send_text,
                        reply_to_message_id=reply_id if i == 0 else None,
                    ),
                    state._loop,
                )
                sent_msg = future.result(timeout=15)
                if sent_msg:
                    sent_message_ids[i] = sent_msg.id
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

            if edit_plan and edit_chunk_idx is not None:
                edit_msg_id = sent_message_ids.get(edit_chunk_idx)
                if edit_msg_id:
                    delay, sent_text, edited_text = edit_plan
                    _time.sleep(delay)
                    try:
                        edit_future = asyncio.run_coroutine_threadsafe(
                            edit_message(account, int(channel_id), edit_msg_id, edited_text),
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
                            edit_msg_id,
                            sent_text,
                            edited_text,
                            kind=edit_kind,
                        )
                        if len(chunks) == 1:
                            final_reply_text = edited_text
                        elif edit_chunk_idx == len(chunks) - 1:
                            final_reply_text = "\n\n".join(
                                chunks[:edit_chunk_idx] + [edited_text]
                            )
                        logger.info(
                            f"[DISCORD] Post-send edit applied to {edit_msg_id} "
                            f"in #{event_data.get('channel_name', channel_id)}"
                            f"{' (LLM)' if inline_edit_text else ''}"
                        )
                    except Exception as edit_err:
                        logger.warning(f"[DISCORD] Post-send edit failed: {edit_err}")
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
        react_settings = get_effective_settings(
            guild_id,
            channel_id=str(channel_id),
            channel_name=event_data.get("channel_name", ""),
        )
        from plugins.leona_discord.lib.gates import reaction_allowed

        if not reaction_allowed(react_settings, account, guild_id, str(channel_id)):
            logger.info(
                "[DISCORD] Inline reaction skipped: reactions disabled or on cooldown in #%s",
                event_data.get("channel_name", channel_id),
            )
        elif not react_settings.get("react_to_trigger", True):
            logger.info(
                "[DISCORD] Inline reaction skipped: react_to_trigger disabled in #%s",
                event_data.get("channel_name", channel_id),
            )
        elif not trigger_message_id:
            logger.info(
                "[DISCORD] Inline reaction skipped: invalid/non-snowflake trigger message id %r",
                event_data.get("message_id", ""),
            )
        elif has_reacted(account, channel_id, str(trigger_message_id), inline_emoji):
            logger.info(
                "[DISCORD] Inline reaction skipped: already reacted to message %s in #%s",
                trigger_message_id,
                event_data.get("channel_name", channel_id),
            )
        else:
            logger.info(
                "[DISCORD] Applying inline reaction %s to message %s in #%s",
                inline_emoji,
                trigger_message_id,
                event_data.get("channel_name", channel_id),
            )

            async def _fire_inline_react(emoji=inline_emoji, gid=guild_id, msg_id=trigger_message_id):
                from plugins.leona_discord.lib.reactions import add_reaction_humanized
                client_ref = state._clients.get(account)
                if not client_ref or not client_ref.is_ready():
                    raise RuntimeError("client not ready")
                ch = client_ref.get_channel(int(channel_id))
                if not ch:
                    ch = await client_ref.fetch_channel(int(channel_id))
                msg = await ch.fetch_message(msg_id)
                await add_reaction_humanized(
                    msg, account, gid, emoji, str(channel_id),
                )
                mark_reacted(account, channel_id, str(msg_id), emoji)

            try:
                react_future = asyncio.run_coroutine_threadsafe(
                    _fire_inline_react(), state._loop,
                )
                react_future.result(timeout=12)
            except Exception as e:
                logger.warning(f"[DISCORD] Inline react failed: {e}")

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
