"""Proactive conversation starters when configured channels go quiet."""

# -- Portable import path (works from plugins/ or user/plugins/) --
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('_ldc', str(__import__('pathlib').Path(__file__).resolve().parent.parent / '_compat.py'))
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod); del _ilu, _spec, _mod

import logging
import random
import time

from plugins.leona_discord.lib.schedule_utils import (
    parse_target,
    resolve_names,
    send_scheduled_message,
)

logger = logging.getLogger(__name__)


def run(event):
    """Called by the continuity scheduler every 15 minutes."""
    from plugins.leona_discord.lib.presence import in_quiet_hours
    from plugins.leona_discord.lib.settings import get_plugin_settings
    from plugins.leona_discord.lib.store import (
        get_last_human_message_at,
        get_last_outreach_at,
    )

    system = (event or {}).get("system")
    raw = get_plugin_settings()
    g = raw.get("global", {}) or {}
    if not g.get("outreach_enabled", False):
        return "Skipped (disabled)"

    if in_quiet_hours(g):
        return "Skipped (quiet hours)"

    from plugins.leona_discord.lib.sleep_schedule import (
        in_sleep_hours,
        is_sleep_schedule_enabled,
        sleep_utc_hour,
        wake_utc_hour,
    )

    if is_sleep_schedule_enabled(g) and in_sleep_hours(g):
        return (
            f"Skipped (sleep hours UTC {sleep_utc_hour(g):02d}:00–"
            f"{wake_utc_hour(g):02d}:00)"
        )

    if not _in_active_hours(g):
        return "Skipped (outside active hours)"

    targets = g.get("outreach_targets") or []
    if not isinstance(targets, list) or not targets:
        return "Skipped (no targets)"

    try:
        quiet_minutes = max(30, min(24 * 60, int(g.get("outreach_quiet_minutes", 240))))
    except (TypeError, ValueError):
        quiet_minutes = 240
    try:
        cooldown_hours = max(1, min(72, int(g.get("outreach_cooldown_hours", 8))))
    except (TypeError, ValueError):
        cooldown_hours = 8
    try:
        skip_chance = max(0, min(90, int(g.get("outreach_skip_chance", 25))))
    except (TypeError, ValueError):
        skip_chance = 25

    use_llm = g.get("outreach_use_llm", True)
    use_typing = g.get("outreach_typing_indicator", True)
    instructions = str(g.get("outreach_message") or "").strip()
    fallback = str(g.get("outreach_fallback") or "Anyone around? 👀").strip()
    provider = str(g.get("outreach_model_provider") or "").strip()
    model = str(g.get("outreach_model_name") or "").strip()
    try:
        max_tokens = int(g.get("outreach_max_tokens", 180))
    except (TypeError, ValueError):
        max_tokens = 180

    quiet_seconds = quiet_minutes * 60.0
    cooldown_seconds = cooldown_hours * 3600.0
    now = time.time()

    sent = 0
    skipped = 0
    errors = []

    for entry in targets:
        try:
            parsed = parse_target(entry)
            if not parsed:
                continue
            account, guild_id, channel_id = parsed

            from plugins.leona_discord.lib.proactive_guard import outreach_skip_reason_for_greeting
            from plugins.leona_discord.lib.sleep_schedule import outreach_skip_reason_for_sleep

            skip_reason = outreach_skip_reason_for_greeting(raw, account, channel_id)
            if skip_reason:
                skipped += 1
                continue

            skip_reason = outreach_skip_reason_for_sleep(raw, account, channel_id)
            if skip_reason:
                skipped += 1
                continue

            last_human = get_last_human_message_at(account, channel_id)
            if last_human is None:
                skipped += 1
                continue
            if now - last_human < quiet_seconds:
                skipped += 1
                continue

            last_outreach = get_last_outreach_at(account, channel_id)
            if last_outreach is not None and now - last_outreach < cooldown_seconds:
                skipped += 1
                continue

            if skip_chance > 0 and random.randint(1, 100) <= skip_chance:
                skipped += 1
                continue

            guild_name, channel_name = resolve_names(account, guild_id, channel_id)
            quiet_hours = (now - last_human) / 3600.0

            message = _build_message(
                system, use_llm, instructions, fallback,
                guild_name, channel_name, guild_id, channel_id, account,
                provider, model, max_tokens, quiet_hours,
            )
            if not message:
                errors.append(f"{account}:{channel_id}:empty")
                continue

            if send_scheduled_message(account, channel_id, message, use_typing=use_typing):
                from plugins.leona_discord.lib.proactive_guard import record_proactive_ping
                record_proactive_ping(account, channel_id, source="outreach", sent_at=now)
                sent += 1
            else:
                errors.append(f"{account}:{channel_id}")
        except Exception as e:
            errors.append(str(e))

    summary = f"Sent {sent} outreach message(s), skipped {skipped}"
    if errors:
        summary += f"; failed: {', '.join(errors[:5])}"
    logger.info(f"[LEONA-DISCORD] Quiet outreach: {summary}")
    return summary


def _in_active_hours(settings: dict) -> bool:
    from datetime import datetime, timezone

    try:
        start = int(settings.get("outreach_active_start", 10)) % 24
        end = int(settings.get("outreach_active_end", 21)) % 24
    except (TypeError, ValueError):
        return True
    hour = datetime.now(timezone.utc).hour
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _build_message(
    system, use_llm, instructions, fallback,
    guild_name, channel_name, guild_id, channel_id, account,
    provider, model, max_tokens, quiet_hours,
) -> str:
    if use_llm and system:
        from plugins.leona_discord.lib.history import format_proactive_history, get_history_snapshot
        from plugins.leona_discord.lib import state
        from plugins.leona_discord.lib.outreach_llm import generate_outreach

        channel_key = state.channel_key(account, channel_id)
        history = get_history_snapshot(channel_key)
        recent = format_proactive_history(history, guild_id, account) if history else []

        text = generate_outreach(
            system,
            account=account,
            guild_name=guild_name,
            channel_name=channel_name,
            instructions=instructions,
            recent_chat=recent,
            quiet_hours=quiet_hours,
            provider_key=provider,
            model_name=model,
            max_tokens=max_tokens,
        )
        if text:
            return text
        logger.warning("[LEONA-DISCORD] Outreach LLM returned empty — using fallback")

    if instructions and not use_llm:
        return instructions
    return fallback
