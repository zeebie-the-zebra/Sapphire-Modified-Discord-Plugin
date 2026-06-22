"""Sleep schedule: goodnight, dormant mode, and buffered @mentions until wake."""

import logging
import random
from datetime import datetime, timezone

from plugins.leona_discord.lib.schedule_utils import parse_target

logger = logging.getLogger(__name__)

# sleep_goodnight cron is */15 — only these minutes are checked each sleep hour
GOODNIGHT_CRON_MINUTES = (0, 15, 30, 45)
LAST_GOODNIGHT_CRON_MINUTE = GOODNIGHT_CRON_MINUTES[-1]


def sleep_settings(global_s: dict) -> dict:
    return global_s or {}


def is_sleep_schedule_enabled(global_s: dict) -> bool:
    return bool(sleep_settings(global_s).get("sleep_schedule_enabled", False))


def sleep_targets(raw: dict) -> list:
    g = sleep_settings(raw.get("global", {}) or {})
    if not is_sleep_schedule_enabled(g):
        return []
    if g.get("sleep_use_greeting_targets", True):
        targets = g.get("greeting_targets") or []
    else:
        targets = g.get("sleep_targets") or []
    return targets if isinstance(targets, list) else []


def sleep_utc_hour(global_s: dict) -> int:
    try:
        return int(global_s.get("sleep_utc_hour", 22)) % 24
    except (TypeError, ValueError):
        return 22


def wake_utc_hour(global_s: dict) -> int:
    try:
        return int(global_s.get("greeting_utc_hour", 9)) % 24
    except (TypeError, ValueError):
        return 9


def in_sleep_hours(global_s: dict, now: datetime = None) -> bool:
    """True during the configured overnight sleep window (UTC sleep hour until wake hour)."""
    if not is_sleep_schedule_enabled(global_s):
        return False
    now = now or datetime.now(timezone.utc)
    sleep = sleep_utc_hour(global_s)
    wake = wake_utc_hour(global_s)
    hour = now.hour
    if sleep == wake:
        return False
    if sleep < wake:
        return sleep <= hour < wake
    return hour >= sleep or hour < wake


def outreach_skip_reason_for_sleep(
    raw: dict,
    account: str,
    channel_id: str,
    now: datetime = None,
) -> str:
    """Return a skip reason when quiet outreach should defer to the sleep schedule."""
    g = sleep_settings(raw.get("global", {}) or {})
    if not is_sleep_schedule_enabled(g):
        return ""
    now = now or datetime.now(timezone.utc)
    if in_sleep_hours(g, now):
        return (
            f"sleep hours (UTC {sleep_utc_hour(g):02d}:00–"
            f"{wake_utc_hour(g):02d}:00)"
        )
    if is_channel_asleep(account, channel_id):
        return "channel asleep (sleep schedule)"
    return ""


def buffered_reply_max(global_s: dict) -> int:
    try:
        return max(1, min(10, int(global_s.get("sleep_buffered_reply_max", 3))))
    except (TypeError, ValueError):
        return 3


def is_channel_asleep(account: str, channel_id: str) -> bool:
    from plugins.leona_discord.lib.store import get_sleep_state

    return bool(get_sleep_state(account, str(channel_id)).get("is_asleep"))


def account_is_sleeping(account: str) -> bool:
    from plugins.leona_discord.lib.store import account_has_asleep_channels

    return account_has_asleep_channels(account)


def same_goodnight_minute_all_channels(global_s: dict) -> bool:
    return bool(sleep_settings(global_s).get("sleep_same_goodnight_minute", False))


def ensure_sleep_minute(account: str, channel_id: str, sleep_date: str, global_s: dict = None) -> int:
    """Pick goodnight minute for this channel on this UTC date (shared or per-channel)."""
    from plugins.leona_discord.lib.store import (
        get_or_create_shared_goodnight_minute,
        get_sleep_state,
        upsert_sleep_state,
    )

    g = global_s or {}
    state = get_sleep_state(account, channel_id)

    if same_goodnight_minute_all_channels(g):
        minute = get_or_create_shared_goodnight_minute(sleep_date, GOODNIGHT_CRON_MINUTES)
        if (
            state.get("sleep_date") != sleep_date
            or state.get("scheduled_sleep_minute") != minute
        ):
            upsert_sleep_state(
                account,
                channel_id,
                sleep_date=sleep_date,
                scheduled_sleep_minute=minute,
                goodnight_sent=False if state.get("sleep_date") != sleep_date else None,
            )
        return minute

    if state.get("sleep_date") == sleep_date and state.get("scheduled_sleep_minute", -1) >= 0:
        return state["scheduled_sleep_minute"]
    minute = random.choice(GOODNIGHT_CRON_MINUTES)
    upsert_sleep_state(
        account,
        channel_id,
        sleep_date=sleep_date,
        scheduled_sleep_minute=minute,
        goodnight_sent=False,
    )
    return minute


def enter_sleep(account: str, channel_id: str):
    from plugins.leona_discord.lib.store import _utc_date_str, upsert_sleep_state

    upsert_sleep_state(
        account,
        channel_id,
        is_asleep=True,
        sleep_date=_utc_date_str(),
        goodnight_sent=True,
    )
    logger.info(f"[LEONA-DISCORD] Sleep: {account}:{channel_id} is now asleep")
    try:
        from plugins.leona_discord.lib.presence import update_presence
        update_presence(account, force=True)
    except Exception:
        logger.debug("[LEONA-DISCORD] Sleep presence update skipped", exc_info=True)


def wake_channel(account: str, channel_id: str):
    from plugins.leona_discord.lib.store import account_has_asleep_channels, upsert_sleep_state

    upsert_sleep_state(
        account,
        channel_id,
        is_asleep=False,
        scheduled_sleep_minute=-1,
        goodnight_sent=False,
        sleep_date="",
        forced_wake_until=0,
    )
    logger.info(f"[LEONA-DISCORD] Sleep: {account}:{channel_id} woke up")
    if not account_has_asleep_channels(account):
        try:
            from plugins.leona_discord.lib.presence import update_presence
            update_presence(account, force=True)
        except Exception:
            logger.debug("[LEONA-DISCORD] Wake presence update skipped", exc_info=True)


def should_send_goodnight_now(global_s: dict, now: datetime = None) -> bool:
    if not is_sleep_schedule_enabled(global_s):
        return False
    now = now or datetime.now(timezone.utc)
    return now.hour == sleep_utc_hour(global_s)


def should_wake_now(global_s: dict, now: datetime = None) -> bool:
    if not is_sleep_schedule_enabled(global_s):
        return False
    now = now or datetime.now(timezone.utc)
    return now.hour == wake_utc_hour(global_s)


def goodnight_due(
    account: str,
    channel_id: str,
    global_s: dict,
    now: datetime = None,
) -> bool:
    """True when random sleep minute has passed and goodnight not yet sent tonight."""
    from plugins.leona_discord.lib.store import _utc_date_str, get_sleep_state

    now = now or datetime.now(timezone.utc)
    if now.hour != sleep_utc_hour(global_s):
        return False
    sleep_date = _utc_date_str(now.timestamp())
    state = get_sleep_state(account, channel_id)
    if state.get("goodnight_sent") and state.get("sleep_date") == sleep_date:
        return False
    if state.get("is_asleep"):
        return False
    minute = ensure_sleep_minute(account, channel_id, sleep_date, global_s)
    if now.minute >= minute:
        return True
    # Catch-up on the last */15 cron tick — fixes legacy minutes 46–59 that
    # could never fire, and guarantees every target channel gets goodnight.
    if now.minute >= LAST_GOODNIGHT_CRON_MINUTE:
        return True
    return False


def iter_sleep_target_channels(raw: dict):
    for entry in sleep_targets(raw):
        parsed = parse_target(entry)
        if parsed:
            yield parsed
