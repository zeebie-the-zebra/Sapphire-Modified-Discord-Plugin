"""Capture Discord→LLM prompts and responses for the settings UI debug viewer."""

import json
import logging
import time
from typing import Optional

from plugins.leona_discord.lib.settings import get_plugin_settings
from plugins.leona_discord.lib.store import connection, init_db, _lock

logger = logging.getLogger(__name__)

_MAX_ROWS = 40
_MAX_TEXT = 120_000


def ensure_llm_debug_table(conn) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS llm_debug_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            account TEXT NOT NULL DEFAULT '',
            guild_id TEXT NOT NULL DEFAULT '',
            guild_name TEXT NOT NULL DEFAULT '',
            channel_id TEXT NOT NULL DEFAULT '',
            channel_name TEXT NOT NULL DEFAULT '',
            message_id TEXT NOT NULL DEFAULT '',
            username TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            formatted_prompt TEXT NOT NULL DEFAULT '',
            enriched_content TEXT NOT NULL DEFAULT '',
            trigger_content TEXT NOT NULL DEFAULT '',
            recent_history TEXT NOT NULL DEFAULT '[]',
            flags TEXT NOT NULL DEFAULT '{}',
            task_name TEXT NOT NULL DEFAULT '',
            task_prompt TEXT NOT NULL DEFAULT '',
            response_raw TEXT NOT NULL DEFAULT '',
            response_clean TEXT NOT NULL DEFAULT '',
            delivery_path TEXT NOT NULL DEFAULT '',
            discord_sent_text TEXT NOT NULL DEFAULT '',
            responded_at REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_llm_debug_time
            ON llm_debug_logs(ts DESC);
        CREATE INDEX IF NOT EXISTS idx_llm_debug_msg
            ON llm_debug_logs(account, channel_id, message_id, responded_at);
    """)
    _ensure_delivery_columns(conn)


def _ensure_delivery_columns(conn) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(llm_debug_logs)")}
    if "delivery_path" not in cols:
        conn.execute("ALTER TABLE llm_debug_logs ADD COLUMN delivery_path TEXT NOT NULL DEFAULT ''")
    if "discord_sent_text" not in cols:
        conn.execute("ALTER TABLE llm_debug_logs ADD COLUMN discord_sent_text TEXT NOT NULL DEFAULT ''")


def _enabled() -> bool:
    return get_plugin_settings().get("llm_debug_messaging_enabled", True)


def _clip(text: str, limit: int = _MAX_TEXT) -> str:
    s = (text or "")
    if len(s) <= limit:
        return s
    return s[: limit - 1] + "…"


def format_event_for_llm(payload: dict) -> str:
    """Same user-message formatting the continuity executor applies to daemon events."""
    try:
        from core.continuity.executor import ContinuityExecutor
        return ContinuityExecutor._format_event_data(json.dumps(payload))
    except Exception as e:
        logger.debug("[LEONA-DISCORD] llm_debug format fallback: %s", e)
        return payload.get("content") or ""


def record_outgoing(payload: dict, *, source: str = "batch") -> None:
    """Log the assembled Discord event payload before it is sent to the LLM task."""
    if not _enabled() or not payload:
        return
    try:
        init_db()
        formatted = _clip(format_event_for_llm(payload))
        history = payload.get("recent_history") or []
        if not isinstance(history, list):
            history = []
        flags = {
            "memory_context": bool(payload.get("memory_context")),
            "profile_context": bool(payload.get("profile_context")),
            "batch_size": int(payload.get("batch_size", 1) or 1),
            "history_size": int(payload.get("history_size", 0) or 0),
            "image_described": bool(payload.get("image_described")),
            "slash_command": (payload.get("slash_command") or "").strip(),
            "is_dm": bool(payload.get("is_dm")),
        }
        now = time.time()
        with _lock:
            conn = connection()
            conn.execute(
                """
                INSERT INTO llm_debug_logs (
                    ts, account, guild_id, guild_name, channel_id, channel_name,
                    message_id, username, source, formatted_prompt, enriched_content,
                    trigger_content, recent_history, flags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    payload.get("account", ""),
                    payload.get("guild_id", ""),
                    payload.get("guild_name", ""),
                    payload.get("channel_id", ""),
                    payload.get("channel_name", ""),
                    str(payload.get("message_id", "")),
                    payload.get("username", ""),
                    (source or "batch")[:40],
                    formatted,
                    _clip(payload.get("content") or ""),
                    _clip(payload.get("trigger_content") or payload.get("content") or ""),
                    json.dumps(history[:100]),
                    json.dumps(flags),
                ),
            )
            conn.execute(
                """
                DELETE FROM llm_debug_logs
                WHERE id NOT IN (
                    SELECT id FROM llm_debug_logs ORDER BY ts DESC LIMIT ?
                )
                """,
                (_MAX_ROWS,),
            )
            conn.commit()
    except Exception as e:
        logger.debug("[LEONA-DISCORD] llm_debug record_outgoing failed: %s", e)


def record_response(
    event_data: dict,
    *,
    response_raw: str = "",
    response_clean: str = "",
    task: Optional[dict] = None,
    delivery_path: str = "",
    discord_sent_text: str = "",
) -> None:
    """Attach LLM output (and task instructions if available) to the latest open log row."""
    if not _enabled() or not event_data:
        return
    account = event_data.get("account", "")
    channel_id = event_data.get("channel_id", "")
    message_id = str(event_data.get("message_id", ""))
    if not account or not channel_id:
        return
    task = task or {}
    try:
        init_db()
        now = time.time()
        with _lock:
            conn = connection()
            row = conn.execute(
                """
                SELECT id FROM llm_debug_logs
                WHERE account = ? AND channel_id = ? AND message_id = ? AND responded_at = 0
                ORDER BY ts DESC LIMIT 1
                """,
                (account, channel_id, message_id),
            ).fetchone()
            if not row:
                row = conn.execute(
                    """
                    SELECT id FROM llm_debug_logs
                    WHERE account = ? AND channel_id = ? AND responded_at = 0
                    ORDER BY ts DESC LIMIT 1
                    """,
                    (account, channel_id),
                ).fetchone()
            if not row:
                return
            conn.execute(
                """
                UPDATE llm_debug_logs SET
                    response_raw = ?,
                    response_clean = ?,
                    task_name = ?,
                    task_prompt = ?,
                    delivery_path = COALESCE(NULLIF(?, ''), delivery_path),
                    discord_sent_text = COALESCE(NULLIF(?, ''), discord_sent_text),
                    responded_at = ?
                WHERE id = ?
                """,
                (
                    _clip(response_raw or ""),
                    _clip(response_clean or ""),
                    _clip((task.get("name") or "")[:120], 120),
                    _clip(task.get("initial_message") or ""),
                    (delivery_path or "")[:40],
                    _clip(discord_sent_text or ""),
                    now,
                    int(row["id"]),
                ),
            )
            conn.commit()
    except Exception as e:
        logger.debug("[LEONA-DISCORD] llm_debug record_response failed: %s", e)


def _find_log_row_id(conn, account: str, channel_id: str, message_id: str):
    if message_id:
        row = conn.execute(
            """
            SELECT id FROM llm_debug_logs
            WHERE account = ? AND channel_id = ? AND message_id = ?
            ORDER BY ts DESC LIMIT 1
            """,
            (account, channel_id, message_id),
        ).fetchone()
        if row:
            return int(row["id"])
    row = conn.execute(
        """
        SELECT id FROM llm_debug_logs
        WHERE account = ? AND channel_id = ?
        ORDER BY ts DESC LIMIT 1
        """,
        (account, channel_id),
    ).fetchone()
    return int(row["id"]) if row else None


def record_post_send_edit(
    event_data: dict,
    *,
    kind: str,
    sent_text: str,
    corrected_text: str,
    delay_secs: float = 0,
    discord_message_id: str = "",
    applied: bool = False,
    error: str = "",
) -> None:
    """Attach post-send edit details (auto typo, LLM [edit:], random edit) to the debug log row."""
    if not _enabled() or not event_data or not kind:
        return
    account = event_data.get("account", "")
    channel_id = event_data.get("channel_id", "")
    message_id = str(event_data.get("message_id", ""))
    if not account or not channel_id:
        return
    try:
        init_db()
        now = time.time()
        with _lock:
            conn = connection()
            row_id = _find_log_row_id(conn, account, str(channel_id), message_id)
            if not row_id:
                return
            row = conn.execute(
                "SELECT flags FROM llm_debug_logs WHERE id = ?",
                (row_id,),
            ).fetchone()
            flags = {}
            if row:
                try:
                    flags = json.loads(row["flags"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    flags = {}
            existing = flags.get("post_send_edit") or {}
            payload = {
                "kind": (kind or "")[:40],
                "sent_text": _clip(sent_text or "", 8000),
                "corrected_text": _clip(corrected_text or "", 8000),
                "delay_secs": round(float(delay_secs or 0), 2),
                "discord_message_id": str(discord_message_id or existing.get("discord_message_id", "")),
                "planned_at": existing.get("planned_at") or (now if not applied else max(0, now - float(delay_secs or 0))),
                "applied": bool(applied),
                "applied_at": now if applied else int(existing.get("applied_at") or 0),
                "error": _clip(error or "", 500) if error else existing.get("error", ""),
            }
            if not applied and not existing.get("planned_at"):
                payload["planned_at"] = now
            flags["post_send_edit"] = payload
            conn.execute(
                "UPDATE llm_debug_logs SET flags = ? WHERE id = ?",
                (json.dumps(flags), row_id),
            )
            conn.commit()
    except Exception as e:
        logger.debug("[LEONA-DISCORD] llm_debug record_post_send_edit failed: %s", e)


def list_logs(*, limit: int = 25, channel_id: str = "") -> list:
    init_db()
    lim = max(1, min(100, int(limit)))
    with _lock:
        conn = connection()
        if channel_id:
            rows = conn.execute(
                """
                SELECT * FROM llm_debug_logs
                WHERE channel_id = ?
                ORDER BY ts DESC LIMIT ?
                """,
                (channel_id, lim),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM llm_debug_logs
                ORDER BY ts DESC LIMIT ?
                """,
                (lim,),
            ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        try:
            d["recent_history"] = json.loads(d.get("recent_history") or "[]")
        except (TypeError, json.JSONDecodeError):
            d["recent_history"] = []
        try:
            d["flags"] = json.loads(d.get("flags") or "{}")
        except (TypeError, json.JSONDecodeError):
            d["flags"] = {}
        out.append(d)
    return out
