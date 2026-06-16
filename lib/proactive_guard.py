"""Coordination between morning greetings and quiet-channel outreach."""

from datetime import datetime, timezone
from plugins.leona_discord.lib.schedule_utils import parse_target as _parse_target

# Hours before the greeting UTC hour (inclusive) where outreach is suppressed
# on channels that also receive the morning greeting.
GREETING_OUTREACH_LEAD_HOURS = 2


def is_greeting_target(account: str, channel_id: str, raw: dict) -> bool:
    account = (account or "").strip()
    channel_id = str(channel_id or "").strip()
    if not account or not channel_id:
        return False
    g = raw.get("global", {}) or {}
    for entry in g.get("greeting_targets") or []:
        parsed = _parse_target(entry)
        if parsed and parsed[0] == account and parsed[2] == channel_id:
            return True
    return False


def greeting_block_hours(raw: dict) -> set:
    """UTC hours when outreach should defer to the morning greeter."""
    g = raw.get("global", {}) or {}
    if not g.get("greeting_enabled", False):
        return set()
    try:
        greeting_hour = int(g.get("greeting_utc_hour", 9)) % 24
    except (TypeError, ValueError):
        greeting_hour = 9
    lead = max(0, min(6, int(g.get("outreach_greeting_lead_hours", GREETING_OUTREACH_LEAD_HOURS))))
    blocked = set()
    for offset in range(lead + 1):
        blocked.add((greeting_hour - offset) % 24)
    return blocked


def outreach_skip_reason_for_greeting(raw: dict, account: str, channel_id: str) -> str:
    """Return a skip reason if outreach should yield to the morning greeting."""
    if not is_greeting_target(account, channel_id, raw):
        return ""
    blocked = greeting_block_hours(raw)
    if not blocked:
        return ""
    hour = datetime.now(timezone.utc).hour
    if hour in blocked:
        try:
            g = raw.get("global", {}) or {}
            target_hour = int(g.get("greeting_utc_hour", 9)) % 24
        except (TypeError, ValueError):
            target_hour = 9
        return f"greeting window (UTC {target_hour}:00)"
    return ""


def record_proactive_ping(account: str, channel_id: str, *, source: str = "outreach", sent_at: float = None):
    """Record a bot-initiated proactive message (outreach or greeting)."""
    from plugins.leona_discord.lib.store import record_outreach

    record_outreach(account, channel_id, sent_at)
    import logging
    logging.getLogger(__name__).debug(
        f"[LEONA-DISCORD] Proactive ping recorded ({source}) for {account}:{channel_id}"
    )
