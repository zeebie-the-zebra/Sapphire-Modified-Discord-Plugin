"""Discord on_message event handler with gate tracing."""

import logging

from plugins.leona_discord.lib.activity import record_message
from plugins.leona_discord.lib.batching import get_or_create_batch, queue_message
from plugins.leona_discord.lib import gates
from plugins.leona_discord.lib.history import append_message
from plugins.leona_discord.lib.images import collect_image_urls
from plugins.leona_discord.lib.reactions import try_silent_react
from plugins.leona_discord.lib.safety import run_safety_checks
from plugins.leona_discord.lib.settings import get_effective_settings, get_plugin_settings
from plugins.leona_discord.lib.trace import MessageTrace
from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)


def register_on_message(client, account_name: str):
    @client.event
    async def on_message(message):
        logger.debug(
            f"[DISCORD] on_message: author={message.author} bot={message.author.bot} "
            f"content={(message.clean_content or '')[:50] or '(empty)'}"
        )

        if message.author == client.user:
            return

        is_dm = message.guild is None
        guild_id = str(message.guild.id) if message.guild else ""
        guild_name = message.guild.name if message.guild else "DM"
        channel_id_str = str(message.channel.id)
        channel_name = getattr(message.channel, "name", "DM")
        channel_key = state.channel_key(account_name, channel_id_str)

        effective = get_effective_settings(
            guild_id=guild_id,
            channel_id=channel_id_str,
            channel_name=channel_name,
            is_dm=is_dm,
            channel_key=channel_key,
        )
        trace_enabled = get_plugin_settings().get("debug_trace_enabled", True)

        triggers = gates.evaluate_triggers(message, client, effective)
        mentioned = triggers["mentioned"]
        author_id = str(message.author.id)

        trace = None
        if trace_enabled:
            trace = MessageTrace(
                account_name, guild_id, channel_id_str, channel_name,
                str(message.id), message.author.display_name, mentioned,
            )

        allowed, deny_reason = gates.check_user_access(
            author_id, message.author.bot, effective,
        )
        if not allowed:
            if trace:
                trace.gate("user_access", False, deny_reason)
                trace.finish(f"dropped_{deny_reason}")
            await try_silent_react(message, account_name, effective, guild_id=guild_id)
            return
        if trace:
            trace.gate("user_access", True)

        safe, safety_reason = await run_safety_checks(
            message, effective, account_name, channel_key,
        )
        if not safe:
            if trace:
                trace.gate("safety", False, safety_reason)
                trace.finish(f"dropped_{safety_reason}")
            return
        if trace:
            trace.gate("safety", True)

        from plugins.leona_discord.lib.sleep_forced_wake import (
            handle_sleep_mention,
            wrap_forced_wake_content,
        )
        from plugins.leona_discord.lib.sleep_schedule import is_channel_asleep
        from plugins.leona_discord.lib.store import (
            buffer_sleep_mention,
            mark_sleep_buffer_message_processed,
        )

        if is_channel_asleep(account_name, channel_id_str):
            if not mentioned:
                if trace:
                    trace.finish("sleep_dormant")
                return

            buffer_sleep_mention(
                account_name,
                guild_id,
                channel_id_str,
                str(message.id),
                author_id,
                message.author.name,
                message.author.display_name,
                message.clean_content or "",
                image_urls=collect_image_urls(message),
            )
            global_s = get_plugin_settings().get("global", {}) or {}
            wake_hint = handle_sleep_mention(account_name, channel_id_str, global_s)
            if wake_hint is None:
                if trace:
                    trace.gate("sleep_buffer", True, "direct @mention held until wake")
                    trace.finish("sleep_buffered_mention")
                return

            mark_sleep_buffer_message_processed(
                account_name, channel_id_str, str(message.id),
            )
            if trace:
                trace.gate("sleep_forced_wake", True, "replying while temporarily awake")

            image_urls = collect_image_urls(message)
            raw_content = wrap_forced_wake_content(
                message.clean_content or "", wake_hint,
            )
            msg_data = {
                "message_id": str(message.id),
                "content": raw_content,
                "clean_content": raw_content,
                "username": message.author.name,
                "display_name": message.author.display_name,
                "author_id": author_id,
                "mentioned": str(mentioned),
                "image_urls": image_urls,
                "sleep_forced_wake": True,
            }

            append_message(channel_key, msg_data, guild_id=guild_id)
            record_message(channel_key)

            from plugins.leona_discord.lib import profile as user_profile
            user_profile.record_user_message(
                account_name,
                guild_id,
                author_id,
                username=message.author.name,
                display_name=message.author.display_name,
                content=raw_content,
                is_dm=is_dm,
                is_bot=message.author.bot,
                message_id=str(message.id),
                thread_reply_to_bot=True,
                mentioned=True,
            )

            if trace:
                trace.gate("persisted_history", True)

            batch = get_or_create_batch(account_name, message)
            queue_message(batch, msg_data)
            if trace:
                trace.gate("batched", True)
                trace.finish("queued_forced_wake_reply")
            return

        image_urls = collect_image_urls(message)
        msg_data = {
            "message_id": str(message.id),
            "content": message.clean_content or "",
            "clean_content": message.clean_content or "",
            "username": message.author.name,
            "display_name": message.author.display_name,
            "author_id": author_id,
            "mentioned": str(mentioned),
            "image_urls": image_urls,
        }

        append_message(channel_key, msg_data, guild_id=guild_id)
        record_message(channel_key)

        from plugins.leona_discord.lib import profile as user_profile
        from plugins.leona_discord.lib.engagement import is_reply_to_bot_message

        thread_reply = await is_reply_to_bot_message(message, client)
        user_profile.record_user_message(
            account_name,
            guild_id,
            author_id,
            username=message.author.name,
            display_name=message.author.display_name,
            content=message.clean_content or "",
            is_dm=is_dm,
            is_bot=message.author.bot,
            message_id=str(message.id),
            thread_reply_to_bot=thread_reply,
            mentioned=mentioned,
        )

        if trace:
            trace.gate("persisted_history", True)

        soft_trigger = triggers["name_matched"] or triggers["keyword_matched"] or triggers["role_trigger"]
        await try_silent_react(message, account_name, effective, guild_id=guild_id)

        from plugins.leona_discord.lib.cooldowns import engagement_boost
        from plugins.leona_discord.lib.engagement import (
            apply_engagement_adjustments,
            record_topics_skipped,
        )

        effective = engagement_boost(effective, account_name, channel_id_str)
        if trace and thread_reply:
            trace.gate("thread_reply", True, "reply to bot message")
        effective = apply_engagement_adjustments(
            effective,
            channel_key=channel_key,
            message_content=message.clean_content or "",
            is_thread_reply=thread_reply,
        )
        effective = user_profile.apply_profile_engagement(
            effective,
            account_name,
            guild_id,
            author_id,
            is_dm=is_dm,
        )

        scope = effective.get("cooldown_scope", "per_channel")
        queue, outcome = gates.should_queue_reply(
            settings=effective,
            mentioned=mentioned,
            name_matched=triggers["name_matched"],
            keyword_matched=triggers["keyword_matched"],
            role_trigger=triggers["role_trigger"],
            is_bot=message.author.bot,
            scope=scope,
            account=account_name,
            guild_id=guild_id,
            channel_id=channel_id_str,
            has_images=bool(image_urls),
            trace=trace,
        )

        if not queue:
            organic_human_drop = (
                not mentioned
                and not soft_trigger
                and not message.author.bot
                and outcome in ("dropped_human_chance", "dropped_human_zero")
            )
            if organic_human_drop:
                record_topics_skipped(channel_key, message.clean_content or "")
                user_profile.record_outcome(
                    account_name, guild_id, author_id, "ignored", is_dm=is_dm,
                )
            if trace:
                trace.finish(outcome or "dropped")
            return

        # Read-only react: saw the message, maybe reacted, chose not to reply
        organic = not mentioned and not soft_trigger
        if organic and gates.should_read_only_react():
            await try_silent_react(
                message, account_name, effective, guild_id=guild_id, force=True,
            )
            user_profile.record_outcome(
                account_name, guild_id, author_id, "react_only", is_dm=is_dm,
            )
            if trace:
                trace.gate("read_only_react", True)
                trace.finish("read_only_react")
            return

        batch = get_or_create_batch(account_name, message)
        queue_message(batch, msg_data)
        if trace:
            trace.gate("batched", True)
            trace.finish("queued_for_reply")

    @client.event
    async def on_typing(channel, user, when):
        """Extend the batch window while the trigger author is still typing."""
        if user.bot:
            return
        try:
            from plugins.leona_discord.lib.batching import extend_batch_timer
            channel_id = str(channel.id)
            extend_batch_timer(account_name, channel_id)
        except Exception:
            pass
