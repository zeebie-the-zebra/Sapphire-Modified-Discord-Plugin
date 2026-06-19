"""Cached reply context and reaction deduplication."""

from plugins.leona_discord.lib.constants import MAX_REACTED_ENTRIES
from plugins.leona_discord.lib import state


def get_reply_context(account: str, channel_id: str):
    key = state.channel_key(account, str(channel_id))
    with state._reply_contexts_lock:
        ctx = state._reply_contexts.get(key, {})
        return {
            "guild_id": ctx.get("guild_id", ""),
            "channel_id": ctx.get("channel_id", ""),
            "message_id": ctx.get("message_id", ""),
        }


def get_pending_payload(account: str, channel_id: str = ""):
    if channel_id:
        key = state.channel_key(account, str(channel_id))
        with state._pending_payloads_lock:
            payload = state._pending_payloads.get(key)
            if payload is not None:
                return dict(payload)
    with state._pending_payloads_lock:
        for key, payload in state._pending_payloads.items():
            if key.startswith(f"{account}:"):
                return dict(payload)
    return {}


def set_reply_context(channel_key: str, guild_id: str, channel_id: str, message_id: str):
    with state._reply_contexts_lock:
        state._reply_contexts[channel_key] = {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "message_id": message_id,
        }


def set_pending_payload(channel_key: str, payload: dict):
    with state._pending_payloads_lock:
        state._pending_payloads[channel_key] = payload


def clear_pending_payload(channel_key: str):
    with state._pending_payloads_lock:
        state._pending_payloads.pop(channel_key, None)


def has_reacted(account: str, channel_id: str, message_id: str, emoji: str) -> bool:
    entry = (state.channel_key(account, str(channel_id)), str(message_id), emoji)
    with state._reacted_messages_lock:
        return entry in state._reacted_messages


def mark_reacted(account: str, channel_id: str, message_id: str, emoji: str) -> bool:
    entry = (state.channel_key(account, str(channel_id)), str(message_id), emoji)
    with state._reacted_messages_lock:
        if entry in state._reacted_messages:
            return False
        if len(state._reacted_messages) >= MAX_REACTED_ENTRIES:
            evict = list(state._reacted_messages.keys())[:MAX_REACTED_ENTRIES // 2]
            for k in evict:
                del state._reacted_messages[k]
        state._reacted_messages[entry] = True
        return True
