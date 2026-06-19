"""Debug trace and memory status API routes."""

import logging

logger = logging.getLogger(__name__)


async def list_traces(**kwargs):
    """GET /api/plugin/leona_discord/traces"""
    query = kwargs.get("query") or {}
    channel_id = str(query.get("channel_id", "")).strip()
    try:
        limit = min(200, max(1, int(query.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    try:
        from plugins.leona_discord.lib import store as sqlite_store
        sqlite_store.init_db()
        traces = sqlite_store.list_traces(channel_id=channel_id, limit=limit)
        for t in traces:
            if isinstance(t.get("gates"), str):
                import json
                try:
                    t["gates"] = json.loads(t["gates"])
                except Exception:
                    t["gates"] = []
        return {"traces": traces}
    except Exception as e:
        logger.error(f"[LEONA-DISCORD] list_traces error: {e}")
        return {"traces": [], "error": str(e)}


async def memory_stats(**kwargs):
    """GET /api/plugin/leona_discord/memory/stats"""
    try:
        from plugins.leona_discord.lib import memory
        return memory.get_stats()
    except Exception as e:
        logger.error(f"[LEONA-DISCORD] memory_stats error: {e}")
        return {"error": str(e)}


async def list_llm_debug_logs(**kwargs):
    """GET /api/plugin/leona_discord/llm-debug"""
    query = kwargs.get("query") or {}
    channel_id = str(query.get("channel_id", "")).strip()
    try:
        limit = min(100, max(1, int(query.get("limit", 25))))
    except (TypeError, ValueError):
        limit = 25
    try:
        from plugins.leona_discord.lib import llm_debug
        logs = llm_debug.list_logs(limit=limit, channel_id=channel_id)
        return {"logs": logs}
    except Exception as e:
        logger.error(f"[LEONA-DISCORD] list_llm_debug_logs error: {e}")
        return {"logs": [], "error": str(e)}
