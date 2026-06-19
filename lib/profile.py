"""Per-user profiling — passive ingest, recall injection, disposition (self-contained)."""

import logging
import random
import time

from plugins.leona_discord.lib import profile_store
from plugins.leona_discord.lib.engagement import extract_topics
from plugins.leona_discord.lib.settings import get_effective_settings, get_plugin_settings

logger = logging.getLogger(__name__)

_REMEMBER_HINTS = (
    "remember that",
    "remember i",
    "don't forget",
    "dont forget",
    "i hate",
    "i love",
    "i like",
    "i dislike",
    "my name is",
    "call me",
)


def _profile_settings(guild_id: str = "", is_dm: bool = False) -> dict:
    raw = get_plugin_settings()
    g = raw.get("global", {}) or {}
    if not g.get("profiling_enabled", False):
        return {"enabled": False}
    merged = get_effective_settings(guild_id)
    if not merged.get("profiling_enabled", False):
        return {"enabled": False}
    if merged.get("profiling_dm_only", False) and not is_dm:
        return {"enabled": False}
    return {
        "enabled": True,
        "max_tokens": int(merged.get("profiling_max_tokens", 300)),
        "min_messages": int(merged.get("profiling_min_messages", 5)),
        "use_llm": bool(merged.get("profiling_use_llm", True)),
        "modulate_reply": bool(merged.get("profiling_modulate_reply_chance", True)),
        "imperfect_recall": bool(merged.get("profiling_imperfect_recall", False)),
        "imperfect_chance": float(merged.get("profiling_imperfect_recall_chance", 0.05)),
        "fact_min_confidence": float(merged.get("profiling_fact_confidence_min", 0.6)),
        "model_provider": str(merged.get("profiling_model_provider", "")).strip(),
        "model_name": str(merged.get("profiling_model_name", "")).strip(),
        "distill_max_tokens": int(merged.get("profiling_distill_max_tokens", 400)),
    }


def start():
    from plugins.leona_discord.lib import store as sqlite_store
    sqlite_store.init_db()
    cfg = get_plugin_settings().get("global", {}) or {}
    if not cfg.get("profiling_enabled", False):
        logger.info("[LEONA-DISCORD-PROFILE] User profiling disabled in settings")
        return
    logger.info("[LEONA-DISCORD-PROFILE] User profiling store ready")


def stop():
    pass


def familiarity_label(message_count: int) -> str:
    if message_count < 3:
        return "new here"
    if message_count < 15:
        return "occasional"
    if message_count < 50:
        return "regular"
    return "familiar regular"


def disposition_phrases(profile: dict) -> list:
    if not profile:
        return []
    phrases = []
    checks = [
        ("warmth", 0.62, "warm"),
        ("warmth", 0.38, "distant", True),
        ("trust", 0.62, "high trust"),
        ("playfulness", 0.62, "playful"),
        ("interest", 0.62, "engaged"),
        ("interest", 0.38, "low interest", True),
        ("patience", 0.35, "low patience", True),
        ("familiarity", 0.55, "well known"),
    ]
    for dim, threshold, label, *invert in checks:
        val = float(profile.get(dim, 0.5))
        if invert and val <= threshold:
            phrases.append(label)
        elif not invert and val >= threshold:
            phrases.append(label)
    return phrases[:4]


def _auto_summary_l1(profile: dict) -> str:
    name = profile.get("display_name") or profile.get("username") or "this user"
    fam = familiarity_label(int(profile.get("message_count", 0)))
    avg_len = int(profile.get("avg_message_length") or 0)
    style = ""
    if avg_len and avg_len < 60:
        style = "tends toward short messages"
    elif avg_len > 140:
        style = "often writes longer messages"
    parts = [f"{name} — {fam}"]
    if style:
        parts.append(style)
    replies = int(profile.get("reply_count", 0))
    if replies >= 5:
        parts.append(f"you've replied to them {replies} times")
    return "; ".join(parts)


def _time_since_note(last_seen_at: float) -> str:
    if not last_seen_at:
        return ""
    gap = time.time() - float(last_seen_at)
    if gap < 3600:
        return ""
    if gap < 86400:
        hours = int(gap / 3600)
        return f"Last spoke ~{hours}h ago — a light callback is fine."
    days = int(gap / 86400)
    if days >= 2:
        return f"Last spoke {days} days ago — acknowledge the gap naturally if relevant."
    return ""


def record_user_message(
    account: str,
    guild_id: str,
    author_id: str,
    *,
    username: str = "",
    display_name: str = "",
    content: str = "",
    is_dm: bool = False,
    is_bot: bool = False,
    message_id: str = "",
    thread_reply_to_bot: bool = False,
    mentioned: bool = False,
) -> None:
    if is_bot or not author_id:
        return
    cfg = _profile_settings(guild_id, is_dm=is_dm)
    if not cfg.get("enabled"):
        return

    profile = profile_store.upsert_profile_touch(
        account,
        guild_id,
        author_id,
        username=username,
        display_name=display_name,
        content=content,
        thread_reply_to_bot=thread_reply_to_bot,
    )

    topics = extract_topics(content or "")
    if topics:
        profile_store.bump_topics_positive(account, guild_id, author_id, topics)

    profile_store.append_buffer_message(
        account,
        guild_id,
        author_id,
        {
            "message_id": message_id,
            "content": (content or "")[:500],
            "at": time.time(),
            "mentioned": mentioned,
        },
    )

    lower = (content or "").lower()
    if any(h in lower for h in _REMEMBER_HINTS):
        profile_store.enqueue_distill(account, guild_id, author_id, reason="explicit_hint")

    mc = int(profile.get("message_count", 0))
    if cfg.get("use_llm") and mc >= cfg.get("min_messages", 5) and mc % 8 == 0:
        profile_store.enqueue_distill(account, guild_id, author_id, reason="periodic")


def record_outcome(
    account: str,
    guild_id: str,
    author_id: str,
    outcome: str,
    *,
    is_dm: bool = False,
) -> None:
    if not author_id:
        return
    cfg = _profile_settings(guild_id, is_dm=is_dm)
    if not cfg.get("enabled"):
        return
    profile_store.apply_outcome_delta(account, guild_id, author_id, outcome)


def record_bot_reply(
    account: str,
    guild_id: str,
    author_id: str,
    *,
    is_dm: bool = False,
) -> None:
    if not author_id:
        return
    cfg = _profile_settings(guild_id, is_dm=is_dm)
    if not cfg.get("enabled"):
        return
    profile_store.record_bot_reply(account, guild_id, author_id)
    profile_store.note_buffer_bot_reply(account, guild_id, author_id)


def save_user_fact(
    account: str,
    guild_id: str,
    author_id: str,
    text: str,
    *,
    username: str = "",
    confidence: float = 0.95,
) -> int:
    profile_store.upsert_profile_touch(
        account, guild_id, author_id, username=username, display_name=username, content=text,
    )
    return profile_store.add_fact(
        account, guild_id, author_id,
        "preference", "note", text,
        confidence=confidence,
    )


def forget_user(account: str, guild_id: str, author_id: str) -> None:
    profile_store.forget_user(account, guild_id, author_id)


def apply_profile_engagement(
    settings: dict,
    account: str,
    guild_id: str,
    author_id: str,
    *,
    is_dm: bool = False,
) -> dict:
    cfg = _profile_settings(guild_id, is_dm=is_dm)
    if not cfg.get("enabled") or not cfg.get("modulate_reply") or not author_id:
        return settings
    profile = profile_store.get_profile(account, guild_id, author_id)
    if not profile:
        return settings
    interest = float(profile.get("interest", 0.5))
    familiarity = float(profile.get("familiarity", 0.1))
    factor = 0.85 + (interest * 0.25) + (familiarity * 0.15)
    factor = max(0.7, min(1.35, factor))
    out = dict(settings)
    for key in ("human_response_chance", "bot_response_chance"):
        try:
            val = int(out.get(key, 0))
            out[key] = max(0, min(100, int(val * factor)))
        except (TypeError, ValueError):
            pass
    return out


def recall_user_context(
    account: str,
    guild_id: str,
    author_id: str,
    query: str = "",
    *,
    username: str = "",
    display_name: str = "",
    is_dm: bool = False,
    mentioned: bool = False,
) -> str:
    cfg = _profile_settings(guild_id, is_dm=is_dm)
    if not cfg.get("enabled") or not author_id:
        return ""

    profile = profile_store.get_profile(account, guild_id, author_id)
    if not profile or int(profile.get("message_count", 0)) < 1:
        return ""

    if cfg.get("imperfect_recall") and random.random() < cfg.get("imperfect_chance", 0.05):
        return ""

    name = display_name or profile.get("display_name") or username or profile.get("username") or "User"
    fam = familiarity_label(int(profile.get("message_count", 0)))
    lines = [
        "[People context — internal]",
        f"User: {name} (@{profile.get('username') or username or 'unknown'}, {fam})",
    ]

    disp = disposition_phrases(profile)
    if disp:
        lines.append(f"Disposition: {', '.join(disp)}")

    l1 = (profile.get("summary_l1") or "").strip() or _auto_summary_l1(profile)
    if l1:
        lines.append(f"Known: {l1}")

    facts = profile_store.search_facts(
        account,
        guild_id,
        author_id,
        query,
        min_confidence=cfg.get("fact_min_confidence", 0.6),
        limit=5 if mentioned or is_dm else 3,
    )
    if facts:
        fact_lines = [f"- {f['fact_value']}" for f in facts]
        lines.append("Facts:\n" + "\n".join(fact_lines))

    if mentioned or is_dm:
        l2 = (profile.get("summary_l2") or "").strip()
        if l2:
            lines.append(f"Detail: {l2}")

    gap_note = _time_since_note(float(profile.get("last_seen_at", 0)))
    if gap_note:
        lines.append(f"Note: {gap_note}")

    block = "\n".join(lines)
    max_chars = max(80, cfg.get("max_tokens", 300) * 4)
    if len(block) > max_chars:
        block = block[: max_chars - 1].rstrip() + "…"
    return block


def get_stats() -> dict:
    from plugins.leona_discord.lib.paths import get_data_dir, get_sqlite_path
    from plugins.leona_discord.lib import store as sqlite_store
    sqlite_store.init_db()
    stats = profile_store.profile_stats()
    return {
        "enabled": bool(get_plugin_settings().get("global", {}).get("profiling_enabled", False)),
        **stats,
        "data_dir": str(get_data_dir()),
        "sqlite_path": str(get_sqlite_path()),
    }
