"""Shared helpers for scheduled tasks (morning_greeting, quiet_outreach)."""

import logging

logger = logging.getLogger(__name__)


def parse_target(entry):
    """Parse a greeting/outreach target entry into (account, guild_id, channel_id)."""
    if isinstance(entry, str):
        parts = entry.split(":")
        if len(parts) < 3:
            return None
        return parts[0].strip(), parts[1].strip(), parts[2].strip()
    if isinstance(entry, dict):
        account = str(entry.get("account", "")).strip()
        guild_id = str(entry.get("guild_id", "")).strip()
        channel_id = str(entry.get("channel_id", "")).strip()
        if account and channel_id:
            return account, guild_id, channel_id
    return None


def resolve_names(account: str, guild_id: str, channel_id: str) -> tuple:
    """Resolve guild and channel names from IDs via the connected Discord client."""
    from plugins.leona_discord.lib import state

    client = state._clients.get(account)
    if not client or not client.is_ready():
        return "", ""
    guild_name = ""
    channel_name = ""
    try:
        if guild_id:
            guild = client.get_guild(int(guild_id))
            if guild:
                guild_name = guild.name
        ch = client.get_channel(int(channel_id))
        if ch:
            channel_name = getattr(ch, "name", "") or ""
    except Exception:
        pass
    return guild_name, channel_name


def send_scheduled_message(account: str, channel_id: str, message: str, use_typing: bool = False) -> bool:
    """Send a message from a scheduled task (greeting or outreach).

    Optionally holds the typing indicator for a realistic delay.
    """
    import asyncio
    import random

    from plugins.leona_discord.lib import state
    from plugins.leona_discord.lib.send import send_message

    client = state._clients.get(account)
    loop = state._loop
    if not client or not loop or not client.is_ready():
        return False

    async def _do():
        try:
            ch = client.get_channel(int(channel_id))
            if not ch:
                return False
            if use_typing:
                delay = random.uniform(1.8, 3.8)
                async with ch.typing():
                    await asyncio.sleep(delay)
            await send_message(account, int(channel_id), message)
            return True
        except Exception:
            return False

    try:
        future = asyncio.run_coroutine_threadsafe(_do(), loop)
        return bool(future.result(timeout=20))
    except Exception as e:
        logger.warning(f"[LEONA-DISCORD] Scheduled send failed: {e}")
        return False
