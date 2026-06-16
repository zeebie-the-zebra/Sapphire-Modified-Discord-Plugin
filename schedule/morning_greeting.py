"""Scheduled morning greetings to configured Discord channels."""

import logging

from plugins.leona_discord.lib.schedule_utils import (
    parse_target,
    resolve_names,
    send_scheduled_message,
)

logger = logging.getLogger(__name__)


def run(event):
    """Called by the continuity scheduler once per hour (cron at :00)."""
    from plugins.leona_discord.lib.settings import get_plugin_settings

    system = (event or {}).get("system")
    raw = get_plugin_settings()
    return run_greeting(raw, system=system, test=False)


def run_greeting(raw: dict, system=None, *, test: bool = False) -> str:
    """Send morning greetings to configured targets.

    When test=True, skips the enabled toggle and UTC hour gate (for manual UI tests).
    """
    from datetime import datetime, timezone

    raw = raw or {}
    g = raw.get("global", {}) or {}
    sleep_on = g.get("sleep_schedule_enabled", False)
    if not test and not g.get("greeting_enabled", False) and not sleep_on:
        return "Skipped (disabled)"

    if not test:
        from plugins.leona_discord.lib.presence import in_quiet_hours
        if in_quiet_hours(g) and not sleep_on:
            return "Skipped (quiet hours)"

        try:
            target_hour = int(g.get("greeting_utc_hour", 9)) % 24
        except (TypeError, ValueError):
            target_hour = 9
        if datetime.now(timezone.utc).hour != target_hour:
            return f"Skipped (not hour {target_hour} UTC)"

    from plugins.leona_discord.lib.sleep_schedule import (
        is_channel_asleep,
        is_sleep_schedule_enabled,
        sleep_targets,
        wake_channel,
    )

    if sleep_on and is_sleep_schedule_enabled(g):
        targets = sleep_targets(raw) or (g.get("greeting_targets") or [])
    else:
        targets = g.get("greeting_targets") or []
    if not isinstance(targets, list) or not targets:
        return "Skipped (no targets)"

    use_llm = g.get("greeting_use_llm", True)
    instructions = str(g.get("greeting_message") or "").strip()
    fallback = str(g.get("greeting_fallback") or "Good morning, everyone! ☀️").strip()
    provider = str(g.get("greeting_model_provider") or "").strip()
    model = str(g.get("greeting_model_name") or "").strip()
    try:
        max_tokens = int(g.get("greeting_max_tokens", 180))
    except (TypeError, ValueError):
        max_tokens = 180

    sent = 0
    errors = []
    label = "Greeting test" if test else "Morning greeting"

    for entry in targets:
        try:
            parsed = parse_target(entry)
            if not parsed:
                continue
            account, guild_id, channel_id = parsed
            guild_name, channel_name = resolve_names(account, guild_id, channel_id)

            message = _build_message(
                system, use_llm, instructions, fallback,
                guild_name, channel_name, guild_id, channel_id, account,
                provider, model, max_tokens,
            )
            if not message:
                errors.append(f"{account}:{channel_id}:empty")
                continue

            if send_scheduled_message(account, channel_id, message):
                from plugins.leona_discord.lib.proactive_guard import record_proactive_ping
                record_proactive_ping(account, channel_id, source="greeting")
                was_asleep = is_channel_asleep(account, channel_id)
                if was_asleep:
                    wake_channel(account, channel_id)
                    from plugins.leona_discord.lib.sleep_buffer import drain_sleep_buffer
                    from plugins.leona_discord.lib.sleep_schedule import buffered_reply_max

                    pending = drain_sleep_buffer(
                        account,
                        channel_id,
                        guild_id,
                        guild_name,
                        channel_name,
                        max_replies=buffered_reply_max(g),
                    )
                    if pending:
                        logger.info(
                            f"[LEONA-DISCORD] Wake: queued {pending} buffered @mention reply(s) "
                            f"for #{channel_name or channel_id}"
                        )
                sent += 1
            else:
                errors.append(f"{account}:{channel_id}")
        except Exception as e:
            errors.append(str(e))

    summary = f"Sent {sent} greeting(s)"
    if errors:
        summary += f"; failed: {', '.join(errors[:5])}"
    logger.info(f"[LEONA-DISCORD] {label}: {summary}")
    return summary


def _build_message(
    system, use_llm, instructions, fallback,
    guild_name, channel_name, guild_id, channel_id, account,
    provider, model, max_tokens,
) -> str:
    if use_llm and system:
        from plugins.leona_discord.lib.greeting_llm import generate_greeting
        from plugins.leona_discord.lib.history import format_proactive_history, get_history_snapshot
        from plugins.leona_discord.lib import state

        channel_key = state.channel_key(account, channel_id)
        history = get_history_snapshot(channel_key)
        recent = format_proactive_history(history, guild_id, account) if history else []

        text = generate_greeting(
            system,
            account=account,
            guild_name=guild_name,
            channel_name=channel_name,
            instructions=instructions,
            recent_chat=recent,
            provider_key=provider,
            model_name=model,
            max_tokens=max_tokens,
        )
        if text:
            return text
        logger.warning("[LEONA-DISCORD] Greeting LLM returned empty — using fallback")

    if instructions and not use_llm:
        return instructions
    return fallback
