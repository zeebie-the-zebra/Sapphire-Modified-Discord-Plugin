"""Send messages via the Discord client on the daemon loop."""

import logging
from pathlib import Path
from typing import Optional

import discord

from plugins.leona_discord.lib.embeds import build_embed, parse_color
from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)


async def send_message(
    account_name: str,
    channel_id: int,
    text: str = "",
    reply_to_message_id: Optional[int] = None,
    embed: discord.Embed = None,
    embed_dict: dict = None,
    file_paths: list = None,
) -> discord.Message:
    client = state._clients.get(account_name)
    if not client:
        raise RuntimeError(f"Account '{account_name}' not connected")
    if not client.is_ready():
        raise RuntimeError(f"Account '{account_name}' not ready yet")

    channel = client.get_channel(channel_id)
    if not channel:
        channel = await client.fetch_channel(channel_id)

    reference = None
    if reply_to_message_id:
        reference = discord.MessageReference(
            message_id=int(reply_to_message_id),
            channel_id=int(channel_id),
            fail_if_not_exists=False,
        )

    embed_obj = embed
    if embed_obj is None and embed_dict:
        embed_obj = build_embed(
            title=embed_dict.get("title", ""),
            description=embed_dict.get("description", ""),
            color=parse_color(embed_dict.get("color")),
            fields=embed_dict.get("fields"),
            footer=embed_dict.get("footer", ""),
        )

    files = []
    for fp in file_paths or []:
        path = Path(fp)
        if path.is_file():
            files.append(discord.File(str(path)))

    content = text if (text and text.strip()) else None
    if not content and not embed_obj and not files:
        raise ValueError("Nothing to send")

    return await channel.send(
        content=content,
        embed=embed_obj,
        reference=reference,
        files=files or None,
    )


async def edit_message(
    account_name: str,
    channel_id: int,
    message_id: int,
    new_text: str,
) -> discord.Message:
    """Edit an existing channel message."""
    client = state._clients.get(account_name)
    if not client:
        raise RuntimeError(f"Account '{account_name}' not connected")
    if not client.is_ready():
        raise RuntimeError(f"Account '{account_name}' not ready yet")

    channel = client.get_channel(channel_id)
    if not channel:
        channel = await client.fetch_channel(channel_id)

    message = await channel.fetch_message(int(message_id))
    return await message.edit(content=new_text)
