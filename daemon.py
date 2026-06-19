# plugins/leona_discord/daemon.py — Discord bot daemon entry point
#
# Wires lifecycle (start/stop) and re-exports the public API used by routes and tools.
# Implementation lives under lib/ and handlers/.

import asyncio
import logging
import threading

from plugins.leona_discord.handlers.reply_handler import reply_handler
from plugins.leona_discord.lib.core_compat import ensure_execution_context_images_support
from plugins.leona_discord.lib.batching import flush_all_pending
from plugins.leona_discord.lib.connection import connect_accounts, connect_single
from plugins.leona_discord.lib import memory
from plugins.leona_discord.lib import profile
from plugins.leona_discord.lib.context_cache import (
    get_pending_payload,
    get_reply_context,
    mark_reacted,
)
from plugins.leona_discord.lib.mentions import resolve_custom_emoji
from plugins.leona_discord.lib.settings import get_effective_settings
from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)

# Backward-compatible re-exports for routes and tools
_clients = state._clients
_connect_single = connect_single
_get_effective_settings = get_effective_settings
_resolve_custom_emoji = resolve_custom_emoji
_channel_key = state.channel_key


def start(plugin_loader, settings):
    """Called by plugin_loader on load. Starts the daemon thread."""
    with state._lifecycle_lock:
        state.set_plugin_loader(plugin_loader)
        state._stop_event.clear()

        state._loop = asyncio.new_event_loop()
        state._thread = threading.Thread(
            target=_run_loop, daemon=True, name="leona-discord-daemon",
        )
        state._thread.start()

        plugin_loader.register_reply_handler("leona_discord", reply_handler)
        ensure_execution_context_images_support()
        memory.start()
        profile.start()
    logger.info("[DISCORD] Daemon thread started")


def stop():
    """Called by plugin_loader on unload. Stops all clients."""
    with state._lifecycle_lock:
        state._stop_event.set()
        flush_all_pending()
        memory.stop()
        profile.stop()

        if state._loop and state._loop.is_running():
            async def _shutdown():
                for name, client in list(state._clients.items()):
                    try:
                        await client.close()
                    except Exception:
                        pass
                state._clients.clear()

            future = asyncio.run_coroutine_threadsafe(_shutdown(), state._loop)
            try:
                future.result(timeout=5)
            except Exception:
                pass
            state._loop.call_soon_threadsafe(state._loop.stop)

        if state._thread and state._thread.is_alive():
            state._thread.join(timeout=5)

        with state._mention_maps_lock:
            state._mention_maps.clear()
        with state._pending_payloads_lock:
            state._pending_payloads.clear()
        with state._reacted_messages_lock:
            state._reacted_messages.clear()

        state._loop = None
        state._thread = None
    logger.info("[DISCORD] Daemon stopped")


def get_client(account_name: str):
    return state._clients.get(account_name)


def get_loop():
    return state._loop


def list_connected():
    return list(state._clients.keys())


def _run_loop():
    asyncio.set_event_loop(state._loop)

    async def _main():
        await connect_accounts()
        while not state._stop_event.is_set():
            # --- Presence cycling: update bot status periodically ---
            try:
                from plugins.leona_discord.lib.presence import update_presence
                for name in list(state._clients.keys()):
                    update_presence(name)
            except Exception:
                pass
            await asyncio.sleep(1)

    try:
        state._loop.run_until_complete(_main())
    except Exception as e:
        if not state._stop_event.is_set():
            logger.error(f"[DISCORD] Daemon loop crashed: {e}", exc_info=True)
    finally:
        try:
            state._loop.run_until_complete(state._loop.shutdown_asyncgens())
        except Exception:
            pass
