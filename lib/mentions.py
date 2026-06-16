"""Custom emoji resolution and @name mention replacement."""

import re

from plugins.leona_discord.lib import state


def resolve_custom_emoji(guild_id: str, emoji_input: str) -> str:
    if not emoji_input.startswith('<'):
        return emoji_input

    emoji_str = emoji_input.strip('<>')
    is_animated = emoji_str.startswith('a:')
    if is_animated:
        emoji_str = emoji_str[2:]

    parts = emoji_str.split(':')
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
                    prefix = '<a:' if emoji.animated else '<:'
                    return f'{prefix}{emoji.name}:{emoji.id}>'
            break

    return emoji_input


def apply_mention_map(text: str, mention_map: dict, account: str, guild_id: str) -> str:
    if not text or (not mention_map and not guild_id):
        return text

    client_ref = state._clients.get(account)

    def _replace_mention(match):
        raw_name = match.group(1)
        name_lower = raw_name.lower().rstrip()
        uid = mention_map.get(name_lower)
        if uid:
            return f"<@{uid}>"
        if client_ref and client_ref.is_ready() and guild_id:
            guild = client_ref.get_guild(int(guild_id))
            if guild:
                raw_name_rstripped = raw_name.rstrip()
                for m in guild.members:
                    if (m.display_name.lower() == raw_name_rstripped.lower()
                            or m.name.lower() == raw_name_rstripped.lower()):
                        mention_map[name_lower] = str(m.id)
                        return f"<@{m.id}>"
        return match.group(0)

    return re.sub(
        r'@([A-Za-z0-9_. ]+?)(?=\s|$|[^A-Za-z0-9_. ])',
        _replace_mention,
        text,
    )
