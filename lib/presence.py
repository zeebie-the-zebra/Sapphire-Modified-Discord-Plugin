"""Quiet hours, scheduled presence, and ambient life helpers."""

import asyncio
import json
import logging
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from plugins.leona_discord.lib import state
from plugins.leona_discord.lib.think_tags import strip_think_tags

logger = logging.getLogger(__name__)

_DEFAULT_PRESENCE_ACTIVITY_PRESETS = [
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

_DEFAULT_SLEEP_ACTIVITY_TEXTS = (
    "custom: sleeping",
    "custom: dreaming",
    "custom: catching Z's",
    "custom: do not disturb",
    "custom: tucked in for the night",
)

_VALID_PRESET_CATEGORIES = {
    "none", "custom", "playing", "listening", "watching", "competing",
    # Grouped in awake.json for UI; Discord renders these as custom statuses.
    "studying", "working", "eating",
}


def _status_config_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "statuses"


def _load_json_file(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _normalize_presence_preset_entry(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    preset_id = str(item.get("id") or "").strip()
    category = str(item.get("category") or "").strip().lower()
    label = str(item.get("label") or "").strip()
    value = str(item.get("value") or "")
    if not preset_id or category not in _VALID_PRESET_CATEGORIES or not label:
        return None
    return {
        "id": preset_id[:50],
        "category": category,
        "label": label[:128],
        "value": value[:128],
    }


def _load_presence_activity_presets() -> list[dict]:
    path = _status_config_dir() / "awake.json"
    try:
        data = _load_json_file(path)
        if not isinstance(data, list):
            raise ValueError("awake.json must contain a list")
        presets = []
        seen_ids = set()
        for index, item in enumerate(data):
            normalized = _normalize_presence_preset_entry(item)
            if not normalized:
                logger.warning(
                    f"[DISCORD] Skipping invalid awake.json entry #{index + 1}: {item!r}"
                )
                continue
            if normalized["id"] in seen_ids:
                continue
            presets.append(normalized)
            seen_ids.add(normalized["id"])
        if not presets:
            raise ValueError("awake.json must contain at least one preset")
        return presets
    except FileNotFoundError:
        return list(_DEFAULT_PRESENCE_ACTIVITY_PRESETS)
    except Exception as e:
        logger.warning(f"[DISCORD] Failed to load awake statuses from {path}: {e}")
        return list(_DEFAULT_PRESENCE_ACTIVITY_PRESETS)


def _load_sleep_activity_texts() -> tuple[str, ...]:
    path = _status_config_dir() / "sleep.json"
    try:
        data = _load_json_file(path)
        if not isinstance(data, list):
            raise ValueError("sleep.json must contain a list")
        values = []
        for index, item in enumerate(data):
            if not isinstance(item, str):
                logger.warning(
                    f"[DISCORD] Skipping invalid sleep.json entry #{index + 1}: {item!r}"
                )
                continue
            text = item.strip()[:128]
            if not text:
                logger.warning(
                    f"[DISCORD] Skipping empty sleep.json entry #{index + 1}"
                )
                continue
            values.append(text)
        if not values:
            raise ValueError("sleep.json must contain at least one status")
        return tuple(values)
    except FileNotFoundError:
        return _DEFAULT_SLEEP_ACTIVITY_TEXTS
    except Exception as e:
        logger.warning(f"[DISCORD] Failed to load sleep statuses from {path}: {e}")
        return _DEFAULT_SLEEP_ACTIVITY_TEXTS


PRESENCE_ACTIVITY_PRESETS = _load_presence_activity_presets()
SLEEP_ACTIVITY_TEXTS = _load_sleep_activity_texts()

_PRESET_BY_ID = {p["id"]: p for p in PRESENCE_ACTIVITY_PRESETS}
_PRESET_BY_VALUE = {p["value"]: p["id"] for p in PRESENCE_ACTIVITY_PRESETS}


def _reload_presence_status_data() -> None:
    """Reload awake/sleep JSON from disk (picks up edits without a full restart)."""
    global PRESENCE_ACTIVITY_PRESETS, SLEEP_ACTIVITY_TEXTS, _PRESET_BY_ID, _PRESET_BY_VALUE
    PRESENCE_ACTIVITY_PRESETS = _load_presence_activity_presets()
    SLEEP_ACTIVITY_TEXTS = _load_sleep_activity_texts()
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

_LLM_STATUS_MAX_CHARS = 60
_THINKING_TAIL_MARKERS = (
    "</think>",
    "</thinking>",
    "</seed:think>",
    "</seed:cot_budget_reflect>",
)
_PRESENCE_META_FRAGMENTS = (
    "user wants",
    "discord custom",
    "2-6 word",
    "inspired by",
    "the chat",
    "reply with",
    "no quotes",
    "custom status",
    "the model",
    "i should",
    "i need to",
    "let me",
)


def _extract_presence_after_thinking(text: str) -> str:
    """Recover visible text after a closed thinking block when strip removed everything."""
    lowered = text.lower()
    best = ""
    for marker in _THINKING_TAIL_MARKERS:
        idx = lowered.rfind(marker.lower())
        if idx >= 0:
            tail = text[idx + len(marker):].strip()
            if tail and (not best or len(tail) < len(best)):
                best = tail
    return best


def _looks_like_presence_meta(text: str) -> bool:
    lower = (text or "").lower()
    return any(fragment in lower for fragment in _PRESENCE_META_FRAGMENTS)


def _salvage_presence_from_thinking(raw: str) -> str:
    """Best-effort extraction when the model only returned reasoning text."""
    if not raw or not raw.strip():
        return ""

    for match in re.finditer(r'"([^"]{2,60})"', raw):
        candidate = sanitize_generated_presence_status(match.group(1))
        if candidate and not _looks_like_presence_meta(candidate):
            return candidate

    for match in re.finditer(r"'([^']{2,60})'", raw):
        candidate = sanitize_generated_presence_status(match.group(1))
        if candidate and not _looks_like_presence_meta(candidate):
            return candidate

    body = re.sub(r"(?is)<think>\s*", "", raw, count=1)
    body = re.sub(r"(?is)<thinking>\s*", "", body, count=1)
    for part in re.split(r"[\n.!?]+", body):
        candidate = sanitize_generated_presence_status(part)
        if not candidate or _looks_like_presence_meta(candidate):
            continue
        words = candidate.split()
        if 2 <= len(words) <= 8:
            return candidate
    return ""


def _presence_llm_gen_params(gen_params: dict, *, max_tokens: int) -> dict:
    params = dict(gen_params)
    params["max_tokens"] = max_tokens
    params["disable_thinking"] = True
    extra_body = dict(params.get("extra_body") or {})
    chat_template_kwargs = dict(extra_body.get("chat_template_kwargs") or {})
    chat_template_kwargs["enable_thinking"] = False
    extra_body["chat_template_kwargs"] = chat_template_kwargs
    if "minimax" in str(params.get("model") or "").lower():
        extra_body.setdefault("thinking", {"type": "disabled"})
    params["extra_body"] = extra_body
    return params


def valid_preset_ids() -> set[str]:
    return set(_PRESET_BY_ID.keys())


def presence_preset_catalog() -> list[dict]:
    _reload_presence_status_data()
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
    return [str(item).strip() for item in value if str(item).strip() in valid]


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


def sanitize_generated_presence_status(text: str) -> str:
    raw = text or ""
    text = strip_think_tags(raw)
    if not text.strip():
        text = _extract_presence_after_thinking(raw)
    text = text.replace("\r", "\n")
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped:
            text = stripped
            break
    else:
        return ""

    if text.startswith('"') and text.endswith('"') and len(text) >= 2:
        text = text[1:-1].strip()
    lower = text.lower()
    for prefix in ("status:", "custom:", "activity:"):
        if lower.startswith(prefix):
            text = text[len(prefix):].strip()
            lower = text.lower()
    text = " ".join(text.split())
    if len(text) > _LLM_STATUS_MAX_CHARS:
        text = text[: _LLM_STATUS_MAX_CHARS - 1].rstrip() + "…"
    return text[:128]


def _parse_presence_llm_raw(llm_response) -> str:
    if llm_response and getattr(llm_response, "content", None):
        return llm_response.content or ""
    return ""


def generate_llm_presence_status(account_name: str, settings: dict) -> str:
    try:
        from core.api_fastapi import get_system
        from core.chat.llm_providers import get_generation_params
        from plugins.leona_discord.lib.proactive_llm import _providers_config
        from plugins.leona_discord.lib.history import format_proactive_history, get_history_snapshot
        from plugins.leona_discord.lib.store import get_most_recent_channel_for_account
    except Exception as e:
        logger.debug(f"[DISCORD] Presence LLM unavailable for {account_name}: {e}")
        return ""

    guild_id, channel_id = get_most_recent_channel_for_account(account_name)
    if not channel_id:
        return ""

    system = get_system()
    if not system or not getattr(system, "llm_chat", None):
        return ""

    recent = format_proactive_history(
        get_history_snapshot(state.channel_key(account_name, channel_id)),
        guild_id or "",
        account_name,
    )
    if not recent:
        return ""

    prompt = (
        "Write one 2-6 word Discord custom status inspired by this chat.\n"
        "Output only the status phrase.\n\n"
        "Chat:\n" + "\n".join(recent[-6:])
    )
    messages = [
        {
            "role": "system",
            "content": "You write ultra-short Discord custom statuses. Never explain or reason aloud.",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        llm = system.llm_chat
        provider_key, provider, model_override = llm._select_provider()
        effective_model = model_override or provider.model
        base_gen = get_generation_params(provider_key, effective_model, _providers_config())
        if model_override:
            base_gen["model"] = model_override

        last_raw = ""
        for max_tokens in (64, 512):
            gen_params = _presence_llm_gen_params(base_gen, max_tokens=max_tokens)
            llm_response = llm.tool_engine.call_llm_with_metrics(
                provider,
                messages,
                gen_params,
                tools=None,
            )
            raw = _parse_presence_llm_raw(llm_response)
            last_raw = raw or last_raw
            cleaned = sanitize_generated_presence_status(raw)
            if cleaned:
                return cleaned
            salvaged = _salvage_presence_from_thinking(raw)
            if salvaged:
                return salvaged

        if last_raw and last_raw.strip():
            preview = last_raw.strip().replace("\n", " ")[:120]
            logger.warning(
                f"[DISCORD] Presence LLM for {account_name} produced unusable output "
                f"({len(last_raw)} chars, finish may be length or thinking-only): {preview!r}"
            )
        return ""
    except Exception as e:
        logger.warning(f"[DISCORD] Presence LLM failed for {account_name}: {e}")
        return ""


def pick_awake_presence(settings: dict, *, account_name: str = "") -> tuple[str, str | None]:
    """Pick status and activity text while the bot is awake."""
    try:
        llm_chance = max(0, min(100, int(settings.get("presence_llm_status_chance", 0))))
    except (TypeError, ValueError):
        llm_chance = 0
    if account_name and llm_chance > 0 and random.randint(1, 100) <= llm_chance:
        llm_status = generate_llm_presence_status(account_name, settings)
        if llm_status:
            return "online", llm_status

    activities = presence_activity_pool(settings)
    activity_text = random.choice(activities) if activities else ""
    if not activity_text:
        return "online", None
    return "online", activity_text


def pick_sleep_presence() -> tuple[str, str]:
    """Pick idle status and a sleep-related custom activity."""
    _reload_presence_status_data()
    return "idle", random.choice(SLEEP_ACTIVITY_TEXTS)


def resolve_presence_target(account_name: str, settings: dict) -> tuple[str, str, str | None]:
    """Return (mode, status_str, activity_text). mode is sleep, quiet, or awake."""
    from plugins.leona_discord.lib.sleep_schedule import account_is_sleeping

    if account_is_sleeping(account_name):
        status_str, activity_text = pick_sleep_presence()
        return "sleep", status_str, activity_text
    if in_quiet_hours(settings):
        return "quiet", "idle", None
    if settings.get("presence_cycling_enabled", True):
        status_str, activity_text = pick_awake_presence(settings, account_name=account_name)
        return "awake", status_str, activity_text
    return "awake", "online", None


# ---------------------------------------------------------------------------
# Presence cycling — set bot status based on time of day
# ---------------------------------------------------------------------------

_last_presence_update: dict[str, float] = {}
_last_presence_mode: dict[str, str] = {}


def _should_skip_presence_update(
    account_name: str,
    mode: str,
    now: float,
    interval: float,
    *,
    force: bool,
) -> bool:
    """Awake statuses rotate on an interval; sleep/quiet apply once until the mode changes."""
    if force:
        return False
    prev_mode = _last_presence_mode.get(account_name)
    if mode in ("sleep", "quiet"):
        return prev_mode == mode
    if mode == "awake":
        return now - _last_presence_update.get(account_name, 0.0) < interval
    return False


def apply_presence_activity(
    account_name: str,
    activity_text: str | None,
    *,
    status_str: str = "online",
) -> bool:
    """Apply a specific Discord presence immediately."""
    if not state._loop or not state._loop.is_running():
        return False
    _last_presence_update[account_name] = time.time()
    _last_presence_mode[account_name] = "awake"
    asyncio.run_coroutine_threadsafe(
        _set_presence(account_name, status_str, activity_text),
        state._loop,
    )
    return True


def update_presence(account_name: str, *, force: bool = False):
    """Cycle the bot's Discord status based on time of day.

    Sleeping → idle + sleep-related custom status (set once, no rotation).
    Quiet hours → idle, no activity.
    Awake + cycling enabled → random activity from settings on an interval.
    Awake + cycling disabled → online, no activity.
    """
    now = time.time()

    from plugins.leona_discord.lib.settings import get_effective_settings
    settings = get_effective_settings()
    interval = presence_cycle_interval_seconds(settings)
    mode, status_str, activity_text = resolve_presence_target(account_name, settings)

    if _should_skip_presence_update(account_name, mode, now, interval, force=force):
        return

    if not state._loop or not state._loop.is_running():
        return

    _last_presence_update[account_name] = now
    _last_presence_mode[account_name] = mode

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
