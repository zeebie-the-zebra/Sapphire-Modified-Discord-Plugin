"""Self-contained SQLite memory — channel history, search, and debug traces."""

import json
import logging
import random
import re
import sqlite3
import threading
import time
from typing import Optional

from plugins.leona_discord.lib.constants import HISTORY_LIMIT
from plugins.leona_discord.lib.paths import get_sqlite_path

logger = logging.getLogger(__name__)

# Messages kept for live transcript injection
RECENT_LIMIT = HISTORY_LIMIT
# Older messages retained for memory search (self-contained long-term store)
MEMORY_RETENTION = 10_000

_conn: Optional[sqlite3.Connection] = None
_lock = threading.Lock()

_WORD_RE = re.compile(r"[a-z0-9']{2,}", re.I)


def init_db():
    global _conn
    with _lock:
        if _conn is not None:
            return
        path = get_sqlite_path()
        conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS channel_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT NOT NULL,
                guild_id TEXT NOT NULL DEFAULT '',
                channel_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                author_id TEXT DEFAULT '',
                username TEXT DEFAULT '',
                display_name TEXT DEFAULT '',
                content TEXT DEFAULT '',
                clean_content TEXT DEFAULT '',
                image_urls TEXT DEFAULT '[]',
                is_bot INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                UNIQUE(account, channel_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_cm_channel_time
                ON channel_messages(account, channel_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_cm_guild_time
                ON channel_messages(account, guild_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS debug_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                account TEXT DEFAULT '',
                guild_id TEXT DEFAULT '',
                channel_id TEXT DEFAULT '',
                channel_name TEXT DEFAULT '',
                message_id TEXT DEFAULT '',
                username TEXT DEFAULT '',
                mentioned INTEGER DEFAULT 0,
                outcome TEXT NOT NULL,
                gates TEXT DEFAULT '[]'
            );
            CREATE INDEX IF NOT EXISTS idx_trace_channel_time
                ON debug_traces(channel_id, ts DESC);

            CREATE TABLE IF NOT EXISTS pinned_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT NOT NULL,
                guild_id TEXT NOT NULL DEFAULT '',
                channel_id TEXT NOT NULL DEFAULT '',
                author_id TEXT DEFAULT '',
                username TEXT DEFAULT '',
                content TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pinned_guild
                ON pinned_memories(account, guild_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS outreach_log (
                account TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                sent_at REAL NOT NULL,
                PRIMARY KEY (account, channel_id)
            );

            CREATE TABLE IF NOT EXISTS sleep_state (
                account TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                is_asleep INTEGER NOT NULL DEFAULT 0,
                sleep_date TEXT NOT NULL DEFAULT '',
                scheduled_sleep_minute INTEGER NOT NULL DEFAULT -1,
                goodnight_sent INTEGER NOT NULL DEFAULT 0,
                forced_wake_until REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (account, channel_id)
            );

            CREATE TABLE IF NOT EXISTS sleep_mention_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account TEXT NOT NULL,
                guild_id TEXT NOT NULL DEFAULT '',
                channel_id TEXT NOT NULL,
                message_id TEXT NOT NULL,
                author_id TEXT DEFAULT '',
                username TEXT DEFAULT '',
                display_name TEXT DEFAULT '',
                content TEXT DEFAULT '',
                image_urls TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                processed INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_sleep_buffer_channel
                ON sleep_mention_buffer(account, channel_id, processed, created_at DESC);
        """)
        _migrate_sleep_state(conn)
        from plugins.leona_discord.lib.profile_store import ensure_profile_tables
        ensure_profile_tables(conn)
        conn.commit()
        _conn = conn
        logger.info(f"[LEONA-DISCORD] Memory store opened at {path}")


def _migrate_sleep_state(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sleep_state)").fetchall()}
    if "forced_wake_until" not in cols:
        conn.execute(
            "ALTER TABLE sleep_state ADD COLUMN forced_wake_until REAL NOT NULL DEFAULT 0"
        )


def _db() -> sqlite3.Connection:
    if _conn is None:
        init_db()
    return _conn


def connection() -> sqlite3.Connection:
    """Public accessor for the shared SQLite connection (profile store, etc.)."""
    return _db()


def save_message(account: str, guild_id: str, channel_id: str, msg_data: dict):
    with _lock:
        conn = _db()
        now = time.time()
        is_bot = 1 if msg_data.get("author_id") == "bot" or msg_data.get("is_bot") else 0
        conn.execute(
            """
            INSERT OR REPLACE INTO channel_messages
            (account, guild_id, channel_id, message_id, author_id, username, display_name,
             content, clean_content, image_urls, is_bot, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account,
                guild_id,
                channel_id,
                str(msg_data.get("message_id", "")),
                str(msg_data.get("author_id", "")),
                msg_data.get("username", ""),
                msg_data.get("display_name", ""),
                msg_data.get("content", ""),
                msg_data.get("clean_content", msg_data.get("content", "")),
                json.dumps(msg_data.get("image_urls") or []),
                is_bot,
                now,
            ),
        )
        conn.commit()
        _trim_channel(conn, account, channel_id, MEMORY_RETENTION)


def _trim_channel(conn, account: str, channel_id: str, keep: int):
    conn.execute(
        """
        DELETE FROM channel_messages
        WHERE account = ? AND channel_id = ? AND id NOT IN (
            SELECT id FROM channel_messages
            WHERE account = ? AND channel_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        )
        """,
        (account, channel_id, account, channel_id, keep),
    )
    conn.commit()


def _row_to_msg(r) -> dict:
    return {
        "message_id": r["message_id"],
        "content": r["content"] or "",
        "clean_content": r["clean_content"] or r["content"] or "",
        "username": r["username"] or "",
        "display_name": r["display_name"] or r["username"] or "",
        "author_id": r["author_id"] or "",
        "image_urls": json.loads(r["image_urls"] or "[]"),
        "is_bot": bool(r["is_bot"]),
        "channel_id": r["channel_id"],
        "guild_id": r["guild_id"],
        "created_at": r["created_at"],
    }


def get_last_human_message_at(account: str, channel_id: str) -> Optional[float]:
    """Unix timestamp of the most recent non-bot message, or None."""
    with _lock:
        conn = _db()
        row = conn.execute(
            """
            SELECT created_at FROM channel_messages
            WHERE account = ? AND channel_id = ? AND is_bot = 0
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (account, channel_id),
        ).fetchone()
    if not row:
        return None
    return float(row["created_at"])


def get_last_outreach_at(account: str, channel_id: str) -> Optional[float]:
    """Unix timestamp of the last proactive quiet-channel outreach, or None."""
    with _lock:
        conn = _db()
        row = conn.execute(
            """
            SELECT sent_at FROM outreach_log
            WHERE account = ? AND channel_id = ?
            """,
            (account, channel_id),
        ).fetchone()
    if not row:
        return None
    return float(row["sent_at"])


def record_outreach(account: str, channel_id: str, sent_at: float = None):
    ts = sent_at if sent_at is not None else time.time()
    with _lock:
        conn = _db()
        conn.execute(
            """
            INSERT INTO outreach_log (account, channel_id, sent_at)
            VALUES (?, ?, ?)
            ON CONFLICT(account, channel_id) DO UPDATE SET sent_at = excluded.sent_at
            """,
            (account, channel_id, ts),
        )
        conn.commit()


def _utc_date_str(ts: float = None) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).strftime("%Y-%m-%d")


def get_sleep_state(account: str, channel_id: str) -> dict:
    with _lock:
        conn = _db()
        row = conn.execute(
            """
            SELECT is_asleep, sleep_date, scheduled_sleep_minute, goodnight_sent, forced_wake_until
            FROM sleep_state WHERE account = ? AND channel_id = ?
            """,
            (account, channel_id),
        ).fetchone()
    if not row:
        return {
            "is_asleep": False,
            "sleep_date": "",
            "scheduled_sleep_minute": -1,
            "goodnight_sent": False,
            "forced_wake_until": 0.0,
        }
    return {
        "is_asleep": bool(row["is_asleep"]),
        "sleep_date": row["sleep_date"] or "",
        "scheduled_sleep_minute": int(row["scheduled_sleep_minute"]),
        "goodnight_sent": bool(row["goodnight_sent"]),
        "forced_wake_until": float(row["forced_wake_until"] or 0),
    }


def upsert_sleep_state(
    account: str,
    channel_id: str,
    *,
    is_asleep: bool = None,
    sleep_date: str = None,
    scheduled_sleep_minute: int = None,
    goodnight_sent: bool = None,
    forced_wake_until: float = None,
):
    current = get_sleep_state(account, channel_id)
    if is_asleep is not None:
        current["is_asleep"] = is_asleep
    if sleep_date is not None:
        current["sleep_date"] = sleep_date
    if scheduled_sleep_minute is not None:
        current["scheduled_sleep_minute"] = scheduled_sleep_minute
    if goodnight_sent is not None:
        current["goodnight_sent"] = goodnight_sent
    if forced_wake_until is not None:
        current["forced_wake_until"] = float(forced_wake_until)
    with _lock:
        conn = _db()
        conn.execute(
            """
            INSERT INTO sleep_state
                (account, channel_id, is_asleep, sleep_date, scheduled_sleep_minute,
                 goodnight_sent, forced_wake_until)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account, channel_id) DO UPDATE SET
                is_asleep = excluded.is_asleep,
                sleep_date = excluded.sleep_date,
                scheduled_sleep_minute = excluded.scheduled_sleep_minute,
                goodnight_sent = excluded.goodnight_sent,
                forced_wake_until = excluded.forced_wake_until
            """,
            (
                account,
                channel_id,
                1 if current["is_asleep"] else 0,
                current["sleep_date"],
                current["scheduled_sleep_minute"],
                1 if current["goodnight_sent"] else 0,
                current["forced_wake_until"],
            ),
        )
        conn.commit()


def account_has_asleep_channels(account: str) -> bool:
    with _lock:
        conn = _db()
        row = conn.execute(
            """
            SELECT 1 FROM sleep_state
            WHERE account = ? AND is_asleep = 1 AND channel_id NOT GLOB '_*'
            LIMIT 1
            """,
            (account,),
        ).fetchone()
    return row is not None


# Internal row for shared goodnight minute across all target channels
_SHARED_GOODNIGHT_ACCOUNT = "_schedule"
_SHARED_GOODNIGHT_CHANNEL = "_shared_goodnight"


def get_or_create_shared_goodnight_minute(sleep_date: str, choices: tuple) -> int:
    """Return one goodnight minute for all channels on this UTC date."""
    state = get_sleep_state(_SHARED_GOODNIGHT_ACCOUNT, _SHARED_GOODNIGHT_CHANNEL)
    if state.get("sleep_date") == sleep_date and state.get("scheduled_sleep_minute", -1) >= 0:
        return state["scheduled_sleep_minute"]
    minute = random.choice(choices)
    upsert_sleep_state(
        _SHARED_GOODNIGHT_ACCOUNT,
        _SHARED_GOODNIGHT_CHANNEL,
        sleep_date=sleep_date,
        scheduled_sleep_minute=minute,
        goodnight_sent=False,
        is_asleep=False,
    )
    return minute


def buffer_sleep_mention(
    account: str,
    guild_id: str,
    channel_id: str,
    message_id: str,
    author_id: str,
    username: str,
    display_name: str,
    content: str,
    image_urls: list = None,
) -> bool:
    with _lock:
        conn = _db()
        existing = conn.execute(
            """
            SELECT 1 FROM sleep_mention_buffer
            WHERE account = ? AND channel_id = ? AND message_id = ? AND processed = 0
            """,
            (account, channel_id, message_id),
        ).fetchone()
        if existing:
            return False
        conn.execute(
            """
            INSERT INTO sleep_mention_buffer
            (account, guild_id, channel_id, message_id, author_id, username,
             display_name, content, image_urls, created_at, processed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                account,
                guild_id,
                channel_id,
                message_id,
                author_id,
                username,
                display_name,
                content,
                json.dumps(image_urls or []),
                time.time(),
            ),
        )
        conn.commit()
    return True


def fetch_sleep_buffer(
    account: str,
    channel_id: str,
    *,
    limit: int = 3,
    unprocessed_only: bool = True,
) -> list:
    """Newest buffered @mentions first."""
    with _lock:
        conn = _db()
        where = "account = ? AND channel_id = ?"
        params: list = [account, channel_id]
        if unprocessed_only:
            where += " AND processed = 0"
        rows = conn.execute(
            f"""
            SELECT id, guild_id, message_id, author_id, username, display_name,
                   content, image_urls, created_at
            FROM sleep_mention_buffer
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (*params, max(1, limit)),
        ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "guild_id": r["guild_id"] or "",
            "message_id": r["message_id"],
            "author_id": r["author_id"] or "",
            "username": r["username"] or "",
            "display_name": r["display_name"] or "",
            "content": r["content"] or "",
            "image_urls": json.loads(r["image_urls"] or "[]"),
            "created_at": float(r["created_at"]),
        })
    return out


def mark_sleep_buffer_processed(ids: list[int]):
    if not ids:
        return
    with _lock:
        conn = _db()
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE sleep_mention_buffer SET processed = 1 WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()


def mark_all_sleep_buffer_processed(account: str, channel_id: str):
    with _lock:
        conn = _db()
        conn.execute(
            """
            UPDATE sleep_mention_buffer SET processed = 1
            WHERE account = ? AND channel_id = ? AND processed = 0
            """,
            (account, channel_id),
        )
        conn.commit()


def count_pending_sleep_buffer(account: str, channel_id: str) -> int:
    with _lock:
        conn = _db()
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM sleep_mention_buffer
            WHERE account = ? AND channel_id = ? AND processed = 0
            """,
            (account, channel_id),
        ).fetchone()
    return int(row["c"]) if row else 0


def count_sleep_mentions_in_window(
    account: str,
    channel_id: str,
    window_minutes: int,
) -> int:
    """Count buffered @mentions in the rolling window (for forced-wake threshold)."""
    since = time.time() - max(1, window_minutes) * 60
    with _lock:
        conn = _db()
        row = conn.execute(
            """
            SELECT COUNT(*) AS c FROM sleep_mention_buffer
            WHERE account = ? AND channel_id = ? AND created_at >= ?
            """,
            (account, channel_id, since),
        ).fetchone()
    return int(row["c"]) if row else 0


def mark_sleep_buffer_message_processed(account: str, channel_id: str, message_id: str):
    with _lock:
        conn = _db()
        conn.execute(
            """
            UPDATE sleep_mention_buffer SET processed = 1
            WHERE account = ? AND channel_id = ? AND message_id = ? AND processed = 0
            """,
            (account, channel_id, message_id),
        )
        conn.commit()


def get_recent_messages(account: str, channel_id: str, limit: int = RECENT_LIMIT) -> list:
    """Return the most recent `limit` messages, oldest-first for transcript order."""
    with _lock:
        conn = _db()
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT * FROM channel_messages
                WHERE account = ? AND channel_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            ) sub
            ORDER BY created_at ASC
            """,
            (account, channel_id, limit),
        ).fetchall()
    return [_row_to_msg(r) for r in rows]


def clear_channel(account: str, channel_id: str):
    with _lock:
        conn = _db()
        conn.execute(
            "DELETE FROM channel_messages WHERE account = ? AND channel_id = ?",
            (account, channel_id),
        )
        conn.commit()


def _query_words(query: str) -> list:
    return list(dict.fromkeys(_WORD_RE.findall((query or "").lower())))[:24]


def _score_row(text: str, words: list, age_hours: float) -> float:
    if not words:
        return 0.0
    lower = (text or "").lower()
    hits = sum(1 for w in words if w in lower)
    if hits == 0:
        return 0.0
    recency = max(0.1, 1.0 / (1.0 + age_hours / 48.0))
    return (hits / len(words)) * recency


def search_memory(account: str, guild_id: str, channel_id: str,
                  query: str, limit: int = 5, min_score: float = 0.2,
                  exclude_message_ids: set = None) -> list:
    """Rank past messages by keyword overlap + recency. Fully self-contained."""
    words = _query_words(query)
    if not words:
        return []
    exclude = exclude_message_ids or set()

    now = time.time()
    with _lock:
        conn = _db()
        channel_rows = conn.execute(
            """
            SELECT * FROM channel_messages
            WHERE account = ? AND channel_id = ?
            ORDER BY created_at DESC
            LIMIT 500
            """,
            (account, channel_id),
        ).fetchall()
        guild_rows = []
        if guild_id:
            guild_rows = conn.execute(
                """
                SELECT * FROM channel_messages
                WHERE account = ? AND guild_id = ? AND channel_id != ?
                ORDER BY created_at DESC
                LIMIT 200
                """,
                (account, guild_id, channel_id),
            ).fetchall()

    scored = []
    seen_ids = set()
    for r in channel_rows:
        msg = _row_to_msg(r)
        if msg["message_id"] in exclude:
            continue
        text = msg["clean_content"] or msg["content"]
        age_h = (now - float(r["created_at"])) / 3600.0
        score = _score_row(text, words, age_h)
        if score >= min_score:
            scored.append((score * 1.2, msg, "channel"))
            seen_ids.add(msg["message_id"])

    for r in guild_rows:
        msg = _row_to_msg(r)
        if msg["message_id"] in seen_ids:
            continue
        text = msg["clean_content"] or msg["content"]
        age_h = (now - float(r["created_at"])) / 3600.0
        score = _score_row(text, words, age_h)
        if score >= min_score:
            scored.append((score, msg, "guild"))
            seen_ids.add(msg["message_id"])

    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, msg, scope in scored[:limit]:
        who = msg["display_name"] or msg["username"] or "Unknown"
        label = f"{who}"
        if scope == "guild":
            label += f" (other channel)"
        out.append({
            "content": msg["clean_content"] or msg["content"],
            "username": label,
            "score": round(score, 3),
        })
    return out


def message_count(account: str = "") -> int:
    with _lock:
        conn = _db()
        if account:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM channel_messages WHERE account = ?",
                (account,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS c FROM channel_messages").fetchone()
    return int(row["c"]) if row else 0


def save_trace(trace: dict):
    with _lock:
        conn = _db()
        conn.execute(
            """
            INSERT INTO debug_traces
            (ts, account, guild_id, channel_id, channel_name, message_id, username,
             mentioned, outcome, gates)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace.get("ts", time.time()),
                trace.get("account", ""),
                trace.get("guild_id", ""),
                trace.get("channel_id", ""),
                trace.get("channel_name", ""),
                trace.get("message_id", ""),
                trace.get("username", ""),
                1 if trace.get("mentioned") else 0,
                trace.get("outcome", "unknown"),
                json.dumps(trace.get("gates") or []),
            ),
        )
        conn.commit()
        conn.execute(
            "DELETE FROM debug_traces WHERE ts < ?",
            (time.time() - 7 * 86400,),
        )
        conn.commit()


def list_traces(channel_id: str = "", limit: int = 50) -> list:
    with _lock:
        conn = _db()
        if channel_id:
            rows = conn.execute(
                """
                SELECT * FROM debug_traces WHERE channel_id = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (channel_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM debug_traces ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def save_pinned_memory(account: str, guild_id: str, channel_id: str,
                       author_id: str, username: str, content: str) -> int:
    text = (content or "").strip()
    if not text:
        return 0
    with _lock:
        conn = _db()
        cur = conn.execute(
            """
            INSERT INTO pinned_memories
            (account, guild_id, channel_id, author_id, username, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (account, guild_id, channel_id, author_id, username, text[:4000], time.time()),
        )
        conn.commit()
        return cur.lastrowid


def get_pinned_memories(account: str, guild_id: str = "", channel_id: str = "",
                        limit: int = 10) -> list:
    with _lock:
        conn = _db()
        if guild_id:
            rows = conn.execute(
                """
                SELECT content, username, created_at FROM pinned_memories
                WHERE account = ? AND guild_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (account, guild_id, limit),
            ).fetchall()
        elif channel_id:
            rows = conn.execute(
                """
                SELECT content, username, created_at FROM pinned_memories
                WHERE account = ? AND channel_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (account, channel_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT content, username, created_at FROM pinned_memories
                WHERE account = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (account, limit),
            ).fetchall()
    return [{"content": r["content"], "username": r["username"]} for r in rows]


def pinned_count(account: str = "") -> int:
    with _lock:
        conn = _db()
        if account:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM pinned_memories WHERE account = ?",
                (account,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS c FROM pinned_memories").fetchone()
    return int(row["c"]) if row else 0


def fetch_user_messages(
    account: str,
    guild_id: str,
    author_id: str,
    *,
    limit: int = 30,
) -> list:
    """Recent messages from a user across all guilds/DMs (for profile distillation)."""
    with _lock:
        conn = _db()
        rows = conn.execute(
            """
            SELECT guild_id, channel_id, content, username, display_name, created_at
            FROM channel_messages
            WHERE account = ? AND author_id = ? AND is_bot = 0
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (account, str(author_id), max(1, min(100, int(limit)))),
        ).fetchall()
    return [dict(r) for r in rows]
