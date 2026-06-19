"""SQLite persistence for per-user profiling (self-contained in leona_discord)."""

import json
import logging
import time
from typing import Optional

from plugins.leona_discord.lib.store import connection, init_db, _lock

logger = logging.getLogger(__name__)

# Profiles are global per Discord user (author_id), not per guild.
GLOBAL_PROFILE_GUILD = ""

_DISPOSITION_DIMS = (
    "familiarity", "warmth", "trust", "playfulness", "patience", "interest",
)

DISPOSITION_REST = {
    "familiarity": 0.1,
    "warmth": 0.5,
    "trust": 0.5,
    "playfulness": 0.5,
    "patience": 0.7,
    "interest": 0.5,
}

BUFFER_IDLE_SECS = 15 * 60


def _profile_guild(guild_id: str = "") -> str:
    """Normalize guild scope — profiles are keyed globally per author."""
    return GLOBAL_PROFILE_GUILD


def _merge_topics(rows: list, key: str) -> str:
    merged = {}
    for row in rows:
        try:
            data = json.loads(row.get(key) or "{}")
        except (TypeError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            continue
        for topic, weight in data.items():
            try:
                merged[topic] = merged.get(topic, 0.0) + float(weight)
            except (TypeError, ValueError):
                continue
    return json.dumps(merged)[:4000]


def _merge_profile_rows(rows: list) -> dict:
    """Combine per-guild profile rows into one global row."""
    if not rows:
        return {}
    items = [dict(r) for r in rows]
    best = max(items, key=lambda r: (int(r.get("message_count", 0)), float(r.get("last_seen_at", 0))))
    total_mc = sum(int(r.get("message_count", 0) or 0) for r in items)
    total_rc = sum(int(r.get("reply_count", 0) or 0) for r in items)
    weighted_len = sum(
        float(r.get("avg_message_length") or 0) * int(r.get("message_count", 0) or 0)
        for r in items
    )
    avg_len = weighted_len / total_mc if total_mc else float(best.get("avg_message_length") or 0)

    merged_disp = {}
    for dim in _DISPOSITION_DIMS:
        if total_mc > 0:
            merged_disp[dim] = sum(
                float(r.get(dim, DISPOSITION_REST[dim])) * int(r.get("message_count", 0) or 0)
                for r in items
            ) / total_mc
        else:
            merged_disp[dim] = float(best.get(dim, DISPOSITION_REST[dim]))

    summary_l1 = ""
    summary_l2 = ""
    summary_updated_at = 0.0
    for r in sorted(items, key=lambda x: (-int(x.get("message_count", 0) or 0), -float(x.get("last_seen_at", 0) or 0))):
        if not summary_l1 and (r.get("summary_l1") or "").strip():
            summary_l1 = r["summary_l1"]
        if not summary_l2 and (r.get("summary_l2") or "").strip():
            summary_l2 = r["summary_l2"]
        summary_updated_at = max(summary_updated_at, float(r.get("summary_updated_at", 0) or 0))

    latest = max(items, key=lambda r: float(r.get("last_seen_at", 0) or 0))
    return {
        "account": best["account"],
        "guild_id": GLOBAL_PROFILE_GUILD,
        "author_id": str(best["author_id"]),
        "username": latest.get("username") or best.get("username") or "",
        "display_name": latest.get("display_name") or best.get("display_name") or "",
        "first_seen_at": min(float(r.get("first_seen_at", 0) or 0) for r in items),
        "last_seen_at": max(float(r.get("last_seen_at", 0) or 0) for r in items),
        "message_count": total_mc,
        "reply_count": total_rc,
        "avg_message_length": avg_len,
        "preferred_hour_utc": int(latest.get("preferred_hour_utc", 0) or 0),
        "topics_positive": _merge_topics(items, "topics_positive"),
        "topics_negative": _merge_topics(items, "topics_negative"),
        "communication_style": (best.get("communication_style") or "")[:500],
        "summary_l1": (summary_l1 or "")[:800],
        "summary_l2": (summary_l2 or "")[:1600],
        "summary_updated_at": summary_updated_at,
        **{dim: max(0.0, min(1.0, merged_disp[dim])) for dim in _DISPOSITION_DIMS},
    }


def _migrate_global_profiles(conn) -> None:
    """One-time merge of legacy per-guild rows into global profiles."""
    pairs = conn.execute(
        """
        SELECT account, author_id
        FROM user_profiles
        GROUP BY account, author_id
        HAVING COUNT(*) > 1 OR SUM(CASE WHEN guild_id != '' THEN 1 ELSE 0 END) > 0
        """
    ).fetchall()
    if not pairs:
        return

    migrated = 0
    for pair in pairs:
        account = pair["account"]
        author_id = str(pair["author_id"])
        rows = conn.execute(
            "SELECT * FROM user_profiles WHERE account = ? AND author_id = ?",
            (account, author_id),
        ).fetchall()
        if not rows:
            continue
        if len(rows) == 1 and (rows[0]["guild_id"] or "") == GLOBAL_PROFILE_GUILD:
            continue

        merged = _merge_profile_rows(rows)
        conn.execute("DELETE FROM user_profiles WHERE account = ? AND author_id = ?", (account, author_id))
        conn.execute(
            """
            INSERT INTO user_profiles (
                account, guild_id, author_id, username, display_name,
                first_seen_at, last_seen_at, message_count, reply_count, avg_message_length,
                preferred_hour_utc, topics_positive, topics_negative, communication_style,
                summary_l1, summary_l2, summary_updated_at,
                familiarity, warmth, trust, playfulness, patience, interest
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                merged["account"], merged["guild_id"], merged["author_id"],
                merged["username"], merged["display_name"],
                merged["first_seen_at"], merged["last_seen_at"],
                merged["message_count"], merged["reply_count"], merged["avg_message_length"],
                merged["preferred_hour_utc"], merged["topics_positive"], merged["topics_negative"],
                merged["communication_style"],
                merged["summary_l1"], merged["summary_l2"], merged["summary_updated_at"],
                merged["familiarity"], merged["warmth"], merged["trust"],
                merged["playfulness"], merged["patience"], merged["interest"],
            ),
        )

        conn.execute(
            "UPDATE profile_facts SET guild_id = ? WHERE account = ? AND author_id = ?",
            (GLOBAL_PROFILE_GUILD, account, author_id),
        )
        conn.execute(
            "UPDATE profile_events SET guild_id = ? WHERE account = ? AND author_id = ?",
            (GLOBAL_PROFILE_GUILD, account, author_id),
        )
        conn.execute(
            "UPDATE profile_pending SET guild_id = ? WHERE account = ? AND author_id = ? AND processed = 0",
            (GLOBAL_PROFILE_GUILD, account, author_id),
        )

        buf_rows = conn.execute(
            "SELECT * FROM profile_buffers WHERE account = ? AND author_id = ?",
            (account, author_id),
        ).fetchall()
        if buf_rows:
            msgs = []
            exchange_count = 0
            last_user_at = 0.0
            last_bot_reply_at = 0.0
            flush_after = 0.0
            for buf in buf_rows:
                try:
                    chunk = json.loads(buf["messages_json"] or "[]")
                except (TypeError, json.JSONDecodeError):
                    chunk = []
                if isinstance(chunk, list):
                    msgs.extend(chunk)
                exchange_count = max(exchange_count, int(buf.get("exchange_count", 0) or 0))
                last_user_at = max(last_user_at, float(buf.get("last_user_at", 0) or 0))
                last_bot_reply_at = max(last_bot_reply_at, float(buf.get("last_bot_reply_at", 0) or 0))
                flush_after = max(flush_after, float(buf.get("flush_after", 0) or 0))
            conn.execute(
                "DELETE FROM profile_buffers WHERE account = ? AND author_id = ?",
                (account, author_id),
            )
            if msgs:
                conn.execute(
                    """
                    INSERT INTO profile_buffers (
                        account, guild_id, author_id, messages_json,
                        exchange_count, last_user_at, last_bot_reply_at, flush_after
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        account, GLOBAL_PROFILE_GUILD, author_id,
                        json.dumps(msgs[-40:]),
                        exchange_count, last_user_at, last_bot_reply_at, flush_after,
                    ),
                )

        migrated += 1

    conn.execute(
        """
        DELETE FROM profile_facts
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM profile_facts
            GROUP BY account, author_id, category, fact_key, fact_value
        )
        """
    )
    conn.execute(
        """
        DELETE FROM profile_pending
        WHERE processed = 0 AND id NOT IN (
            SELECT MIN(id)
            FROM profile_pending
            WHERE processed = 0
            GROUP BY account, author_id
        )
        """
    )

    if migrated:
        logger.info("[LEONA-DISCORD-PROFILE] Migrated %s user(s) to global profiles", migrated)


def ensure_profile_tables(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            account TEXT NOT NULL,
            guild_id TEXT NOT NULL DEFAULT '',
            author_id TEXT NOT NULL,
            username TEXT DEFAULT '',
            display_name TEXT DEFAULT '',
            first_seen_at REAL NOT NULL,
            last_seen_at REAL NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 0,
            reply_count INTEGER NOT NULL DEFAULT 0,
            avg_message_length REAL NOT NULL DEFAULT 0,
            preferred_hour_utc INTEGER NOT NULL DEFAULT 0,
            topics_positive TEXT NOT NULL DEFAULT '{}',
            topics_negative TEXT NOT NULL DEFAULT '{}',
            communication_style TEXT NOT NULL DEFAULT '',
            summary_l1 TEXT NOT NULL DEFAULT '',
            summary_l2 TEXT NOT NULL DEFAULT '',
            summary_updated_at REAL NOT NULL DEFAULT 0,
            familiarity REAL NOT NULL DEFAULT 0.1,
            warmth REAL NOT NULL DEFAULT 0.5,
            trust REAL NOT NULL DEFAULT 0.5,
            playfulness REAL NOT NULL DEFAULT 0.5,
            patience REAL NOT NULL DEFAULT 0.7,
            interest REAL NOT NULL DEFAULT 0.5,
            PRIMARY KEY (account, guild_id, author_id)
        );
        CREATE INDEX IF NOT EXISTS idx_user_profiles_last_seen
            ON user_profiles(account, guild_id, last_seen_at DESC);

        CREATE TABLE IF NOT EXISTS profile_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT NOT NULL,
            guild_id TEXT NOT NULL DEFAULT '',
            author_id TEXT NOT NULL,
            category TEXT NOT NULL,
            fact_key TEXT NOT NULL,
            fact_value TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.7,
            source_message_ids TEXT NOT NULL DEFAULT '[]',
            first_seen_at REAL NOT NULL,
            last_confirmed_at REAL NOT NULL,
            expires_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_profile_facts_user
            ON profile_facts(account, guild_id, author_id, confidence DESC);

        CREATE TABLE IF NOT EXISTS profile_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT NOT NULL,
            guild_id TEXT NOT NULL DEFAULT '',
            author_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_profile_events_user_time
            ON profile_events(account, guild_id, author_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS profile_buffers (
            account TEXT NOT NULL,
            guild_id TEXT NOT NULL DEFAULT '',
            author_id TEXT NOT NULL,
            messages_json TEXT NOT NULL DEFAULT '[]',
            exchange_count INTEGER NOT NULL DEFAULT 0,
            last_user_at REAL NOT NULL,
            last_bot_reply_at REAL NOT NULL DEFAULT 0,
            flush_after REAL NOT NULL,
            PRIMARY KEY (account, guild_id, author_id)
        );

        CREATE TABLE IF NOT EXISTS profile_pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account TEXT NOT NULL,
            guild_id TEXT NOT NULL DEFAULT '',
            author_id TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL,
            processed INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_profile_pending_open
            ON profile_pending(processed, created_at ASC);
    """)
    _migrate_global_profiles(conn)


def _row_to_profile(row) -> dict:
    if not row:
        return {}
    d = dict(row)
    for key in ("topics_positive", "topics_negative"):
        try:
            d[key] = json.loads(d.get(key) or "{}")
        except (TypeError, json.JSONDecodeError):
            d[key] = {}
    return d


def get_profile(account: str, guild_id: str, author_id: str) -> Optional[dict]:
    init_db()
    gid = _profile_guild(guild_id)
    with _lock:
        row = connection().execute(
            """
            SELECT * FROM user_profiles
            WHERE account = ? AND guild_id = ? AND author_id = ?
            """,
            (account, gid, str(author_id)),
        ).fetchone()
    return _row_to_profile(row) if row else None


def upsert_profile_touch(
    account: str,
    guild_id: str,
    author_id: str,
    *,
    username: str = "",
    display_name: str = "",
    content: str = "",
    thread_reply_to_bot: bool = False,
) -> dict:
    """Increment counters and refresh display names; return updated profile."""
    init_db()
    gid = _profile_guild(guild_id)
    now = time.time()
    msg_len = len((content or "").strip())
    hour_utc = int(time.gmtime(now).tm_hour)

    with _lock:
        conn = connection()
        row = conn.execute(
            """
            SELECT * FROM user_profiles
            WHERE account = ? AND guild_id = ? AND author_id = ?
            """,
            (account, gid, str(author_id)),
        ).fetchone()

        if row:
            mc = int(row["message_count"]) + 1
            prev_avg = float(row["avg_message_length"] or 0)
            avg_len = ((prev_avg * (mc - 1)) + msg_len) / mc if mc else float(msg_len)
            fam = min(1.0, float(row["familiarity"]) + 0.008)
            warmth = float(row["warmth"])
            interest = float(row["interest"])
            if thread_reply_to_bot:
                warmth = min(1.0, warmth + 0.01)
                interest = min(1.0, interest + 0.015)
            conn.execute(
                """
                UPDATE user_profiles SET
                    username = ?, display_name = ?, last_seen_at = ?,
                    message_count = ?, avg_message_length = ?,
                    preferred_hour_utc = ?, familiarity = ?, warmth = ?, interest = ?
                WHERE account = ? AND guild_id = ? AND author_id = ?
                """,
                (
                    username or row["username"],
                    display_name or row["display_name"],
                    now,
                    mc,
                    avg_len,
                    hour_utc,
                    fam,
                    warmth,
                    interest,
                    account,
                    gid,
                    str(author_id),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO user_profiles (
                    account, guild_id, author_id, username, display_name,
                    first_seen_at, last_seen_at, message_count, avg_message_length,
                    preferred_hour_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    account,
                    gid,
                    str(author_id),
                    username,
                    display_name,
                    now,
                    now,
                    float(msg_len),
                    hour_utc,
                ),
            )
        conn.commit()

    return get_profile(account, guild_id, author_id) or {}


def record_bot_reply(account: str, guild_id: str, author_id: str) -> None:
    init_db()
    gid = _profile_guild(guild_id)
    now = time.time()
    with _lock:
        conn = connection()
        row = conn.execute(
            """
            SELECT reply_count, interest, familiarity, trust
            FROM user_profiles
            WHERE account = ? AND guild_id = ? AND author_id = ?
            """,
            (account, gid, str(author_id)),
        ).fetchone()
        if not row:
            return
        conn.execute(
            """
            UPDATE user_profiles SET
                reply_count = reply_count + 1,
                last_seen_at = ?,
                interest = MIN(1.0, interest + 0.02),
                familiarity = MIN(1.0, familiarity + 0.01),
                trust = MIN(1.0, trust + 0.005)
            WHERE account = ? AND guild_id = ? AND author_id = ?
            """,
            (now, account, gid, str(author_id)),
        )
        conn.commit()


def apply_disposition_delta(
    account: str,
    guild_id: str,
    author_id: str,
    deltas: dict,
    *,
    cap: float = 0.05,
) -> None:
    if not deltas:
        return
    init_db()
    gid = _profile_guild(guild_id)
    with _lock:
        conn = connection()
        row = conn.execute(
            """
            SELECT familiarity, warmth, trust, playfulness, patience, interest
            FROM user_profiles
            WHERE account = ? AND guild_id = ? AND author_id = ?
            """,
            (account, gid, str(author_id)),
        ).fetchone()
        if not row:
            return
        updates = {}
        for dim, rest in DISPOSITION_REST.items():
            raw = deltas.get(dim)
            if raw is None:
                continue
            try:
                delta = max(-cap, min(cap, float(raw)))
            except (TypeError, ValueError):
                continue
            current = float(row[dim])
            updates[dim] = max(0.0, min(1.0, current + delta))
        if not updates:
            return
        sets = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE user_profiles SET {sets} WHERE account = ? AND guild_id = ? AND author_id = ?",
            (*updates.values(), account, gid, str(author_id)),
        )
        conn.commit()


def apply_outcome_delta(account: str, guild_id: str, author_id: str, outcome: str) -> None:
    deltas = {
        "ignored": {"interest": -0.008},
        "react_only": {"interest": -0.003},
        "replied": {},
    }.get(outcome, {})
    apply_disposition_delta(account, guild_id, author_id, deltas, cap=0.02)


def decay_dispositions(account: str = "", max_rows: int = 200) -> int:
    """Drift disposition dimensions toward resting values."""
    init_db()
    changed = 0
    with _lock:
        conn = connection()
        if account:
            rows = conn.execute(
                """
                SELECT account, guild_id, author_id,
                       familiarity, warmth, trust, playfulness, patience, interest
                FROM user_profiles
                WHERE account = ? AND last_seen_at > ?
                LIMIT ?
                """,
                (account, time.time() - 90 * 86400, max_rows),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT account, guild_id, author_id,
                       familiarity, warmth, trust, playfulness, patience, interest
                FROM user_profiles
                WHERE last_seen_at > ?
                LIMIT ?
                """,
                (time.time() - 90 * 86400, max_rows),
            ).fetchall()
        for row in rows:
            new_vals = {}
            for dim, rest in DISPOSITION_REST.items():
                current = float(row[dim])
                if abs(current - rest) < 0.005:
                    continue
                step = 0.01
                if current > rest:
                    new_vals[dim] = max(rest, current - step)
                else:
                    new_vals[dim] = min(rest, current + step)
            if not new_vals:
                continue
            sets = ", ".join(f"{k} = ?" for k in new_vals)
            conn.execute(
                f"""
                UPDATE user_profiles SET {sets}
                WHERE account = ? AND guild_id = ? AND author_id = ?
                """,
                (*new_vals.values(), row["account"], row["guild_id"], row["author_id"]),
            )
            changed += 1
        if changed:
            conn.commit()
    return changed


def add_fact(
    account: str,
    guild_id: str,
    author_id: str,
    category: str,
    fact_key: str,
    fact_value: str,
    *,
    confidence: float = 0.7,
    source_message_ids: list = None,
    expires_at: float = None,
) -> int:
    init_db()
    now = time.time()
    cat = (category or "preference").strip()[:40]
    key = (fact_key or "note").strip()[:80]
    val = (fact_value or "").strip()[:500]
    if not val:
        return 0
    conf = max(0.0, min(1.0, float(confidence)))
    gid = _profile_guild(guild_id)
    with _lock:
        conn = connection()
        existing = conn.execute(
            """
            SELECT id, confidence FROM profile_facts
            WHERE account = ? AND guild_id = ? AND author_id = ?
              AND category = ? AND fact_key = ? AND fact_value = ?
            """,
            (account, gid, str(author_id), cat, key, val),
        ).fetchone()
        if existing:
            new_conf = min(1.0, float(existing["confidence"]) + 0.1)
            conn.execute(
                """
                UPDATE profile_facts SET confidence = ?, last_confirmed_at = ?
                WHERE id = ?
                """,
                (new_conf, now, existing["id"]),
            )
            conn.commit()
            return int(existing["id"])
        cur = conn.execute(
            """
            INSERT INTO profile_facts (
                account, guild_id, author_id, category, fact_key, fact_value,
                confidence, source_message_ids, first_seen_at, last_confirmed_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account,
                gid,
                str(author_id),
                cat,
                key,
                val,
                conf,
                json.dumps(source_message_ids or []),
                now,
                now,
                expires_at,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def lower_fact_confidence(fact_id: int, *, amount: float = 0.25) -> None:
    init_db()
    with _lock:
        conn = connection()
        conn.execute(
            """
            UPDATE profile_facts SET confidence = MAX(0, confidence - ?)
            WHERE id = ?
            """,
            (amount, int(fact_id)),
        )
        conn.commit()


def get_facts(
    account: str,
    guild_id: str,
    author_id: str,
    *,
    min_confidence: float = 0.6,
    limit: int = 20,
) -> list:
    init_db()
    gid = _profile_guild(guild_id)
    now = time.time()
    with _lock:
        rows = connection().execute(
            """
            SELECT id, category, fact_key, fact_value, confidence
            FROM profile_facts
            WHERE account = ? AND guild_id = ? AND author_id = ?
              AND confidence >= ?
              AND (expires_at IS NULL OR expires_at > ?)
            ORDER BY confidence DESC, last_confirmed_at DESC
            LIMIT ?
            """,
            (account, gid, str(author_id), min_confidence, now, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def search_facts(
    account: str,
    guild_id: str,
    author_id: str,
    query: str,
    *,
    min_confidence: float = 0.6,
    limit: int = 5,
) -> list:
    facts = get_facts(account, guild_id, author_id, min_confidence=min_confidence, limit=50)
    if not query:
        return facts[:limit]
    words = {w.lower() for w in query.split() if len(w) >= 3}
    if not words:
        return facts[:limit]
    scored = []
    for f in facts:
        blob = f"{f['category']} {f['fact_key']} {f['fact_value']}".lower()
        score = sum(1 for w in words if w in blob)
        if score:
            scored.append((score, f))
    scored.sort(key=lambda x: (-x[0], -x[1]["confidence"]))
    return [f for _, f in scored[:limit]]


def update_summaries(
    account: str,
    guild_id: str,
    author_id: str,
    *,
    summary_l1: str = "",
    summary_l2: str = "",
) -> None:
    init_db()
    gid = _profile_guild(guild_id)
    now = time.time()
    with _lock:
        conn = connection()
        conn.execute(
            """
            UPDATE user_profiles SET
                summary_l1 = COALESCE(NULLIF(?, ''), summary_l1),
                summary_l2 = COALESCE(NULLIF(?, ''), summary_l2),
                summary_updated_at = ?
            WHERE account = ? AND guild_id = ? AND author_id = ?
            """,
            (
                (summary_l1 or "")[:800],
                (summary_l2 or "")[:1600],
                now,
                account,
                gid,
                str(author_id),
            ),
        )
        conn.commit()


def log_event(account: str, guild_id: str, author_id: str, event_type: str, detail: str = "") -> None:
    init_db()
    gid = _profile_guild(guild_id)
    with _lock:
        conn = connection()
        conn.execute(
            """
            INSERT INTO profile_events (account, guild_id, author_id, event_type, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (account, gid, str(author_id), event_type, (detail or "")[:500], time.time()),
        )
        conn.commit()


def append_buffer_message(
    account: str,
    guild_id: str,
    author_id: str,
    message: dict,
) -> None:
    init_db()
    gid = _profile_guild(guild_id)
    now = time.time()
    with _lock:
        conn = connection()
        row = conn.execute(
            """
            SELECT messages_json, exchange_count FROM profile_buffers
            WHERE account = ? AND guild_id = ? AND author_id = ?
            """,
            (account, gid, str(author_id)),
        ).fetchone()
        if row:
            try:
                msgs = json.loads(row["messages_json"] or "[]")
            except (TypeError, json.JSONDecodeError):
                msgs = []
            msgs.append(message)
            msgs = msgs[-40:]
            conn.execute(
                """
                UPDATE profile_buffers SET
                    messages_json = ?, last_user_at = ?, flush_after = ?
                WHERE account = ? AND guild_id = ? AND author_id = ?
                """,
                (
                    json.dumps(msgs),
                    now,
                    now + BUFFER_IDLE_SECS,
                    account,
                    gid,
                    str(author_id),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO profile_buffers (
                    account, guild_id, author_id, messages_json,
                    exchange_count, last_user_at, flush_after
                ) VALUES (?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    account,
                    gid,
                    str(author_id),
                    json.dumps([message]),
                    now,
                    now + BUFFER_IDLE_SECS,
                ),
            )
        conn.commit()


def note_buffer_bot_reply(account: str, guild_id: str, author_id: str) -> None:
    init_db()
    gid = _profile_guild(guild_id)
    now = time.time()
    with _lock:
        conn = connection()
        conn.execute(
            """
            UPDATE profile_buffers SET
                exchange_count = exchange_count + 1,
                last_bot_reply_at = ?
            WHERE account = ? AND guild_id = ? AND author_id = ?
            """,
            (now, account, gid, str(author_id)),
        )
        conn.commit()


def enqueue_distill(account: str, guild_id: str, author_id: str, reason: str = "") -> None:
    init_db()
    gid = _profile_guild(guild_id)
    with _lock:
        conn = connection()
        conn.execute(
            """
            INSERT INTO profile_pending (account, guild_id, author_id, reason, created_at, processed)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (account, gid, str(author_id), (reason or "")[:120], time.time()),
        )
        conn.commit()


def list_ready_buffers() -> list:
    init_db()
    now = time.time()
    with _lock:
        rows = connection().execute(
            """
            SELECT account, guild_id, author_id, exchange_count, last_user_at
            FROM profile_buffers
            WHERE flush_after <= ? OR exchange_count >= 3
            """,
            (now,),
        ).fetchall()
    return [dict(r) for r in rows]


def clear_buffer(account: str, guild_id: str, author_id: str) -> None:
    init_db()
    gid = _profile_guild(guild_id)
    with _lock:
        conn = connection()
        conn.execute(
            "DELETE FROM profile_buffers WHERE account = ? AND guild_id = ? AND author_id = ?",
            (account, gid, str(author_id)),
        )
        conn.commit()


def fetch_pending_distills(limit: int = 8) -> list:
    init_db()
    with _lock:
        rows = connection().execute(
            """
            SELECT id, account, guild_id, author_id, reason
            FROM profile_pending
            WHERE processed = 0
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (max(1, min(50, int(limit))),),
        ).fetchall()
    return [dict(r) for r in rows]


def mark_pending_processed(pending_id: int) -> None:
    init_db()
    with _lock:
        conn = connection()
        conn.execute(
            "UPDATE profile_pending SET processed = 1 WHERE id = ?",
            (int(pending_id),),
        )
        conn.commit()


def forget_user(account: str, guild_id: str, author_id: str) -> None:
    """Wipe a user's global profile (all servers)."""
    init_db()
    aid = str(author_id)
    with _lock:
        conn = connection()
        conn.execute(
            "DELETE FROM user_profiles WHERE account = ? AND author_id = ?",
            (account, aid),
        )
        conn.execute(
            "DELETE FROM profile_facts WHERE account = ? AND author_id = ?",
            (account, aid),
        )
        conn.execute(
            "DELETE FROM profile_events WHERE account = ? AND author_id = ?",
            (account, aid),
        )
        conn.execute(
            "DELETE FROM profile_buffers WHERE account = ? AND author_id = ?",
            (account, aid),
        )
        conn.execute(
            "DELETE FROM profile_pending WHERE account = ? AND author_id = ?",
            (account, aid),
        )
        conn.commit()


def bump_topics_positive(account: str, guild_id: str, author_id: str, topics: set) -> None:
    if not topics:
        return
    profile = get_profile(account, guild_id, author_id)
    if not profile:
        return
    pos = dict(profile.get("topics_positive") or {})
    for t in topics:
        pos[t] = pos.get(t, 0.0) + 0.5
    init_db()
    gid = _profile_guild(guild_id)
    with _lock:
        connection().execute(
            """
            UPDATE user_profiles SET topics_positive = ?
            WHERE account = ? AND guild_id = ? AND author_id = ?
            """,
            (json.dumps(pos)[:4000], account, gid, str(author_id)),
        )
        connection().commit()


def list_profiles(
    *,
    account: str = "",
    guild_id: str = "",
    limit: int = 100,
) -> list:
    """List recently active global user profiles for UI inspection."""
    init_db()
    lim = max(1, min(500, int(limit)))
    gid = GLOBAL_PROFILE_GUILD
    with _lock:
        conn = connection()
        if guild_id:
            sql = """
                SELECT p.* FROM user_profiles p
                WHERE p.guild_id = ?
            """
            params: list = [gid]
            if account:
                sql += " AND p.account = ?"
                params.append(account)
            sql += """
                AND p.author_id IN (
                    SELECT DISTINCT author_id FROM channel_messages
                    WHERE account = p.account AND guild_id = ?
                      AND author_id != '' AND is_bot = 0
                )
                ORDER BY p.last_seen_at DESC
                LIMIT ?
            """
            params.extend([guild_id, lim])
            rows = conn.execute(sql, params).fetchall()
        elif account:
            rows = conn.execute(
                """
                SELECT * FROM user_profiles
                WHERE account = ? AND guild_id = ?
                ORDER BY last_seen_at DESC
                LIMIT ?
                """,
                (account, gid, lim),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM user_profiles
                WHERE guild_id = ?
                ORDER BY last_seen_at DESC
                LIMIT ?
                """,
                (gid, lim),
            ).fetchall()
    return [_row_to_profile(r) for r in rows]


def get_recent_events(
    account: str,
    guild_id: str,
    author_id: str,
    *,
    limit: int = 5,
) -> list:
    init_db()
    gid = _profile_guild(guild_id)
    with _lock:
        rows = connection().execute(
            """
            SELECT event_type, detail, created_at
            FROM profile_events
            WHERE account = ? AND guild_id = ? AND author_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (account, gid, str(author_id), max(1, min(20, int(limit)))),
        ).fetchall()
    return [dict(r) for r in rows]


def profile_stats() -> dict:
    init_db()
    with _lock:
        conn = connection()
        profiles = conn.execute("SELECT COUNT(*) AS c FROM user_profiles").fetchone()["c"]
        facts = conn.execute(
            "SELECT COUNT(*) AS c FROM profile_facts WHERE confidence >= 0.6"
        ).fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) AS c FROM profile_pending WHERE processed = 0"
        ).fetchone()["c"]
    return {
        "profile_count": int(profiles),
        "fact_count": int(facts),
        "pending_distills": int(pending),
    }
