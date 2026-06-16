"""Plugin settings: defaults, merge logic, and live reads from plugin state."""

from plugins.leona_discord.emojis import DISCORD_EMOJI
from plugins.leona_discord.lib.constants import BATCH_DELAY_DEFAULT
from plugins.leona_discord.lib.presets import PERSONALITY_PRESETS, VALID_PRESETS

SETTING_DEFAULTS = {
    "human_response_chance": 15,
    "cooldown_seconds": 120,
    "cooldown_scope": "per_channel",
    "name_match_enabled": True,
    "name_match_case_sensitive": False,
    "bot_response_chance": 15,
    "reactions_enabled": True,
    "reaction_chance": 50,
    "reaction_cooldown_seconds": 30,
    "react_to_trigger": True,
    "react_to_any": False,
    "allowed_emojis": DISCORD_EMOJI,
    "reaction_backend": "vader",
    "image_enabled": False,
    "image_model_provider": "",
    "image_model_name": "",
    "image_model_max_tokens": 1024,
    "append_to_user_message_enabled": False,
    "append_to_user_message": "",
    "memory_enabled": True,
    "memory_max_tokens": 300,
    "memory_search_threshold": 0.35,
    "history_inject_limit": 25,
    "history_line_max_chars": 280,
    # Tier 3 — personality & presence
    "personality_preset": "custom",
    "reply_mode": "default",
    "keyword_triggers": [],
    "always_respond_role_ids": [],
    "user_denylist": [],
    "user_allowlist": [],
    "bot_allowlist": [],
    "ignore_bots": False,
    "quiet_hours_enabled": False,
    "quiet_hours_start": 22,
    "quiet_hours_end": 8,
    "quiet_hours_mode": "reactions_only",
    "activity_decay_enabled": False,
    "activity_decay_threshold": 10,
    "activity_decay_multiplier": 0.5,
    "engagement_weight": 100,
    "message_edits_enabled": True,
    "greeting_enabled": False,
    "greeting_utc_hour": 9,
    "greeting_use_llm": True,
    "greeting_message": (
        "Write a short, warm good-morning message for this Discord channel. "
        "Sound like a friendly community member, not a bot announcement. "
        "One or two sentences. Vary your wording each day."
    ),
    "greeting_fallback": "Good morning, everyone! ☀️",
    "greeting_model_provider": "",
    "greeting_model_name": "",
    "greeting_max_tokens": 180,
    "greeting_targets": [],
    "sleep_schedule_enabled": False,
    "sleep_utc_hour": 22,
    "sleep_use_llm": True,
    "sleep_use_greeting_targets": True,
    "sleep_message": (
        "Write a short, warm good-night message for this Discord channel. "
        "Sound like a friendly community member signing off for the night. "
        "One or two sentences. Vary your wording."
    ),
    "sleep_fallback": "Good night, everyone! 🌙",
    "sleep_model_provider": "",
    "sleep_model_name": "",
    "sleep_max_tokens": 180,
    "sleep_targets": [],
    "sleep_buffered_reply_max": 3,
    "outreach_enabled": False,
    "outreach_quiet_minutes": 240,
    "outreach_cooldown_hours": 8,
    "outreach_skip_chance": 25,
    "outreach_active_start": 10,
    "outreach_active_end": 21,
    "outreach_use_llm": True,
    "outreach_typing_indicator": True,
    "outreach_message": (
        "Casually restart conversation in this Discord channel. "
        "Write one short message like a friend checking in — not an announcement or bot greeting. "
        "A question or light observation works well. Vary your wording."
    ),
    "outreach_fallback": "Anyone around? 👀",
    "outreach_model_provider": "",
    "outreach_model_name": "",
    "outreach_max_tokens": 180,
    "outreach_targets": [],
    "gif_replies_enabled": False,
    "gif_reply_chance": 15,
    "gif_reply_cooldown_seconds": 120,
    "gif_use_llm": True,
    "gif_model_provider": "",
    "gif_model_name": "",
    "gif_model_max_tokens": 80,
    "gif_provider": "klipy",
    "gif_content_filter": "medium",
    "tenor_content_filter": "medium",
    # Tier 4 — safety & slash
    "slash_commands_enabled": True,
    "safety_check_permissions": True,
    "rate_limit_seconds": 2,
    "rate_limit_burst": 8,
    "rate_limit_window": 60,
    "content_blocklist": [],
}

DM_DEFAULTS = {
    "human_response_chance": 25,
    "bot_response_chance": 0,
    "reaction_chance": 40,
    "cooldown_seconds": 60,
}


def get_plugin_settings() -> dict:
    try:
        from core.plugin_loader import plugin_loader
        state = plugin_loader.get_plugin_state("leona_discord")
        return state.get("settings", {}) or {}
    except Exception:
        return {}


def _normalize_id_list(value) -> list:
    if not value:
        return []
    if isinstance(value, str):
        parts = value.replace(",", " ").split()
        return [p.strip() for p in parts if p.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


def _normalize_keywords(value) -> list:
    items = _normalize_id_list(value)
    return [k.lower() for k in items if k][:50]


def _channel_override(server_s: dict, channel_id: str, channel_name: str) -> dict:
    channels = server_s.get("channels") or {}
    if not isinstance(channels, dict):
        return {}
    if channel_id and channel_id in channels:
        return dict(channels[channel_id] or {})
    name_key = (channel_name or "").strip().lower()
    if name_key and name_key in channels:
        return dict(channels[name_key] or {})
    return {}


def get_effective_settings(
    guild_id: str = "",
    channel_id: str = "",
    channel_name: str = "",
    is_dm: bool = False,
    channel_key: str = "",
) -> dict:
    """Merge global → preset → server → channel → DM, then presence modifiers."""
    try:
        raw = get_plugin_settings()
        global_s = raw.get("global", {}) or {}

        preset = str(global_s.get("personality_preset", "custom")).lower()
        base = dict(SETTING_DEFAULTS)
        if preset in PERSONALITY_PRESETS and preset != "custom":
            base.update(PERSONALITY_PRESETS[preset])

        merged = {**base, **global_s}

        if guild_id:
            server_s = (raw.get("servers", {}) or {}).get(str(guild_id), {}) or {}
            server_preset = str(server_s.get("personality_preset", "")).lower()
            if server_preset in PERSONALITY_PRESETS and server_preset != "custom":
                merged = {**merged, **PERSONALITY_PRESETS[server_preset]}
            ch_override = _channel_override(server_s, str(channel_id), channel_name)
            merged = {**merged, **{k: v for k, v in server_s.items() if k != "channels"}, **ch_override}

        if is_dm:
            dm_s = raw.get("dm", {}) or {}
            merged = {**merged, **{**DM_DEFAULTS, **dm_s}}

        merged["keyword_triggers"] = _normalize_keywords(merged.get("keyword_triggers"))
        merged["always_respond_role_ids"] = _normalize_id_list(merged.get("always_respond_role_ids"))
        merged["user_denylist"] = _normalize_id_list(merged.get("user_denylist"))
        merged["user_allowlist"] = _normalize_id_list(merged.get("user_allowlist"))
        merged["bot_allowlist"] = _normalize_id_list(merged.get("bot_allowlist"))

        from plugins.leona_discord.lib.presence import apply_quiet_hours
        from plugins.leona_discord.lib.activity import apply_activity_decay

        merged = apply_quiet_hours(merged)
        if channel_key:
            merged = apply_activity_decay(merged, channel_key)
        return merged
    except Exception:
        return dict(SETTING_DEFAULTS)


def get_batch_delay() -> float:
    val = get_plugin_settings().get("batch_delay", BATCH_DELAY_DEFAULT)
    try:
        return max(1.0, min(300.0, float(val)))
    except (TypeError, ValueError):
        return BATCH_DELAY_DEFAULT


def get_always_online() -> bool:
    """When True (default), connect all configured bot accounts on daemon start."""
    return bool(get_plugin_settings().get("always_online", True))


def get_image_settings(guild_id: str = "") -> dict:
    merged = get_effective_settings(guild_id=guild_id)
    return {
        "image_enabled": merged.get("image_enabled", False),
        "image_model_provider": merged.get("image_model_provider", ""),
        "image_model_name": merged.get("image_model_name", ""),
        "image_model_max_tokens": merged.get("image_model_max_tokens", 1024),
    }


def is_valid_preset(name: str) -> bool:
    return str(name).lower() in VALID_PRESETS
