"""Build and emit discord_message daemon events (batch + slash)."""

import json
import logging

from plugins.leona_discord.lib.context_cache import (
    clear_pending_payload,
    set_pending_payload,
    set_reply_context,
)
from plugins.leona_discord.lib.history import (
    build_mention_map,
    format_recent_history,
    get_history_snapshot,
    recent_message_ids,
    store_mention_map,
)
from plugins.leona_discord.lib import memory
from plugins.leona_discord.lib.reactions import build_reaction_hint
from plugins.leona_discord.lib.settings import get_effective_settings
from plugins.leona_discord.lib.typing_indicator import fire_typing
from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)


def build_event_payload(
    *,
    account: str,
    guild_id: str,
    guild_name: str,
    channel_id: str,
    channel_name: str,
    message_id: str,
    author_id: str,
    username: str,
    display_name: str,
    content: str,
    is_dm: bool = False,
    mentioned: bool = True,
    image_urls: list = None,
    slash_command: str = "",
    reply_to_message_id: str = "",
) -> dict:
    channel_key = state.channel_key(account, channel_id)
    effective = get_effective_settings(
        guild_id=guild_id,
        channel_id=channel_id,
        channel_name=channel_name,
        is_dm=is_dm,
        channel_key=channel_key,
    )

    combined = content
    if slash_command:
        combined = f"[Slash /{slash_command}]\n{combined}"

    if effective.get("append_to_user_message_enabled") and effective.get("append_to_user_message"):
        append_text = effective["append_to_user_message"].strip()
        if append_text:
            combined = combined + "\n" + append_text

    reaction_hint = build_reaction_hint(effective)
    full_history = get_history_snapshot(channel_key)
    skip_ids = recent_message_ids(full_history, guild_id)

    memory_context = memory.recall_context(
        account, guild_id, channel_id, combined,
        guild_name, channel_name,
        exclude_message_ids=skip_ids,
    )
    if memory_context:
        combined = f"{memory_context}\n\n{combined}"
    if reaction_hint:
        combined = f"{combined}\n\n{reaction_hint}"

    from plugins.leona_discord.lib.gifs import build_gif_hint
    gif_hint = build_gif_hint(guild_id)
    if gif_hint:
        combined = f"{combined}\n\n{gif_hint}"

    from plugins.leona_discord.lib.edit_history import build_message_edit_hint
    edit_hint = build_message_edit_hint(effective.get("message_edits_enabled", True))
    if edit_hint:
        combined = f"{combined}\n\n{edit_hint}"

    recent_history = format_recent_history(full_history, guild_id)
    msg_stub = [{"author_id": author_id, "username": username, "display_name": display_name}]
    mention_map = build_mention_map(full_history, msg_stub)
    store_mention_map(channel_key, mention_map)

    payload = {
        "account": account,
        "guild_id": guild_id,
        "guild_name": guild_name,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "message_id": message_id,
        "content": combined,
        "username": username,
        "display_name": display_name,
        "author_id": author_id,
        "is_dm": is_dm,
        "mentioned": str(mentioned),
        "recent_history": recent_history,
        "batch_size": 1,
        "history_size": len(full_history),
        "mention_map": mention_map,
        "memory_context": bool(memory_context),
        "image_urls": image_urls or [],
        "image_described": False,
        "slash_command": slash_command,
        "reply_to_message_id": reply_to_message_id or message_id,
    }

    from plugins.leona_discord.lib.bot_identity import enrich_payload_with_bot_identity
    enrich_payload_with_bot_identity(payload)
    return payload


def emit_event(payload: dict) -> bool:
    account = payload["account"]
    channel_id = payload["channel_id"]
    channel_key = state.channel_key(account, channel_id)

    fire_typing(account, int(channel_id))

    set_reply_context(
        channel_key,
        payload.get("guild_id", ""),
        channel_id,
        payload.get("message_id", ""),
    )
    set_pending_payload(channel_key, payload)

    loader = state.get_plugin_loader()
    if not loader:
        clear_pending_payload(channel_key)
        return False

    accepted = loader.emit_daemon_event("discord_message", json.dumps(payload))
    if not accepted:
        logger.info(
            f"[DISCORD] No task accepted event in #{payload.get('channel_name', channel_id)}"
        )
        clear_pending_payload(channel_key)
        return False
    return True
