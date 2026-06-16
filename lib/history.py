"""Persistent channel history and mention maps."""

from collections import deque

from plugins.leona_discord.lib.constants import HISTORY_LIMIT
from plugins.leona_discord.lib import store as sqlite_store
from plugins.leona_discord.lib import state

# Hot in-memory cache keyed by channel_key — synced to SQLite on write
_cache: dict = {}
_cache_lock = __import__('threading').Lock()


def _parse_channel_key(channel_key: str):
    parts = channel_key.split(":", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", channel_key


def append_message(channel_key: str, msg_data: dict, guild_id: str = ""):
    account, channel_id = _parse_channel_key(channel_key)
    with _cache_lock:
        if channel_key not in _cache:
            _cache[channel_key] = deque(maxlen=HISTORY_LIMIT)
            persisted = sqlite_store.get_recent_messages(account, channel_id, HISTORY_LIMIT)
            for m in persisted:
                _cache[channel_key].append(m)
        if not any(m.get("message_id") == msg_data.get("message_id") for m in _cache[channel_key]):
            _cache[channel_key].append(msg_data)
    sqlite_store.save_message(account, guild_id, channel_id, msg_data)


def get_history_snapshot(channel_key: str) -> list:
    account, channel_id = _parse_channel_key(channel_key)
    with _cache_lock:
        if channel_key in _cache:
            return list(_cache[channel_key])
    return sqlite_store.get_recent_messages(account, channel_id, HISTORY_LIMIT)


def store_mention_map(channel_key: str, mention_map: dict):
    with state._mention_maps_lock:
        state._mention_maps[channel_key] = mention_map


def get_mention_map(channel_id: str, account: str = "") -> dict:
    if account:
        key = state.channel_key(account, str(channel_id))
        with state._mention_maps_lock:
            if key in state._mention_maps:
                return dict(state._mention_maps[key])
    with state._mention_maps_lock:
        for key, mmap in state._mention_maps.items():
            if key.endswith(f":{channel_id}"):
                return dict(mmap)
    return {}


def clear_channel_history(account: str, channel_id: str):
    key = state.channel_key(account, channel_id)
    sqlite_store.clear_channel(account, channel_id)
    with _cache_lock:
        _cache.pop(key, None)


def append_bot_reply(channel_key: str, clean: str, account: str, bot_display: str,
                     guild_id: str = "", guild_name: str = "", channel_name: str = ""):
    msg_data = {
        "content": clean,
        "clean_content": clean,
        "username": account,
        "display_name": bot_display,
        "author_id": "bot",
        "is_bot": True,
        "message_id": f"bot-{__import__('time').time():.0f}",
    }
    append_message(channel_key, msg_data, guild_id=guild_id)


def build_mention_map(full_history: list, messages_to_send: list) -> dict:
    mention_map = {}
    for m in full_history + messages_to_send:
        aid = m.get("author_id", "")
        if not aid or aid == "bot":
            continue
        uname = m.get("username", "")
        dname = m.get("display_name", "")
        if uname:
            mention_map[uname.lower()] = aid
        if dname and dname.lower() != uname.lower():
            mention_map[dname.lower()] = aid
    return mention_map


def _inject_limits(guild_id: str = "") -> tuple:
    from plugins.leona_discord.lib.constants import DEFAULT_INJECT_LIMIT, DEFAULT_LINE_MAX_CHARS
    from plugins.leona_discord.lib.settings import get_effective_settings
    s = get_effective_settings(guild_id)
    limit = int(s.get("history_inject_limit", DEFAULT_INJECT_LIMIT))
    line_max = int(s.get("history_line_max_chars", DEFAULT_LINE_MAX_CHARS))
    return max(5, min(100, limit)), max(80, min(1000, line_max))


def format_recent_history(full_history: list, guild_id: str = "") -> list:
    """Build the LLM-facing transcript — capped count and per-line length."""
    inject_limit, line_max = _inject_limits(guild_id)
    window = full_history[-inject_limit:] if len(full_history) > inject_limit else full_history

    recent_history = []
    for m in window:
        who = m.get("display_name", m.get("username", "Unknown"))
        text = (m.get("clean_content") or m.get("content") or "").replace("\n", " ").strip()
        m_urls = m.get("image_urls") or []
        if m_urls:
            text = (text + (" " if text else "")) + f"(+{len(m_urls)} image)"
        line = f"{who}: {text}"
        if len(line) > line_max:
            line = line[: line_max - 1].rstrip() + "…"
        recent_history.append(line)
    return recent_history


def format_proactive_history(full_history: list, guild_id: str = "", account: str = "") -> list:
    """Recent chat for greeting/outreach — bot lines labeled as 'You'."""
    from plugins.leona_discord.lib.bot_identity import bot_identity_fields, bot_name_aliases

    fields = bot_identity_fields(account) if account else {}
    bot_names = {name.lower() for name in bot_name_aliases(fields)}

    inject_limit, line_max = _inject_limits(guild_id)
    window = full_history[-inject_limit:] if len(full_history) > inject_limit else full_history

    recent_history = []
    for m in window:
        who = m.get("display_name", m.get("username", "Unknown"))
        is_self = (
            m.get("is_bot")
            or str(m.get("author_id")) == "bot"
            or who.lower() in bot_names
        )
        if is_self:
            who = "You"
        text = (m.get("clean_content") or m.get("content") or "").replace("\n", " ").strip()
        m_urls = m.get("image_urls") or []
        if m_urls:
            text = (text + (" " if text else "")) + f"(+{len(m_urls)} image)"
        line = f"{who}: {text}"
        if len(line) > line_max:
            line = line[: line_max - 1].rstrip() + "…"
        recent_history.append(line)
    return recent_history


def recent_message_ids(full_history: list, guild_id: str = "") -> set:
    """Message IDs already in the injected transcript — skip in memory recall."""
    inject_limit, _ = _inject_limits(guild_id)
    window = full_history[-inject_limit:] if len(full_history) > inject_limit else full_history
    return {str(m.get("message_id", "")) for m in window if m.get("message_id")}
