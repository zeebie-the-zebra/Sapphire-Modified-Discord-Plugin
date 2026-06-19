"""Discord bot connection lifecycle with reconnect safeguards."""

import asyncio
import logging
import time

from plugins.leona_discord.handlers.on_message import register_on_message
from plugins.leona_discord.handlers.slash_commands import register_slash_commands, setup_slash_tree
from plugins.leona_discord.lib import state
from plugins.leona_discord.lib.constants import CONNECT_COOLDOWN
from plugins.leona_discord.lib.settings import get_always_online

logger = logging.getLogger(__name__)


async def connect_accounts():
    elapsed = time.monotonic() - state._last_connect_time
    if state._last_connect_time > 0 and elapsed < CONNECT_COOLDOWN:
        wait = CONNECT_COOLDOWN - elapsed
        logger.info(f"[DISCORD] Cooldown: waiting {wait:.0f}s before reconnecting")
        await asyncio.sleep(wait)

    from core.plugin_loader import plugin_loader
    plugin_state = plugin_loader.get_plugin_state("leona_discord")
    accounts = plugin_state.get("accounts", {})

    if not accounts:
        logger.info("[DISCORD] No accounts configured — daemon idle")
        return

    active = set()
    if not get_always_online():
        active = plugin_loader.active_daemon_accounts("discord_message")
        if not active:
            logger.info("[DISCORD] always_online OFF and no active daemon tasks — not connecting")
            return

    state._last_connect_time = time.monotonic()

    to_connect = []
    for name, meta in accounts.items():
        if not get_always_online() and name not in active:
            logger.debug(f"[DISCORD] Skipping '{name}' — no active daemon task")
            continue
        token = meta.get("token", "")
        if token:
            to_connect.append((name, token))

    for i, (name, token) in enumerate(to_connect):
        if i > 0:
            logger.info(f"[DISCORD] Staggering connection for '{name}' (5s)")
            await asyncio.sleep(5)
        try:
            await connect_single(name, token)
        except Exception as e:
            logger.error(f"[DISCORD] Failed to connect '{name}': {e}")


async def connect_single(account_name: str, token: str = None):
    import discord

    if not token:
        from core.plugin_loader import plugin_loader
        plugin_state = plugin_loader.get_plugin_state("leona_discord")
        accounts = plugin_state.get("accounts", {})
        meta = accounts.get(account_name, {})
        token = meta.get("token", "")
        if not token:
            return

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True

    client = discord.Client(intents=intents)
    register_on_message(client, account_name)
    slash_tree = setup_slash_tree(client, account_name)

    @client.event
    async def on_ready():
        # Register client only after it's fully connected — prevents
        # events from reaching the bot before is_ready() is true.
        state._clients[account_name] = client
        logger.info(
            f"[DISCORD] Connected: {account_name} "
            f"({client.user.name}#{client.user.discriminator})"
        )
        try:
            from core.plugin_loader import plugin_loader
            plugin_state = plugin_loader.get_plugin_state("leona_discord")
            accounts = plugin_state.get("accounts", {})
            if account_name in accounts:
                accounts[account_name]["bot_name"] = client.user.name
                accounts[account_name]["bot_id"] = client.user.id
                plugin_state.save("accounts", accounts)
        except Exception:
            pass
        try:
            register_slash_commands(slash_tree, client, account_name)
            synced = await slash_tree.sync()
            logger.info(f"[DISCORD] Synced {len(synced)} slash command(s) for {account_name}")
        except Exception as e:
            logger.warning(f"[DISCORD] Slash command sync failed for {account_name}: {e}")

    async def _start_with_retry():
        for attempt in range(3):
            try:
                await client.start(token)
                return
            except Exception as e:
                if '429' in str(e) and attempt < 2:
                    wait = 10 * (attempt + 1)
                    logger.warning(
                        f"[DISCORD] Rate limited on connect for '{account_name}', "
                        f"retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"[DISCORD] Failed to start '{account_name}': {e}")
                    state._clients.pop(account_name, None)
                    return

    asyncio.ensure_future(_start_with_retry())
