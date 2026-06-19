"""Self-contained Discord memory — SQLite only, injected seamlessly (no tool calls)."""

import logging

from plugins.leona_discord.lib import store as sqlite_store
from plugins.leona_discord.lib.settings import get_effective_settings, get_plugin_settings

logger = logging.getLogger(__name__)


def _memory_settings(guild_id: str = "") -> dict:
    raw = get_plugin_settings()
    g = raw.get("global", {}) or {}
    if not g.get("memory_enabled", True):
        return {"enabled": False, "max_tokens": 0, "threshold": 0.35}
    merged = get_effective_settings(guild_id)
    if not merged.get("memory_enabled", True):
        return {"enabled": False, "max_tokens": 0, "threshold": 0.35}
    return {
        "enabled": True,
        "max_tokens": int(merged.get("memory_max_tokens", 300)),
        "threshold": float(merged.get("memory_search_threshold", 0.35)),
    }


def start():
    sqlite_store.init_db()
    cfg = get_plugin_settings()
    g = cfg.get("global", {}) or {}
    if not g.get("memory_enabled", True):
        logger.info("[LEONA-DISCORD-MEM] Memory disabled in settings")
        return
    logger.info("[LEONA-DISCORD-MEM] Self-contained memory store ready")


def stop():
    pass


def recall_context(account: str, guild_id: str, channel_id: str,
                   query: str, guild_name: str = "", channel_name: str = "",
                   exclude_message_ids: set = None) -> str:
    """Older relevant messages only — skips IDs already in the recent transcript."""
    cfg = _memory_settings(guild_id)
    if not cfg["enabled"]:
        return ""

    min_score = max(0.05, min(0.95, cfg["threshold"]))
    hits = sqlite_store.search_memory(
        account, guild_id, channel_id, query,
        limit=5,
        min_score=min_score,
        exclude_message_ids=exclude_message_ids,
    )

    pinned = sqlite_store.get_pinned_memories(account, guild_id=guild_id, limit=8)
    pinned_block = ""
    if pinned:
        lines = [f"- {p['username']}: {(p['content'] or '')[:200]}" for p in pinned]
        pinned_block = "[Pinned memories — saved via /remember]\n" + "\n".join(lines)

    if not hits and not pinned_block:
        return ""

    max_chars = cfg["max_tokens"] * 4
    parts = []
    if pinned_block:
        parts.append(pinned_block)
    if hits:
        header = "[Earlier Discord context — relevant messages not in recent chat]"
        lines = [header]
        used = len(header)
        for h in hits:
            text = (h["content"] or "").replace("\n", " ").strip()[:200]
            line = f"- {h['username']}: {text}"
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line)
        if len(lines) > 1:
            parts.append("\n".join(lines))

    if not parts:
        return ""
    return "\n\n".join(parts)


def get_stats() -> dict:
    from plugins.leona_discord.lib.paths import get_data_dir, get_sqlite_path
    sqlite_store.init_db()
    stats = {
        "backend": "sqlite",
        "self_contained": True,
        "message_count": sqlite_store.message_count(),
        "pinned_count": sqlite_store.pinned_count(),
        "data_dir": str(get_data_dir()),
        "sqlite_path": str(get_sqlite_path()),
    }
    try:
        from plugins.leona_discord.lib import profile
        stats["profiling"] = profile.get_stats()
    except Exception:
        stats["profiling"] = {}
    return stats
