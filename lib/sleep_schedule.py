"""Sleep schedule: goodnight, dormant mode, and buffered @mentions until wake."""

import logging
import random
from datetime import datetime, timezone

from plugins.leona_discord.lib.schedule_utils import parse_target

logger = logging.getLogger(__name__)


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


def ensure_sleep_minute(account: str, channel_id: str, sleep_date: str) -> int:
    """Pick a random minute (0–59) for goodnight on this UTC date."""
    from plugins.leona_discord.lib.store import get_sleep_state, upsert_sleep_state

    state = get_sleep_state(account, channel_id)
    if state.get("sleep_date") == sleep_date and state.get("scheduled_sleep_minute", -1) >= 0:
        return state["scheduled_sleep_minute"]
    minute = random.randint(0, 59)
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


def wake_channel(account: str, channel_id: str):
    from plugins.leona_discord.lib.store import upsert_sleep_state

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
    minute = ensure_sleep_minute(account, channel_id, sleep_date)
    return now.minute >= minute


def iter_sleep_target_channels(raw: dict):
    for entry in sleep_targets(raw):
        parsed = parse_target(entry)
        if parsed:
            yield parsed
