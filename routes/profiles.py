"""Profile inspection/reset routes for Leona Discord settings UI."""

# -- Portable import path (works from plugins/ or user/plugins/) --
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('_ldc', str(__import__('pathlib').Path(__file__).resolve().parent.parent / '_compat.py'))
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod); del _ilu, _spec, _mod

import logging

logger = logging.getLogger(__name__)


async def list_profiles(**kwargs):
    """GET /api/plugin/leona_discord/profiles"""
    query = kwargs.get("query") or {}
    account = str(query.get("account", "")).strip()
    guild_id = str(query.get("guild_id", "")).strip()
    username = str(query.get("username", "")).strip().lower()
    try:
        limit = max(1, min(200, int(query.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50

    try:
        from plugins.leona_discord.lib import profile_store

        profiles = profile_store.list_profiles(account=account, guild_id=guild_id, limit=limit)
        if username:
            profiles = [
                p for p in profiles
                if username in str(p.get("username", "")).lower()
                or username in str(p.get("display_name", "")).lower()
            ]
        out = []
        for p in profiles:
            facts = profile_store.get_facts(
                p.get("account", ""),
                p.get("guild_id", ""),
                p.get("author_id", ""),
                min_confidence=0.4,
                limit=6,
            )
            events = profile_store.get_recent_events(
                p.get("account", ""),
                p.get("guild_id", ""),
                p.get("author_id", ""),
                limit=3,
            )
            out.append(
                {
                    "account": p.get("account", ""),
                    "guild_id": p.get("guild_id", ""),
                    "author_id": p.get("author_id", ""),
                    "username": p.get("username", ""),
                    "display_name": p.get("display_name", ""),
                    "message_count": int(p.get("message_count", 0) or 0),
                    "reply_count": int(p.get("reply_count", 0) or 0),
                    "last_seen_at": float(p.get("last_seen_at", 0) or 0),
                    "summary_l1": (p.get("summary_l1") or "")[:800],
                    "summary_l2": (p.get("summary_l2") or "")[:1200],
                    "familiarity": float(p.get("familiarity", 0.0) or 0.0),
                    "warmth": float(p.get("warmth", 0.0) or 0.0),
                    "trust": float(p.get("trust", 0.0) or 0.0),
                    "playfulness": float(p.get("playfulness", 0.0) or 0.0),
                    "patience": float(p.get("patience", 0.0) or 0.0),
                    "interest": float(p.get("interest", 0.0) or 0.0),
                    "facts": facts,
                    "events": events,
                }
            )
        return {"profiles": out}
    except Exception as e:
        logger.error(f"[LEONA-DISCORD] list_profiles error: {e}")
        return {"profiles": [], "error": str(e)}


async def reset_profile(**kwargs):
    """POST /api/plugin/leona_discord/profiles/reset"""
    body = kwargs.get("body") or {}
    account = str(body.get("account", "")).strip()
    guild_id = str(body.get("guild_id", "")).strip()
    author_id = str(body.get("author_id", "")).strip()
    if not account or not author_id:
        return {"error": "account and author_id are required"}
    try:
        from plugins.leona_discord.lib import profile_store

        profile_store.forget_user(account, guild_id, author_id)
        return {
            "status": "reset",
            "account": account,
            "guild_id": guild_id,
            "author_id": author_id,
        }
    except Exception as e:
        logger.error(f"[LEONA-DISCORD] reset_profile error: {e}")
        return {"error": str(e)}


async def run_distill_now(**kwargs):
    """POST /api/plugin/leona_discord/profiles/distill-now"""
    try:
        from core.api_fastapi import get_system
        from plugins.leona_discord.schedule.profile_distill import run

        system = get_system()
        summary = run({"system": system})
        return {"status": "ok", "message": summary}
    except Exception as e:
        logger.error(f"[LEONA-DISCORD] run_distill_now error: {e}", exc_info=True)
        return {"error": str(e)}
