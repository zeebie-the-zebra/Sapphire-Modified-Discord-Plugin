"""Scheduled goodnight messages and sleep state transitions."""

import logging

from plugins.leona_discord.lib.schedule_utils import (
    parse_target,
    resolve_names,
    send_scheduled_message,
)

logger = logging.getLogger(__name__)


def run(event):
    """Called every 15 minutes by the continuity scheduler."""
    from plugins.leona_discord.lib.settings import get_plugin_settings

    system = (event or {}).get("system")
    raw = get_plugin_settings()
    return run_sleep_goodnight(raw, system=system)


def run_sleep_goodnight(raw: dict, system=None) -> str:
    from datetime import datetime, timezone

    from plugins.leona_discord.lib.sleep_schedule import (
        enter_sleep,
        goodnight_due,
        is_sleep_schedule_enabled,
        iter_sleep_target_channels,
        should_send_goodnight_now,
    )

    raw = raw or {}
    g = raw.get("global", {}) or {}
    if not is_sleep_schedule_enabled(g):
        return "Skipped (sleep schedule disabled)"

    now = datetime.now(timezone.utc)
    if not should_send_goodnight_now(g, now):
        return f"Skipped (not sleep hour {g.get('sleep_utc_hour', 22)} UTC)"

    use_llm = g.get("sleep_use_llm", True)
    instructions = str(g.get("sleep_message") or "").strip()
    fallback = str(g.get("sleep_fallback") or "Good night, everyone! 🌙").strip()
    provider = str(g.get("sleep_model_provider") or g.get("greeting_model_provider") or "").strip()
    model = str(g.get("sleep_model_name") or g.get("greeting_model_name") or "").strip()
    try:
        max_tokens = int(g.get("sleep_max_tokens", g.get("greeting_max_tokens", 180)))
    except (TypeError, ValueError):
        max_tokens = 180

    sent = 0
    skipped = 0
    errors = []

    for account, guild_id, channel_id in iter_sleep_target_channels(raw):
        try:
            if not goodnight_due(account, channel_id, g, now):
                skipped += 1
                continue

            guild_name, channel_name = resolve_names(account, guild_id, channel_id)
            message = _build_goodnight(
                system, use_llm, instructions, fallback,
                guild_name, channel_name, guild_id, channel_id, account,
                provider, model, max_tokens,
            )
            if not message:
                errors.append(f"{account}:{channel_id}:empty")
                continue

            if send_scheduled_message(account, channel_id, message, use_typing=True):
                enter_sleep(account, channel_id)
                sent += 1
            else:
                errors.append(f"{account}:{channel_id}")
        except Exception as e:
            errors.append(str(e))

    summary = f"Goodnight sent to {sent} channel(s), skipped {skipped}"
    if errors:
        summary += f"; failed: {', '.join(errors[:5])}"
    logger.info(f"[LEONA-DISCORD] Sleep goodnight: {summary}")
    return summary


def _build_goodnight(
    system, use_llm, instructions, fallback,
    guild_name, channel_name, guild_id, channel_id, account,
    provider, model, max_tokens,
) -> str:
    if use_llm and system:
        from plugins.leona_discord.lib.goodnight_llm import generate_goodnight
        from plugins.leona_discord.lib.history import format_proactive_history, get_history_snapshot
        from plugins.leona_discord.lib import state

        channel_key = state.channel_key(account, channel_id)
        history = get_history_snapshot(channel_key)
        recent = format_proactive_history(history, guild_id, account) if history else []

        text = generate_goodnight(
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
        logger.warning("[LEONA-DISCORD] Goodnight LLM returned empty — using fallback")

    if instructions and not use_llm:
        return instructions
    return fallback
