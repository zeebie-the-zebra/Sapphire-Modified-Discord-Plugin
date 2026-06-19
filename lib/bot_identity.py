"""Bot self-identity hints for the reply LLM."""

import re

from plugins.leona_discord.lib import state


def _account_metadata(account: str) -> dict:
    loader = state.get_plugin_loader()
    if not loader:
        return {}
    try:
        plugin_state = loader.get_plugin_state("leona_discord") or {}
        return (plugin_state.get("accounts") or {}).get(account, {}) or {}
    except Exception:
        return {}


def bot_identity_fields(account: str) -> dict:
    """Resolve the connected bot's Discord identity for an account."""
    client = state._clients.get(account)
    if client and client.is_ready() and client.user:
        user = client.user
        return {
            "bot_id": str(user.id),
            "bot_username": user.name or "",
            "bot_display_name": user.display_name or user.name or "",
        }

    meta = _account_metadata(account)
    bot_id = str(meta.get("bot_id") or "").strip()
    bot_username = str(meta.get("bot_name") or "").strip()
    if not bot_id and not bot_username:
        return {}
    return {
        "bot_id": bot_id,
        "bot_username": bot_username,
        "bot_display_name": bot_username,
    }


def build_bot_identity_hint(fields: dict) -> str:
    """Short framing block so the model knows which Discord user it is."""
    bot_id = str(fields.get("bot_id") or "").strip()
    username = str(fields.get("bot_username") or "").strip()
    display_name = str(fields.get("bot_display_name") or "").strip() or username
    if not bot_id and not display_name:
        return ""

    who = display_name
    if username and username.lower() != display_name.lower():
        who = f"{display_name} (@{username})"

    lines = [f"You are {who} on Discord."]
    if bot_id:
        lines.append(f"Your Discord user ID is {bot_id}.")
        lines.append(f"Mentions like <@{bot_id}> refer to you.")
    if display_name:
        lines.append(
            f'Messages in "Recent chat" from "{display_name}" are your own prior '
            f"messages — speak about yourself in first person, not third person."
        )
    return "\n".join(lines)


def bot_display_name(client=None, account: str = "") -> str:
    """Human-readable bot name for UI strings and slash command descriptions."""
    if client is not None:
        user = getattr(client, "user", None)
        if user:
            for attr in ("global_name", "display_name", "name"):
                value = str(getattr(user, attr, None) or "").strip()
                if value:
                    return value

    account = str(account or "").strip()
    if account:
        fields = bot_identity_fields(account)
        for key in ("bot_display_name", "bot_username"):
            value = str(fields.get(key) or "").strip()
            if value:
                return value

    return "the bot"


def bot_name_aliases(fields: dict) -> list[str]:
    """Distinct non-empty display/username strings for the bot."""
    names: list[str] = []
    seen: set[str] = set()
    for key in ("bot_display_name", "bot_username"):
        value = str(fields.get(key) or "").strip()
        lower = value.lower()
        if value and lower not in seen:
            names.append(value)
            seen.add(lower)
    return names


def build_proactive_post_hint(fields: dict, *, purpose: str = "greeting") -> str:
    """Framing for greeting/outreach LLM — the bot is the speaker, not the audience."""
    names = bot_name_aliases(fields)
    if not names:
        return (
            "You are posting a proactive Discord message as this bot account. "
            "Address the humans in the channel, not yourself."
        )

    who = names[0]
    if len(names) > 1 and fields.get("bot_username"):
        username = str(fields.get("bot_username") or "").strip()
        if username and username != who:
            who = f"{who} (@{username})"

    lines = [
        f"You are {who} posting a message in this Discord channel.",
        "Write TO the people in the channel — you are the speaker, not the audience.",
    ]
    if purpose == "greeting":
        lines.append(
            "This is a good-morning style greeting for the channel or whoever is around — "
            "not a message to yourself."
        )
    elif purpose == "goodnight":
        lines.append(
            "This is a good-night sign-off for the channel — you are going to sleep until morning. "
            "Not a message to yourself."
        )
    else:
        lines.append(
            "Casually check in with the channel — do not address yourself by name."
        )

    quoted = ", ".join(f'"{name}"' for name in names)
    lines.append(f"Never greet or address {quoted} — that is you.")
    lines.append(
        'Lines labeled "You:" in recent chat are your own prior messages.'
    )
    return "\n".join(lines)


def strip_self_address(text: str, fields: dict) -> str:
    """Remove accidental self-greetings like 'Morning, Remmi —'."""
    out = (text or "").strip()
    if not out:
        return out

    for name in bot_name_aliases(fields):
        pattern = re.compile(
            rf"^((?:Good\s+)?Morning|Hey|Hi|Hello)\s*,?\s*{re.escape(name)}\s*(?:[,—–-]\s*)?",
            re.IGNORECASE,
        )
        out = pattern.sub(r"\1 — ", out, count=1)
        out = re.sub(
            rf",\s*{re.escape(name)}\s*([,—–-])",
            r" \1",
            out,
            count=1,
            flags=re.IGNORECASE,
        )
    return out.strip()


def enrich_payload_with_bot_identity(payload: dict) -> dict:
    """Add bot identity fields and prepend the self-identity hint to content."""
    account = str(payload.get("account") or "").strip()
    if not account:
        return payload

    fields = bot_identity_fields(account)
    hint = build_bot_identity_hint(fields)
    if fields.get("bot_id"):
        payload["bot_id"] = fields["bot_id"]
    if fields.get("bot_username"):
        payload["bot_username"] = fields["bot_username"]
    if fields.get("bot_display_name"):
        payload["bot_display_name"] = fields["bot_display_name"]

    if hint:
        content = str(payload.get("content") or "").strip()
        payload["content"] = f"{hint}\n\n{content}" if content else hint
    return payload
