"""Discord slash commands — /ask, /summarize, /remember."""

import logging

import discord
from discord import app_commands

from plugins.leona_discord.lib import events
from plugins.leona_discord.lib import store as sqlite_store
from plugins.leona_discord.lib.history import format_recent_history, get_history_snapshot
from plugins.leona_discord.lib.settings import get_plugin_settings
from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)


def setup_slash_tree(client: discord.Client, account_name: str) -> app_commands.CommandTree:
    tree = app_commands.CommandTree(client)

    @tree.command(name="ask", description="Ask Leona a question in this channel")
    @app_commands.describe(prompt="What do you want to ask?")
    async def ask_cmd(interaction: discord.Interaction, prompt: str):
        if not _slash_enabled():
            await interaction.response.send_message("Slash commands are disabled.", ephemeral=True)
            return
        prompt = (prompt or "").strip()
        if not prompt:
            await interaction.response.send_message("Please provide a question.", ephemeral=True)
            return

        await interaction.response.send_message("On it — I'll reply in this channel.", ephemeral=True)
        await _emit_slash(
            interaction, account_name, prompt,
            slash_command="ask",
        )

    @tree.command(name="summarize", description="Summarize recent messages in this channel")
    @app_commands.describe(count="How many messages to include (5–50)")
    async def summarize_cmd(interaction: discord.Interaction, count: int = 20):
        if not _slash_enabled():
            await interaction.response.send_message("Slash commands are disabled.", ephemeral=True)
            return

        count = max(5, min(50, int(count)))
        channel_id = str(interaction.channel_id)
        channel_key = state.channel_key(account_name, channel_id)
        history = get_history_snapshot(channel_key)
        window = history[-count:] if len(history) > count else history

        if not window:
            await interaction.response.send_message("No messages in history yet.", ephemeral=True)
            return

        lines = format_recent_history(window, str(interaction.guild_id) if interaction.guild else "")
        transcript = "\n".join(lines)
        prompt = (
            f"Please summarize the last {len(window)} messages in this Discord channel. "
            f"Be concise but capture key topics, decisions, and tone.\n\n"
            f"Transcript:\n{transcript}"
        )

        await interaction.response.send_message(
            f"Summarizing the last {len(window)} messages…", ephemeral=True,
        )
        await _emit_slash(interaction, account_name, prompt, slash_command="summarize")

    @tree.command(name="remember", description="Save something to Leona's memory for this server")
    @app_commands.describe(note="What to remember (leave empty to use your last message)")
    async def remember_cmd(interaction: discord.Interaction, note: str = None):
        if not _slash_enabled():
            await interaction.response.send_message("Slash commands are disabled.", ephemeral=True)
            return

        text = (note or "").strip()
        if not text:
            text = await _fetch_user_last_message(interaction)
        if not text:
            await interaction.response.send_message(
                "Nothing to remember — provide text or send a message first.", ephemeral=True,
            )
            return

        guild_id = str(interaction.guild_id) if interaction.guild else ""
        channel_id = str(interaction.channel_id)
        author = interaction.user

        sqlite_store.save_pinned_memory(
            account_name, guild_id, channel_id,
            str(author.id), author.display_name, text,
        )
        preview = text[:120] + ("…" if len(text) > 120 else "")
        await interaction.response.send_message(
            f"Saved to memory: _{preview}_", ephemeral=True,
        )

    client._slash_tree = tree
    return tree


def _slash_enabled() -> bool:
    raw = get_plugin_settings()
    g = raw.get("global", {}) or {}
    return g.get("slash_commands_enabled", True)


async def _fetch_user_last_message(interaction: discord.Interaction) -> str:
    try:
        channel = interaction.channel
        if not channel:
            return ""
        async for msg in channel.history(limit=25):
            if msg.author.id == interaction.user.id and (msg.clean_content or msg.content):
                return (msg.clean_content or msg.content).strip()
    except Exception as e:
        logger.debug(f"[DISCORD] Could not fetch last user message: {e}")
    return ""


async def _emit_slash(interaction: discord.Interaction, account_name: str,
                      content: str, slash_command: str):
    guild = interaction.guild
    guild_id = str(guild.id) if guild else ""
    guild_name = guild.name if guild else "DM"
    channel_id = str(interaction.channel_id)
    channel_name = getattr(interaction.channel, "name", "DM")
    user = interaction.user

    payload = events.build_event_payload(
        account=account_name,
        guild_id=guild_id,
        guild_name=guild_name,
        channel_id=channel_id,
        channel_name=channel_name,
        message_id=str(interaction.id),
        author_id=str(user.id),
        username=user.name,
        display_name=user.display_name,
        content=content,
        is_dm=guild is None,
        mentioned=True,
        slash_command=slash_command,
        reply_to_message_id=str(interaction.id),
    )

    accepted = events.emit_event(payload)
    if not accepted:
        try:
            await interaction.followup.send(
                "No active Schedule task is listening for Discord messages on this account.",
                ephemeral=True,
            )
        except Exception:
            pass
