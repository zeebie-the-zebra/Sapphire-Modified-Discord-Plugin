"""Custom emoji resolution and @name mention replacement."""

import re

from plugins.leona_discord.lib import state

_SNOWFLAKE_RE = re.compile(r"^\d{17,20}$")
_ANGLE_MENTION_RE = re.compile(r"<@!?([^>]+)>")
# Fallback when name is not in the lookup table — multi-word display names.
_BARE_AT_FALLBACK_RE = re.compile(
    r"@([\w][\w .'\u2019-]*?)"
    r"(?=\s*[—–-]|\s{2,}|[,.;:!?)\]]|\s+and\s|\s+or\s|$)",
    re.UNICODE | re.IGNORECASE,
)


def mentioned_users_from_discord(message) -> list[dict]:
    """Discord message.mentions as serializable dicts for the mention map."""
    out = []
    for user in getattr(message, "mentions", None) or []:
        out.append({
            "id": str(user.id),
            "username": user.name or "",
            "display_name": getattr(user, "display_name", None) or user.name or "",
        })
    return out


def merge_user_into_mention_map(
    mention_map: dict,
    user_id: str,
    *,
    username: str = "",
    display_name: str = "",
) -> None:
    if not user_id:
        return
    uid = str(user_id)
    if username:
        mention_map[username.strip().lower()] = uid
    dname = (display_name or "").strip()
    uname = (username or "").strip()
    if dname and dname.lower() != uname.lower():
        mention_map[dname.lower()] = uid


def resolve_custom_emoji(guild_id: str, emoji_input: str) -> str:
    if not emoji_input.startswith("<"):
        return emoji_input

    emoji_str = emoji_input.strip("<>")
    is_animated = emoji_str.startswith("a:")
    if is_animated:
        emoji_str = emoji_str[2:]

    parts = emoji_str.split(":")
    if len(parts) < 2:
        return emoji_input

    emoji_name = parts[1].lower()

    for client in state._clients.values():
        if not client.is_ready():
            continue
        guild = client.get_guild(int(guild_id)) if guild_id else None
        if not guild:
            for g in client.guilds:
                if str(g.id) == str(guild_id):
                    guild = g
                    break
        if guild:
            for emoji in guild.emojis:
                if emoji.name.lower() == emoji_name:
                    prefix = "<a:" if emoji.animated else "<:"
                    return f"{prefix}{emoji.name}:{emoji.id}>"
            break

    return emoji_input


def _get_guild(account: str, guild_id: str):
    client_ref = state._clients.get(account) if account else None
    if not client_ref or not client_ref.is_ready() or not guild_id:
        return None
    try:
        return client_ref.get_guild(int(guild_id))
    except (TypeError, ValueError):
        return None


def resolve_guild_for_channel(account: str, channel_id: str):
    client_ref = state._clients.get(account) if account else None
    if not client_ref or not client_ref.is_ready():
        return None
    try:
        ch_id_int = int(str(channel_id).strip())
    except (TypeError, ValueError):
        return None
    for guild in client_ref.guilds:
        if guild.get_channel(ch_id_int):
            return guild
    return None


def resolve_user_id(name: str, mention_map: dict, guild) -> str | None:
    key = (name or "").strip().lower()
    if not key:
        return None
    uid = mention_map.get(key)
    if uid:
        return str(uid)
    if guild:
        member = guild.get_member_named(name.strip())
        if member:
            mention_map[key] = str(member.id)
            return str(member.id)
    return None


def _lookup_name_keys(mention_map: dict, guild) -> list[str]:
    keys = set(mention_map.keys())
    if guild:
        for member in guild.members:
            keys.add(member.display_name.lower())
            keys.add(member.name.lower())
    return sorted(keys, key=len, reverse=True)


def _replace_angle_mentions(text: str, mention_map: dict, guild) -> str:
    def _fix(match):
        inner = match.group(1).strip()
        if _SNOWFLAKE_RE.match(inner):
            return match.group(0)
        uid = resolve_user_id(inner, mention_map, guild)
        return f"<@{uid}>" if uid else match.group(0)

    return _ANGLE_MENTION_RE.sub(_fix, text)


def _replace_bare_at_mentions(text: str, mention_map: dict, guild) -> str:
    if "@" not in text:
        return text

    lookup_keys = _lookup_name_keys(mention_map, guild)
    out = []
    i = 0
    n = len(text)

    while i < n:
        if text[i] == "@" and (i == 0 or text[i - 1] != "<"):
            rest_lower = text[i + 1 :].lower()
            matched = False
            for key in lookup_keys:
                if key and rest_lower.startswith(key):
                    end = i + 1 + len(key)
                    if end == n or text[end] in " \t\n,;:.!?)]'\"—–-":
                        uid = resolve_user_id(key, mention_map, guild)
                        if uid:
                            out.append(f"<@{uid}>")
                            i = end
                            matched = True
                            break
            if matched:
                continue

            m = _BARE_AT_FALLBACK_RE.match(text[i:])
            if m:
                candidate = m.group(1).strip()
                uid = resolve_user_id(candidate, mention_map, guild)
                if uid:
                    out.append(f"<@{uid}>")
                    i += m.end()
                    continue

        out.append(text[i])
        i += 1

    return "".join(out)


def apply_mention_map(text: str, mention_map: dict, account: str, guild_id: str) -> str:
    if not text:
        return text

    working = dict(mention_map or {})
    guild = _get_guild(account, guild_id)
    text = _replace_angle_mentions(text, working, guild)
    text = _replace_bare_at_mentions(text, working, guild)
    if mention_map is not None:
        mention_map.update(working)
    return text


def apply_mention_map_for_channel(
    text: str,
    channel_id: str,
    account: str = "",
    guild_id: str = "",
) -> str:
    """Resolve @name / <@name> mentions using the channel mention map + guild cache."""
    if not channel_id or not text:
        return text
    from plugins.leona_discord.lib.history import get_mention_map

    channel_id = str(channel_id).strip()
    if not account:
        with state._mention_maps_lock:
            for key in state._mention_maps:
                if key.endswith(f":{channel_id}"):
                    account = key.split(":", 1)[0]
                    break
        if not account:
            try:
                from plugins.leona_discord.daemon import list_connected
                connected = list_connected()
                if len(connected) == 1:
                    account = connected[0]
            except Exception:
                pass

    mmap = dict(get_mention_map(channel_id, account))
    if not guild_id and account:
        guild = resolve_guild_for_channel(account, channel_id)
        if guild:
            guild_id = str(guild.id)
    return apply_mention_map(text, mmap, account, guild_id)


def build_mention_format_hint() -> str:
    return (
        "When @mentioning other users, write @DisplayName only "
        "(e.g. @Spike le Vain). Do not use <@DisplayName> or made-up IDs — "
        "the plugin converts @DisplayName to real Discord pings."
    )
