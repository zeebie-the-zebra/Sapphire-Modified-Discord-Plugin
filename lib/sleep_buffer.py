"""Drain buffered @mentions after the bot wakes up."""

import logging
import random
import time

logger = logging.getLogger(__name__)

_WAKE_REPLY_GAP_MIN = 25.0
_WAKE_REPLY_GAP_MAX = 75.0


def drain_sleep_buffer(
    account: str,
    channel_id: str,
    guild_id: str,
    guild_name: str,
    channel_name: str,
    *,
    max_replies: int = 3,
) -> int:
    """Emit LLM events for up to max_replies newest buffered @mentions. Returns count sent."""
    from plugins.leona_discord.lib.events import build_event_payload, emit_event
    from plugins.leona_discord.lib.store import (
        count_pending_sleep_buffer,
        fetch_sleep_buffer,
        mark_all_sleep_buffer_processed,
        mark_sleep_buffer_processed,
    )

    pending = count_pending_sleep_buffer(account, channel_id)
    if pending <= 0:
        return 0

    rows = fetch_sleep_buffer(account, channel_id, limit=max_replies)
    if not rows:
        return 0

    skipped = pending - len(rows)
    if skipped > 0:
        logger.info(
            f"[LEONA-DISCORD] Sleep buffer: skipping {skipped} older @mention(s) "
            f"in #{channel_name or channel_id} (max {max_replies}/wake)"
        )

    sent = 0
    processed_ids = []
    for i, row in enumerate(rows):
        if i > 0:
            time.sleep(random.uniform(_WAKE_REPLY_GAP_MIN, _WAKE_REPLY_GAP_MAX))

        content = (row.get("content") or "").strip()
        if not content:
            processed_ids.append(row["id"])
            continue

        wrapped = (
            "[You were asleep overnight. This is a delayed reply to an @mention "
            f"from {row.get('display_name') or row.get('username') or 'someone'}.]\n\n"
            f"{content}"
        )

        payload = build_event_payload(
            account=account,
            guild_id=guild_id or row.get("guild_id", ""),
            guild_name=guild_name,
            channel_id=channel_id,
            channel_name=channel_name,
            message_id=row.get("message_id", ""),
            author_id=row.get("author_id", ""),
            username=row.get("username", ""),
            display_name=row.get("display_name", ""),
            content=wrapped,
            mentioned=True,
            image_urls=row.get("image_urls") or [],
            reply_to_message_id=row.get("message_id", ""),
        )
        if emit_event(payload):
            sent += 1
            logger.info(
                f"[LEONA-DISCORD] Sleep buffer reply queued ({sent}/{len(rows)}) "
                f"for #{channel_name or channel_id}"
            )
        processed_ids.append(row["id"])

    mark_sleep_buffer_processed(processed_ids)
    mark_all_sleep_buffer_processed(account, channel_id)
    return sent
