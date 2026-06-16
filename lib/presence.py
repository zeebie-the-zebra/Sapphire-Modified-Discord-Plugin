"""Quiet hours, scheduled presence, and ambient life helpers."""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone

from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)

# Activity status options — rotated occasionally to look alive
_ACTIVITIES = [
    ("online", None),               # default online, no activity
    ("online", "listening to chat"),
    ("online", None),
    ("online", None),
    ("idle", None),                  # idle during quiet hours
]


def in_quiet_hours(settings: dict) -> bool:
    if not settings.get("quiet_hours_enabled", False):
        return False
    try:
        start = int(settings.get("quiet_hours_start", 22)) % 24
        end = int(settings.get("quiet_hours_end", 8)) % 24
    except (TypeError, ValueError):
        return False
    hour = datetime.now(timezone.utc).hour
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def apply_quiet_hours(settings: dict) -> dict:
    """Return a copy with reply chances zeroed during quiet hours."""
    if not in_quiet_hours(settings):
        return settings
    mode = settings.get("quiet_hours_mode", "reactions_only")
    out = dict(settings)
    out["human_response_chance"] = 0
    out["bot_response_chance"] = 0
    out["name_match_enabled"] = False
    out["keyword_triggers"] = []
    if mode == "silent":
        out["reactions_enabled"] = False
    return out


# ---------------------------------------------------------------------------
# Presence cycling — set bot status based on time of day
# ---------------------------------------------------------------------------

_last_presence_update = 0.0
_PRESENCE_INTERVAL = 600  # update every 10 minutes


def update_presence(account_name: str):
    """Cycle the bot's Discord status based on time of day.

    During quiet hours → idle.  Otherwise → online with occasional
    activity text.  Called periodically from the daemon loop.
    """
    global _last_presence_update
    now = time.time()
    if now - _last_presence_update < _PRESENCE_INTERVAL:
        return
    _last_presence_update = now

    if not state._loop or not state._loop.is_running():
        return

    # Decide status based on quiet hours
    from plugins.leona_discord.lib.settings import get_effective_settings
    settings = get_effective_settings()
    quiet = in_quiet_hours(settings)

    from plugins.leona_discord.lib.sleep_schedule import account_is_sleeping
    if account_is_sleeping(account_name):
        status_str, activity_text = "idle", "sleeping"
    elif quiet:
        status_str, activity_text = "idle", None
    else:
        status_str, activity_text = random.choice(_ACTIVITIES[:4])  # skip idle

    asyncio.run_coroutine_threadsafe(
        _set_presence(account_name, status_str, activity_text),
        state._loop,
    )


async def _set_presence(account_name: str, status_str: str, activity_text: str):
    import discord

    client = state._clients.get(account_name)
    if not client or not client.is_ready():
        return

    try:
        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        status = status_map.get(status_str, discord.Status.online)

        activity = None
        if activity_text:
            activity = discord.Activity(type=discord.ActivityType.listening, name=activity_text)

        await client.change_presence(status=status, activity=activity)
        logger.debug(f"[DISCORD] Presence updated for {account_name}: {status_str}")
    except Exception as e:
        logger.debug(f"[DISCORD] Presence update failed for {account_name}: {e}")
