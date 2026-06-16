# plugins/leona-discord/routes/settings.py — Plugin settings management

import logging

logger = logging.getLogger(__name__)

from plugins.leona_discord.emojis import DISCORD_EMOJI
from plugins.leona_discord.lib.presets import VALID_PRESETS, preset_values
from plugins.leona_discord.lib.reply_context import apply_reply_context_settings, read_reply_context_settings
from plugins.leona_discord.lib.settings import DM_DEFAULTS, SETTING_DEFAULTS

_DEFAULT_EMOJIS = DISCORD_EMOJI

_GLOBAL_DEFAULTS = {**SETTING_DEFAULTS}

_VALID_BACKENDS = ["vader", "distilbert"]
_VALID_REPLY_MODES = ["default", "reactions_only", "never", "mentions_only"]
_VALID_QUIET_MODES = ["reactions_only", "silent"]

_INT_FIELDS = {
    "human_response_chance": (0, 100),
    "bot_response_chance":   (0, 100),
    "cooldown_seconds":      (0, 600),
    "reaction_chance":       (0, 100),
    "reaction_cooldown_seconds": (0, 600),
    "image_model_max_tokens": (50, 2000),
    "memory_max_tokens": (100, 1200),
    "history_inject_limit": (5, 100),
    "history_line_max_chars": (80, 1000),
    "quiet_hours_start": (0, 23),
    "quiet_hours_end": (0, 23),
    "activity_decay_threshold": (2, 100),
    "engagement_weight": (1, 100),
    "rate_limit_seconds": (0, 120),
    "rate_limit_burst": (1, 50),
    "rate_limit_window": (10, 600),
    "outreach_quiet_minutes": (30, 1440),
    "outreach_cooldown_hours": (1, 72),
    "outreach_skip_chance": (0, 90),
    "outreach_active_start": (0, 23),
    "outreach_active_end": (0, 23),
    "outreach_max_tokens": (40, 500),
    "greeting_utc_hour": (0, 23),
    "sleep_utc_hour": (0, 23),
    "sleep_max_tokens": (40, 500),
    "sleep_buffered_reply_max": (1, 10),
    "sleep_forced_wake_mention_count": (2, 20),
    "sleep_forced_wake_window_minutes": (1, 120),
    "sleep_forced_wake_duration_minutes": (5, 180),
    "gif_reply_chance": (0, 100),
    "gif_reply_cooldown_seconds": (0, 3600),
    "gif_model_max_tokens": (20, 120),
}
_FLOAT_FIELDS = {
    "memory_search_threshold": (0.0, 1.0),
    "activity_decay_multiplier": (0.0, 1.0),
}
_BOOL_FIELDS = [
    "name_match_enabled",
    "name_match_case_sensitive",
    "reactions_enabled",
    "react_to_trigger",
    "react_to_any",
    "image_enabled",
    "append_to_user_message_enabled",
    "memory_enabled",
    "ignore_bots",
    "quiet_hours_enabled",
    "activity_decay_enabled",
    "greeting_enabled",
    "greeting_use_llm",
    "sleep_schedule_enabled",
    "sleep_use_llm",
    "sleep_use_greeting_targets",
    "sleep_forced_wake_enabled",
    "outreach_enabled",
    "outreach_use_llm",
    "outreach_typing_indicator",
    "gif_replies_enabled",
    "gif_use_llm",
    "message_edits_enabled",
    "slash_commands_enabled",
    "safety_check_permissions",
]
_LIST_FIELDS = [
    "keyword_triggers",
    "always_respond_role_ids",
    "user_denylist",
    "user_allowlist",
    "bot_allowlist",
    "greeting_targets",
    "outreach_targets",
    "content_blocklist",
]
_VALID_SCOPES = ["per_channel", "global"]


def _get_state():
    from core.plugin_loader import plugin_loader
    return plugin_loader.get_plugin_state("leona_discord")


def _parse_list_field(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()][:200]
    if isinstance(value, str):
        parts = value.replace(",", "\n").split()
        return [p.strip() for p in parts if p.strip()][:200]
    return []


def _apply_message_settings(body: dict, target: dict):
    for field, (mn, mx) in _INT_FIELDS.items():
        if field in body:
            try:
                target[field] = max(mn, min(mx, int(body[field])))
            except (TypeError, ValueError):
                pass
    for field, (mn, mx) in _FLOAT_FIELDS.items():
        if field in body:
            try:
                target[field] = max(mn, min(mx, float(body[field])))
            except (TypeError, ValueError):
                pass
    for field in _BOOL_FIELDS:
        if field in body:
            target[field] = bool(body[field])
    for field in _LIST_FIELDS:
        if field in body:
            target[field] = _parse_list_field(body[field])
    if "cooldown_scope" in body and body["cooldown_scope"] in _VALID_SCOPES:
        target["cooldown_scope"] = body["cooldown_scope"]
    if "reaction_backend" in body and body["reaction_backend"] in _VALID_BACKENDS:
        target["reaction_backend"] = body["reaction_backend"]
    if "reply_mode" in body and body["reply_mode"] in _VALID_REPLY_MODES:
        target["reply_mode"] = body["reply_mode"]
    if "quiet_hours_mode" in body and body["quiet_hours_mode"] in _VALID_QUIET_MODES:
        target["quiet_hours_mode"] = body["quiet_hours_mode"]
    if "personality_preset" in body:
        preset = str(body["personality_preset"]).lower().strip()
        if preset in VALID_PRESETS:
            target["personality_preset"] = preset
            if preset != "custom" and body.get("apply_preset_values"):
                target.update(preset_values(preset))
    if "allowed_emojis" in body and isinstance(body["allowed_emojis"], list):
        target["allowed_emojis"] = [str(e).strip() for e in body["allowed_emojis"] if str(e).strip()][:100]
    if "image_model_provider" in body:
        target["image_model_provider"] = str(body["image_model_provider"]).strip()
    if "image_model_name" in body:
        target["image_model_name"] = str(body["image_model_name"]).strip()
    if "image_model_max_tokens" in body:
        try:
            val = int(body["image_model_max_tokens"])
            if 1 <= val <= 2000:
                target["image_model_max_tokens"] = val
        except (ValueError, TypeError):
            pass
    if "append_to_user_message" in body:
        target["append_to_user_message"] = str(body["append_to_user_message"]).strip()[:2000]
    if "greeting_message" in body:
        target["greeting_message"] = str(body["greeting_message"]).strip()[:2000]
    if "sleep_message" in body:
        target["sleep_message"] = str(body["sleep_message"]).strip()[:2000]


def _apply_top_level_settings(body: dict, stored: dict):
    """Write settings that live at the root level (NOT in the global/server merge chain).

    Greeting/outreach/memory/gif/slash settings are written to stored["global"]
    via _apply_message_settings — do NOT duplicate them here.
    """
    if "batch_delay" in body:
        try:
            val = float(body["batch_delay"])
            if not (1 <= val <= 300):
                return "batch_delay must be between 1 and 300 seconds"
            stored["batch_delay"] = val
        except (TypeError, ValueError):
            return "batch_delay must be a number"
    if "always_online" in body:
        stored["always_online"] = bool(body["always_online"])
    if "debug_trace_enabled" in body:
        stored["debug_trace_enabled"] = bool(body["debug_trace_enabled"])
    if "tenor_api_key" in body:
        stored["gif_api_key"] = str(body["tenor_api_key"]).strip()[:200]
    if "gif_api_key" in body:
        stored["gif_api_key"] = str(body["gif_api_key"]).strip()[:200]
    if "gif_provider" in body:
        prov = str(body["gif_provider"]).strip().lower()
        if prov in ("klipy", "giphy", "tenor"):
            stored["gif_provider"] = prov
    if "dm" in body and isinstance(body["dm"], dict):
        dm = stored.get("dm", {}) or {}
        _apply_message_settings(body["dm"], dm)
        stored["dm"] = dm
    if "llm_max_history" in body:
        try:
            stored["llm_max_history"] = max(0, min(500, int(body["llm_max_history"])))
        except (TypeError, ValueError):
            return "llm_max_history must be a number (0–500)"
    if "reply_context_limit" in body:
        try:
            stored["reply_context_limit"] = max(0, min(200000, int(body["reply_context_limit"])))
        except (TypeError, ValueError):
            return "reply_context_limit must be a number (0–200000)"
    return None


async def get_settings(**kwargs):
    """GET /api/plugin/leona_discord/settings"""
    state = _get_state()
    stored = state.get("settings", {}) or {}
    global_s = {**_GLOBAL_DEFAULTS, **(stored.get("global", {}) or {})}
    if "allowed_emojis" not in global_s:
        global_s["allowed_emojis"] = list(_DEFAULT_EMOJIS)
    return {
        # Truly top-level settings (stored at root, NOT in global merge chain)
        "batch_delay": stored.get("batch_delay", 8),
        "always_online": stored.get("always_online", True),
        "debug_trace_enabled": stored.get("debug_trace_enabled", True),
        "tenor_api_key": stored.get("gif_api_key") or stored.get("tenor_api_key", ""),
        "gif_api_key": stored.get("gif_api_key") or stored.get("tenor_api_key", ""),
        "gif_provider": stored.get("gif_provider", "klipy"),
        "dm": {**DM_DEFAULTS, **(stored.get("dm", {}) or {})},
        # Settings that live in stored["global"] (single source of truth)
        "memory_enabled": global_s.get("memory_enabled", True),
        "greeting_enabled": global_s.get("greeting_enabled", False),
        "greeting_utc_hour": global_s.get("greeting_utc_hour", 9),
        "greeting_use_llm": global_s.get("greeting_use_llm", True),
        "greeting_message": global_s.get("greeting_message", ""),
        "greeting_fallback": global_s.get("greeting_fallback", "Good morning, everyone! ☀️"),
        "greeting_model_provider": global_s.get("greeting_model_provider", ""),
        "greeting_model_name": global_s.get("greeting_model_name", ""),
        "greeting_max_tokens": global_s.get("greeting_max_tokens", 180),
        "greeting_targets": global_s.get("greeting_targets", []) or [],
        "sleep_schedule_enabled": global_s.get("sleep_schedule_enabled", False),
        "sleep_utc_hour": global_s.get("sleep_utc_hour", 22),
        "sleep_use_llm": global_s.get("sleep_use_llm", True),
        "sleep_use_greeting_targets": global_s.get("sleep_use_greeting_targets", True),
        "sleep_message": global_s.get("sleep_message", ""),
        "sleep_fallback": global_s.get("sleep_fallback", "Good night, everyone! 🌙"),
        "sleep_model_provider": global_s.get("sleep_model_provider", ""),
        "sleep_model_name": global_s.get("sleep_model_name", ""),
        "sleep_max_tokens": global_s.get("sleep_max_tokens", 180),
        "sleep_targets": global_s.get("sleep_targets", []) or [],
        "sleep_buffered_reply_max": global_s.get("sleep_buffered_reply_max", 3),
        "sleep_forced_wake_enabled": global_s.get("sleep_forced_wake_enabled", False),
        "sleep_forced_wake_mention_count": global_s.get("sleep_forced_wake_mention_count", 3),
        "sleep_forced_wake_window_minutes": global_s.get("sleep_forced_wake_window_minutes", 15),
        "sleep_forced_wake_duration_minutes": global_s.get("sleep_forced_wake_duration_minutes", 30),
        "outreach_enabled": global_s.get("outreach_enabled", False),
        "outreach_quiet_minutes": global_s.get("outreach_quiet_minutes", 240),
        "outreach_cooldown_hours": global_s.get("outreach_cooldown_hours", 8),
        "outreach_skip_chance": global_s.get("outreach_skip_chance", 25),
        "outreach_active_start": global_s.get("outreach_active_start", 10),
        "outreach_active_end": global_s.get("outreach_active_end", 21),
        "outreach_use_llm": global_s.get("outreach_use_llm", True),
        "outreach_typing_indicator": global_s.get("outreach_typing_indicator", True),
        "outreach_message": global_s.get("outreach_message", ""),
        "outreach_fallback": global_s.get("outreach_fallback", "Anyone around? 👀"),
        "outreach_model_provider": global_s.get("outreach_model_provider", ""),
        "outreach_model_name": global_s.get("outreach_model_name", ""),
        "outreach_max_tokens": global_s.get("outreach_max_tokens", 180),
        "outreach_targets": global_s.get("outreach_targets", []) or [],
        "gif_replies_enabled": global_s.get("gif_replies_enabled", False),
        "gif_reply_chance": global_s.get("gif_reply_chance", 15),
        "gif_reply_cooldown_seconds": global_s.get("gif_reply_cooldown_seconds", 120),
        "gif_use_llm": global_s.get("gif_use_llm", True),
        "gif_model_provider": global_s.get("gif_model_provider", ""),
        "gif_model_name": global_s.get("gif_model_name", ""),
        "gif_model_max_tokens": global_s.get("gif_model_max_tokens", 80),
        "gif_content_filter": global_s.get("gif_content_filter") or global_s.get("tenor_content_filter", "medium"),
        "tenor_content_filter": global_s.get("gif_content_filter") or global_s.get("tenor_content_filter", "medium"),
        "slash_commands_enabled": global_s.get("slash_commands_enabled", True),
        "message_edits_enabled": global_s.get("message_edits_enabled", True),
        # Sub-objects
        "global": global_s,
        "servers": stored.get("servers", {}) or {},
        "default_emojis": _DEFAULT_EMOJIS,
        "personality_presets": sorted(p for p in VALID_PRESETS if p != "custom"),
        **read_reply_context_settings(),
    }


async def save_global_settings(**kwargs):
    """POST /api/plugin/leona_discord/settings/global"""
    body = kwargs.get("body", {})
    state = _get_state()
    stored = state.get("settings", {}) or {}

    err = _apply_top_level_settings(body, stored)
    if err:
        return {"error": err}

    global_s = stored.get("global", {}) or {}
    if "personality_preset" in body and body.get("apply_preset_values"):
        body = {**body, "apply_preset_values": True}
    _apply_message_settings(body, global_s)
    stored["global"] = global_s

    state.save("settings", stored)

    sync_body = {}
    if "llm_max_history" in body:
        sync_body["llm_max_history"] = stored.get("llm_max_history", 0)
    if "reply_context_limit" in body:
        sync_body["reply_context_limit"] = stored.get("reply_context_limit", 0)
    warnings = []
    if sync_body:
        ok, sync_warnings = apply_reply_context_settings(**sync_body)
        if not ok:
            return {"error": sync_warnings[0] if sync_warnings else "Failed to sync reply context settings"}
        warnings.extend(sync_warnings)

    logger.info(f"[LEONA-DISCORD] Global settings updated: {global_s}")
    result = {"status": "saved", "global": global_s, **read_reply_context_settings()}
    if warnings:
        result["warnings"] = warnings
    return result


async def save_server_settings(**kwargs):
    """POST /api/plugin/leona_discord/settings/servers/{guild_id}"""
    guild_id = str(kwargs.get("guild_id", "")).strip()
    if not guild_id:
        return {"error": "guild_id required"}
    body = kwargs.get("body", {})
    state = _get_state()
    stored = state.get("settings", {}) or {}
    servers = stored.get("servers", {}) or {}
    server_s = servers.get(guild_id, {}) or {}
    _apply_message_settings(body, server_s)

    if "channels" in body and isinstance(body["channels"], dict):
        channels = server_s.get("channels", {}) or {}
        for ch_key, ch_body in body["channels"].items():
            ch_key = str(ch_key).strip()
            if not ch_key:
                continue
            if ch_body is None or ch_body == {}:
                channels.pop(ch_key, None)
            elif isinstance(ch_body, dict):
                entry = channels.get(ch_key, {}) or {}
                _apply_message_settings(ch_body, entry)
                if ch_body.get("reply_mode") in _VALID_REPLY_MODES:
                    entry["reply_mode"] = ch_body["reply_mode"]
                channels[ch_key] = entry
        server_s["channels"] = channels

    servers[guild_id] = server_s
    stored["servers"] = servers
    state.save("settings", stored)
    logger.info(f"[LEONA-DISCORD] Server {guild_id} override updated: {server_s}")
    return {"status": "saved", "guild_id": guild_id, "settings": server_s}


async def delete_server_settings(**kwargs):
    """DELETE /api/plugin/leona_discord/settings/servers/{guild_id}"""
    guild_id = str(kwargs.get("guild_id", "")).strip()
    if not guild_id:
        return {"error": "guild_id required"}
    state = _get_state()
    stored = state.get("settings", {}) or {}
    servers = stored.get("servers", {}) or {}
    servers.pop(guild_id, None)
    stored["servers"] = servers
    state.save("settings", stored)
    logger.info(f"[LEONA-DISCORD] Server {guild_id} override removed")
    return {"status": "deleted", "guild_id": guild_id}


async def list_servers(**kwargs):
    """GET /api/plugin/leona_discord/servers"""
    try:
        from plugins.leona_discord.daemon import _clients
        servers = []
        for acct, client in _clients.items():
            if not client.is_ready():
                continue
            for guild in client.guilds:
                servers.append({
                    "guild_id": str(guild.id),
                    "guild_name": guild.name,
                    "account": acct,
                    "member_count": guild.member_count,
                })
        return {"servers": servers}
    except Exception as e:
        logger.error(f"[LEONA-DISCORD] list_servers error: {e}")
        return {"servers": []}


async def list_channels(**kwargs):
    """GET /api/plugin/leona_discord/channels?guild_id=&account="""
    guild_id = str(kwargs.get("guild_id", "")).strip()
    account = str(kwargs.get("account", "")).strip()
    if not guild_id:
        return {"error": "guild_id required", "channels": []}
    try:
        from plugins.leona_discord.daemon import _clients
        channels = []
        clients = _clients.items() if not account else [(account, _clients.get(account))]
        for acct, client in clients:
            if not client or not client.is_ready():
                continue
            guild = client.get_guild(int(guild_id))
            if not guild:
                continue
            for ch in guild.text_channels:
                channels.append({
                    "channel_id": str(ch.id),
                    "channel_name": ch.name,
                    "account": acct,
                })
            break
        return {"channels": channels}
    except Exception as e:
        logger.error(f"[LEONA-DISCORD] list_channels error: {e}")
        return {"channels": [], "error": str(e)}


_GREETING_TEST_KEYS = (
    "greeting_use_llm",
    "greeting_message",
    "greeting_fallback",
    "greeting_model_provider",
    "greeting_model_name",
    "greeting_max_tokens",
    "greeting_targets",
)


async def test_greeting(**kwargs):
    """POST /api/plugin/leona_discord/greeting/test — send greeting now (ignores UTC hour)."""
    body = kwargs.get("body") or {}

    raw = dict(_get_state().get("settings", {}) or {})
    g = dict(raw.get("global", {}) or {})
    for key in _GREETING_TEST_KEYS:
        if key in body:
            g[key] = body[key]
    raw["global"] = g

    targets = g.get("greeting_targets") or []
    if not isinstance(targets, list) or not targets:
        return {"success": False, "error": "No greeting channels selected"}

    try:
        from core.api_fastapi import get_system
        from plugins.leona_discord.schedule.morning_greeting import run_greeting

        system = get_system()
        summary = run_greeting(raw, system=system, test=True)
    except Exception as e:
        logger.error(f"[LEONA-DISCORD] Greeting test failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

    if summary.startswith("Skipped"):
        return {"success": False, "error": summary, "message": summary}

    sent_ok = summary.startswith("Sent ") and not summary.startswith("Sent 0 ")
    return {"success": sent_ok, "message": summary}


async def list_greeting_targets(**kwargs):
    """GET /api/plugin/leona_discord/greeting/targets — all text channels for the picker UI."""
    try:
        from plugins.leona_discord.daemon import _clients
        targets = []
        for acct, client in _clients.items():
            if not client or not client.is_ready():
                continue
            for guild in client.guilds:
                for ch in guild.text_channels:
                    targets.append({
                        "account": acct,
                        "guild_id": str(guild.id),
                        "guild_name": guild.name,
                        "channel_id": str(ch.id),
                        "channel_name": ch.name,
                        "value": f"{acct}:{guild.id}:{ch.id}",
                        "label": f"{acct} · {guild.name} · #{ch.name}",
                    })
        targets.sort(key=lambda t: (t["account"].lower(), t["guild_name"].lower(), t["channel_name"].lower()))
        return {"targets": targets, "connected": bool(targets)}
    except Exception as e:
        logger.error(f"[LEONA-DISCORD] list_greeting_targets error: {e}")
        return {"targets": [], "connected": False, "error": str(e)}
