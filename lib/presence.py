"""Quiet hours, scheduled presence, and ambient life helpers."""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone

from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)

PRESENCE_ACTIVITY_PRESETS = [
    {"id": "clear", "category": "none", "label": "No activity (cleared)", "value": ""},
    {"id": "listening_chat", "category": "listening", "label": "Listening to chat", "value": "listening: chat"},
    {"id": "listening_lofi", "category": "listening", "label": "Listening to lo-fi", "value": "listening: lo-fi beats"},
    {"id": "listening_podcast", "category": "listening", "label": "Listening to a podcast", "value": "listening: a podcast"},
    {"id": "listening_rain", "category": "listening", "label": "Listening to rain", "value": "listening: rain"},
    {"id": "watching_server", "category": "watching", "label": "Watching the server", "value": "watching: the server"},
    {"id": "watching_memes", "category": "watching", "label": "Watching memes roll in", "value": "watching: memes roll in"},
    {"id": "watching_notifications", "category": "watching", "label": "Watching notifications", "value": "watching: notifications"},
    {"id": "watching_sky", "category": "watching", "label": "Watching the sky", "value": "watching: the sky"},
    {"id": "playing_ideas", "category": "playing", "label": "Playing with ideas", "value": "playing: with ideas"},
    {"id": "playing_games", "category": "playing", "label": "Playing games", "value": "playing: games"},
    {"id": "playing_dnd", "category": "playing", "label": "Playing D&D", "value": "playing: D&D"},
    {"id": "playing_code", "category": "playing", "label": "Playing with code", "value": "playing: with code"},
    {"id": "competing_trivia", "category": "competing", "label": "Competing in trivia", "value": "competing: in trivia"},
    {"id": "competing_debate", "category": "competing", "label": "Competing in debates", "value": "competing: in a debate"},
    {"id": "competing_chess", "category": "competing", "label": "Competing in chess", "value": "competing: in chess"},
    {"id": "custom_alone_time", "category": "custom", "label": "Enjoying alone time", "value": "enjoying alone time"},
    {"id": "custom_friday", "category": "custom", "label": "Looking forward to Friday", "value": "looking forward to Friday"},
    {"id": "custom_chill", "category": "custom", "label": "Having a chill day", "value": "having a chill day"},
    {"id": "custom_vibing", "category": "custom", "label": "Just vibing", "value": "just vibing"},
    {"id": "custom_coffee", "category": "custom", "label": "Waiting for coffee to kick in", "value": "waiting for coffee to kick in"},
    {"id": "custom_good_mood", "category": "custom", "label": "In a good mood", "value": "in a good mood"},
    {"id": "custom_social_battery", "category": "custom", "label": "Low social battery", "value": "low social battery"},
    {"id": "custom_buffering", "category": "custom", "label": "Brain buffering", "value": "brain buffering"},
    {"id": "custom_snacks", "category": "custom", "label": "Thinking about snacks", "value": "thinking about snacks"},
    {"id": "custom_own_world", "category": "custom", "label": "Off in my own world", "value": "off in my own world"},
    {"id": "custom_might_return", "category": "custom", "label": "Might be back later", "value": "might be back later"},
    {"id": "daydreaming", "category": "custom", "label": "Daydreaming", "value": "daydreaming"},
]

DEFAULT_ENABLED_PRESET_IDS = [
    "clear",
    "listening_chat",
    "watching_server",
    "playing_ideas",
    "daydreaming",
]

_PRESET_BY_ID = {p["id"]: p for p in PRESENCE_ACTIVITY_PRESETS}
_PRESET_BY_VALUE = {p["value"]: p["id"] for p in PRESENCE_ACTIVITY_PRESETS}

_LEGACY_VALUE_ALIASES = {
    "listening to chat": "listening_chat",
    "watching the server": "watching_server",
    "daydreaming": "daydreaming",
}


def _preset_id_for_activity_value(value: str) -> str | None:
    preset_id = _PRESET_BY_VALUE.get(value)
    if preset_id:
        return preset_id
    return _LEGACY_VALUE_ALIASES.get(value)

_ACTIVITY_PREFIXES = {
    "custom": "custom",
    "playing": "playing",
    "listening": "listening",
    "watching": "watching",
    "competing": "competing",
}


def valid_preset_ids() -> set[str]:
    return set(_PRESET_BY_ID.keys())


def presence_preset_catalog() -> list[dict]:
    return list(PRESENCE_ACTIVITY_PRESETS)


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


def parse_presence_activities(value) -> list:
    """Parse custom activity lines; empty markers clear the activity."""
    if value is None:
        return []
    if isinstance(value, list):
        lines = [str(v) for v in value]
    else:
        lines = str(value).splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped in ("", "-", "(none)", "(clear)"):
            result.append("")
        elif stripped:
            result.append(stripped[:128])
    return result[:50]


def _normalize_enabled_preset_ids(value) -> list[str]:
    valid = valid_preset_ids()
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip() in valid][:50]


def resolve_presence_selection(settings: dict) -> tuple[list[str], list[str]]:
    """Return (enabled_preset_ids, custom_activities) with legacy migration."""
    if "presence_activity_presets" in settings:
        enabled = _normalize_enabled_preset_ids(settings.get("presence_activity_presets"))
        custom = parse_presence_activities(settings.get("presence_activities_custom"))
        return enabled, custom

    legacy = settings.get("presence_activities")
    if legacy:
        enabled = []
        custom = []
        for item in parse_presence_activities(legacy):
            preset_id = _preset_id_for_activity_value(item)
            if preset_id:
                if preset_id not in enabled:
                    enabled.append(preset_id)
            else:
                custom.append(item)
        if not enabled:
            enabled = list(DEFAULT_ENABLED_PRESET_IDS)
        return enabled, custom

    return list(DEFAULT_ENABLED_PRESET_IDS), []


def presence_activity_pool(settings: dict) -> list:
    enabled_ids, custom = resolve_presence_selection(settings)
    pool = []
    for preset_id in enabled_ids:
        preset = _PRESET_BY_ID.get(preset_id)
        if preset:
            pool.append(preset["value"])
    pool.extend(custom)
    if not pool:
        pool = [_PRESET_BY_ID[pid]["value"] for pid in DEFAULT_ENABLED_PRESET_IDS if pid in _PRESET_BY_ID]
    return pool


def presence_cycle_interval_seconds(settings: dict) -> float:
    try:
        minutes = int(settings.get("presence_cycle_interval_minutes", 10))
    except (TypeError, ValueError):
        minutes = 10
    minutes = max(5, min(180, minutes))
    return float(minutes * 60)


def parse_activity_entry(text: str):
    """Return (activity_type_name, activity_name) or (None, None) when cleared."""
    if not text:
        return None, None
    lower = text.lower()
    for prefix, kind in _ACTIVITY_PREFIXES.items():
        needle = f"{prefix}:"
        if lower.startswith(needle):
            name = text[len(needle):].strip()
            return kind, name[:128] if name else None
    # Plain text → Discord custom status (not "Listening to …")
    return "custom", text[:128]


def pick_awake_presence(settings: dict) -> tuple[str, str | None]:
    """Pick status and activity text while the bot is awake."""
    activities = presence_activity_pool(settings)
    activity_text = random.choice(activities) if activities else ""
    if not activity_text:
        return "online", None
    return "online", activity_text


# ---------------------------------------------------------------------------
# Presence cycling — set bot status based on time of day
# ---------------------------------------------------------------------------

_last_presence_update = 0.0


def update_presence(account_name: str):
    """Cycle the bot's Discord status based on time of day.

    Sleeping → idle + "sleeping".  Quiet hours → idle, no activity.
    Awake + cycling enabled → random activity from settings.
    Awake + cycling disabled → online, no activity.
  """
    global _last_presence_update
    now = time.time()

    from plugins.leona_discord.lib.settings import get_effective_settings
    settings = get_effective_settings()
    interval = presence_cycle_interval_seconds(settings)
    if now - _last_presence_update < interval:
        return
    _last_presence_update = now

    if not state._loop or not state._loop.is_running():
        return

    quiet = in_quiet_hours(settings)

    from plugins.leona_discord.lib.sleep_schedule import account_is_sleeping
    if account_is_sleeping(account_name):
        status_str, activity_text = "idle", "custom: sleeping"
    elif quiet:
        status_str, activity_text = "idle", None
    elif settings.get("presence_cycling_enabled", True):
        status_str, activity_text = pick_awake_presence(settings)
    else:
        status_str, activity_text = "online", None

    asyncio.run_coroutine_threadsafe(
        _set_presence(account_name, status_str, activity_text),
        state._loop,
    )


async def _set_presence(account_name: str, status_str: str, activity_text: str | None):
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
            kind, name = parse_activity_entry(activity_text)
            if kind == "playing":
                activity = discord.Game(name=name or activity_text)
            elif kind == "watching":
                activity = discord.Activity(type=discord.ActivityType.watching, name=name or activity_text)
            elif kind == "competing":
                activity = discord.Activity(type=discord.ActivityType.competing, name=name or activity_text)
            elif kind == "custom":
                activity = discord.CustomActivity(name=name or activity_text)
            else:
                activity = discord.Activity(
                    type=discord.ActivityType.listening,
                    name=name or activity_text,
                )

        await client.change_presence(status=status, activity=activity)
        label = activity_text or "(cleared)"
        logger.debug(f"[DISCORD] Presence updated for {account_name}: {status_str} — {label}")
    except Exception as e:
        logger.debug(f"[DISCORD] Presence update failed for {account_name}: {e}")
