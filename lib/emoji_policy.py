"""Allowed emoji policy — Unicode always OK; custom server emoji use the allowlist."""

import re

from plugins.leona_discord.lib.mentions import resolve_custom_emoji

_CUSTOM_EMOJI_RE = re.compile(r"^<a?:([^:>]+):(\d*)>$")


def is_custom_discord_emoji(emoji: str) -> bool:
    return bool(emoji) and str(emoji).strip().startswith("<")


def custom_emoji_name(emoji: str) -> str:
    """Extract emoji name from <:name:id>, <a:name:id>, or <:name:>."""
    text = (emoji or "").strip()
    match = _CUSTOM_EMOJI_RE.match(text)
    if match:
        return match.group(1)
    # Fallback for unusual formatting
    inner = text.strip("<>").strip()
    if inner.startswith("a:"):
        inner = inner[2:]
    parts = inner.split(":")
    return parts[0] if parts and parts[0] else ""


def custom_allowlist(settings: dict) -> list:
    """Server-configured custom Discord emoji codes (Unicode is not listed here)."""
    allowed = settings.get("allowed_emojis") or []
    return [str(e).strip() for e in allowed if isinstance(e, str) and e.strip().startswith("<")]


def _allowlist_names(codes: list) -> set:
    return {custom_emoji_name(code).lower() for code in codes if custom_emoji_name(code)}


def custom_emoji_permitted(emoji: str, settings: dict, guild_id: str = "") -> bool:
    """True if a custom Discord emoji is on the configured allowlist."""
    raw = (emoji or "").strip()
    if not is_custom_discord_emoji(raw):
        return False

    allowlist = custom_allowlist(settings)
    if not allowlist:
        return False

    resolved = resolve_custom_emoji(guild_id, raw)
    names = _allowlist_names(allowlist)
    name = custom_emoji_name(resolved).lower() or custom_emoji_name(raw).lower()

    if raw in allowlist or resolved in allowlist:
        return True
    return bool(name and name in names)


def emoji_is_allowed(emoji: str, settings: dict, guild_id: str = "") -> bool:
    """Unicode emoji are always allowed; custom emoji must be on the allowlist."""
    raw = (emoji or "").strip()
    if not raw:
        return False
    if not is_custom_discord_emoji(raw):
        return True
    return custom_emoji_permitted(raw, settings, guild_id)


def resolve_reaction_emoji(emoji: str, guild_id: str = "") -> str:
    """Resolve partial custom codes to full <:name:id> before sending to Discord."""
    raw = (emoji or "").strip()
    if is_custom_discord_emoji(raw):
        return resolve_custom_emoji(guild_id, raw)
    return raw


def pick_custom_reaction(settings: dict) -> str:
    """Pick a random allowed custom emoji, if any."""
    allowlist = custom_allowlist(settings)
    if not allowlist:
        return ""
    import random
    return random.choice(allowlist)
