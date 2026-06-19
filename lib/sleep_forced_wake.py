"""Forced wake: enough @mentions during sleep temporarily rouses the bot."""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

_JUST_WOKEN_HINT = (
    "[You were asleep for the night but repeated @mentions woke you up. "
    "Reply helpfully, but briefly complain or grumble that people woke you — "
    "you're tired and will go back to sleep soon.]"
)

_STILL_AWAKE_HINT = (
    "[You were woken up earlier and are still awake for a little while. "
    "You may grumble lightly, but answer the message.]"
)

_FORCED_WAKE_FALLBACK = (
    "Ugh, seriously? You woke me up… what do you want? 😴"
)


def forced_wake_fallback_text(global_s: dict = None) -> str:
    g = global_s or {}
    return str(
        g.get("sleep_forced_wake_fallback") or _FORCED_WAKE_FALLBACK
    ).strip()


def is_forced_wake_event(event_data: dict) -> bool:
    if not event_data:
        return False
    return str(event_data.get("sleep_forced_wake", "")).lower() in ("true", "1", "yes")


def is_forced_wake_enabled(global_s: dict) -> bool:
    g = global_s or {}
    return bool(g.get("sleep_schedule_enabled")) and bool(g.get("sleep_forced_wake_enabled", False))


def mention_threshold(global_s: dict) -> int:
    try:
        return max(2, min(20, int(global_s.get("sleep_forced_wake_mention_count", 3))))
    except (TypeError, ValueError):
        return 3


def window_minutes(global_s: dict) -> int:
    try:
        return max(1, min(120, int(global_s.get("sleep_forced_wake_window_minutes", 15))))
    except (TypeError, ValueError):
        return 15


def duration_minutes(global_s: dict) -> int:
    try:
        return max(5, min(180, int(global_s.get("sleep_forced_wake_duration_minutes", 30))))
    except (TypeError, ValueError):
        return 30


def build_forced_wake_hint(*, just_woke: bool) -> str:
    return _JUST_WOKEN_HINT if just_woke else _STILL_AWAKE_HINT


def is_forced_awake(account: str, channel_id: str) -> bool:
    from plugins.leona_discord.lib.store import get_sleep_state

    until = float(get_sleep_state(account, str(channel_id)).get("forced_wake_until") or 0)
    return until > time.time()


def expire_forced_wake_if_needed(account: str, channel_id: str) -> bool:
    """Clear expired forced wake. Returns True if wake was active and just expired."""
    from plugins.leona_discord.lib.store import get_sleep_state, upsert_sleep_state

    state = get_sleep_state(account, str(channel_id))
    until = float(state.get("forced_wake_until") or 0)
    if until <= 0:
        return False
    if until > time.time():
        return False
    upsert_sleep_state(account, str(channel_id), forced_wake_until=0)
    logger.info(f"[LEONA-DISCORD] Forced wake expired for {account}:{channel_id}")
    return True


def enter_forced_wake(account: str, channel_id: str, global_s: dict):
    from plugins.leona_discord.lib.store import upsert_sleep_state

    mins = duration_minutes(global_s)
    until = time.time() + mins * 60
    upsert_sleep_state(account, str(channel_id), forced_wake_until=until)
    logger.info(
        f"[LEONA-DISCORD] Forced wake for {account}:{channel_id} "
        f"({mins} min, until {until:.0f})"
    )


def clear_forced_wake(account: str, channel_id: str):
    from plugins.leona_discord.lib.store import upsert_sleep_state

    upsert_sleep_state(account, str(channel_id), forced_wake_until=0)


def should_block_sleep_reply(account: str, channel_id: str) -> bool:
    """True when the channel is asleep and not temporarily forced awake."""
    from plugins.leona_discord.lib.sleep_schedule import is_channel_asleep

    if not is_channel_asleep(account, channel_id):
        return False
    expire_forced_wake_if_needed(account, channel_id)
    return not is_forced_awake(account, channel_id)


def handle_sleep_mention(account: str, channel_id: str, global_s: dict) -> Optional[str]:
    """After an @mention is buffered, decide whether to reply now with a wake hint.

    Returns hint text to prefix the user message, or None to hold until morning wake.
    """
    if not is_forced_wake_enabled(global_s):
        return None

    expire_forced_wake_if_needed(account, channel_id)

    if is_forced_awake(account, channel_id):
        return build_forced_wake_hint(just_woke=False)

    from plugins.leona_discord.lib.store import count_sleep_mentions_in_window

    window = window_minutes(global_s)
    threshold = mention_threshold(global_s)
    count = count_sleep_mentions_in_window(account, channel_id, window)
    if count < threshold:
        return None

    enter_forced_wake(account, channel_id, global_s)
    return build_forced_wake_hint(just_woke=True)


def wrap_forced_wake_content(content: str, hint: str) -> str:
    body = (content or "").strip()
    if not hint:
        return body
    return f"{hint}\n\n{body}" if body else hint
