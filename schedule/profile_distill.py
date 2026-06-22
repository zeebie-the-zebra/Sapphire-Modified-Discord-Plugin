"""Process profile distillation queue and idle interaction buffers."""

# -- Portable import path (works from plugins/ or user/plugins/) --
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('_ldc', str(__import__('pathlib').Path(__file__).resolve().parent.parent / '_compat.py'))
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod); del _ilu, _spec, _mod

import logging
import time

logger = logging.getLogger(__name__)
_LAST_DISTILL_RUN_AT = 0.0


def run(event):
    """Called by the continuity scheduler every few minutes."""
    from plugins.leona_discord.lib import profile_store
    from plugins.leona_discord.lib.profile import _profile_settings
    from plugins.leona_discord.lib.profile_distill_llm import distill_profile
    from plugins.leona_discord.lib.settings import get_plugin_settings
    from plugins.leona_discord.lib import store as sqlite_store

    raw = get_plugin_settings()
    g = raw.get("global", {}) or {}
    if not g.get("profiling_enabled", False):
        return "Skipped (profiling disabled)"
    if not g.get("profiling_use_llm", True):
        return "Skipped (LLM distillation off)"

    ready_buffers = profile_store.list_ready_buffers()
    pending = profile_store.fetch_pending_distills(limit=6)
    if not ready_buffers and not pending:
        return "Skipped (no new profiling content)"

    global _LAST_DISTILL_RUN_AT
    try:
        interval_minutes = max(1, min(60, int(g.get("profiling_distill_interval_minutes", 3))))
    except (TypeError, ValueError):
        interval_minutes = 3
    now = time.time()
    if _LAST_DISTILL_RUN_AT > 0 and (now - _LAST_DISTILL_RUN_AT) < (interval_minutes * 60):
        return f"Deferred (interval {interval_minutes}m)"

    system = (event or {}).get("system")
    if not system:
        return "Skipped (no system)"

    processed = 0

    for buf in ready_buffers:
        account = buf["account"]
        guild_id = buf["guild_id"]
        author_id = buf["author_id"]
        cfg = _profile_settings(guild_id, is_dm=(guild_id == ""))
        if not cfg.get("enabled"):
            profile_store.clear_buffer(account, guild_id, author_id)
            continue
        profile = profile_store.get_profile(account, guild_id, author_id)
        if not profile or int(profile.get("message_count", 0)) < cfg.get("min_messages", 5):
            profile_store.clear_buffer(account, guild_id, author_id)
            continue
        profile_store.enqueue_distill(account, guild_id, author_id, reason="buffer_ready")
        profile_store.clear_buffer(account, guild_id, author_id)

    for job in pending:
        account = job["account"]
        guild_id = job["guild_id"]
        author_id = job["author_id"]
        cfg = _profile_settings(guild_id, is_dm=(guild_id == ""))
        if not cfg.get("enabled"):
            profile_store.mark_pending_processed(job["id"])
            continue

        profile = profile_store.get_profile(account, guild_id, author_id)
        if not profile:
            profile_store.mark_pending_processed(job["id"])
            continue

        rows = sqlite_store.fetch_user_messages(account, guild_id, author_id, limit=24)
        if not rows:
            profile_store.mark_pending_processed(job["id"])
            continue

        rows.reverse()
        lines = []
        for r in rows:
            text = (r.get("content") or "").replace("\n", " ").strip()[:220]
            if text:
                lines.append(f"{r.get('display_name') or r.get('username')}: {text}")

        facts = profile_store.get_facts(
            account, guild_id, author_id,
            min_confidence=cfg.get("fact_min_confidence", 0.6),
            limit=12,
        )

        result = distill_profile(
            system,
            account=account,
            guild_id=guild_id,
            author_id=author_id,
            display_name=profile.get("display_name") or profile.get("username") or "User",
            transcript_lines=lines,
            current_summary_l1=profile.get("summary_l1") or "",
            current_facts=facts,
            disposition={
                k: profile.get(k) for k in (
                    "familiarity", "warmth", "trust", "playfulness", "patience", "interest",
                )
            },
            provider_key=cfg.get("model_provider", ""),
            model_name=cfg.get("model_name", ""),
            max_tokens=cfg.get("distill_max_tokens", 400),
        )

        if result:
            for fact in result.get("facts_add") or []:
                try:
                    profile_store.add_fact(
                        account,
                        guild_id,
                        author_id,
                        str(fact.get("category", "preference")),
                        str(fact.get("key", "note")),
                        str(fact.get("value", "")),
                        confidence=float(fact.get("confidence", 0.7)),
                    )
                except (TypeError, ValueError):
                    pass
            for supersede in result.get("facts_supersede") or []:
                try:
                    profile_store.lower_fact_confidence(int(supersede.get("id", 0)))
                except (TypeError, ValueError):
                    pass
            profile_store.apply_disposition_delta(
                account, guild_id, author_id,
                result.get("disposition_delta") or {},
            )
            note = (result.get("relationship_note") or "").strip()
            if note:
                profile_store.log_event(account, guild_id, author_id, "relationship", note)
            profile_store.update_summaries(
                account,
                guild_id,
                author_id,
                summary_l1=str(result.get("l1_summary") or ""),
                summary_l2=str(result.get("l2_summary") or ""),
            )

        profile_store.mark_pending_processed(job["id"])
        processed += 1

    if processed:
        _LAST_DISTILL_RUN_AT = now
        decayed = profile_store.decay_dispositions(max_rows=40)
        return f"Distilled {processed} profile(s); decayed {decayed}"
    return "No profile work"
