# plugins/leona_discord/daemon.py — Discord bot daemon entry point
#
# Wires lifecycle (start/stop) and re-exports the public API used by routes and tools.
# Implementation lives under lib/ and handlers/.

# -- Portable import path (works from plugins/ or user/plugins/) --
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location('_ldc', str(__import__('pathlib').Path(__file__).resolve().parent / '_compat.py'))
_mod = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_mod); del _ilu, _spec, _mod

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


def _warn_if_asyncio_shutdown_missing() -> None:
    """Warn when Sapphire core lacks graceful asyncio shutdown helpers."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.find_spec("core.asyncio_shutdown")
    if spec is not None and spec.origin not in (None, "built-in", "frozen"):
        return

    core_spec = importlib.util.find_spec("core")
    core_dir = None
    if core_spec is not None and core_spec.submodule_search_locations:
        core_dir = Path(core_spec.submodule_search_locations[0])
    elif core_spec is not None and core_spec.origin not in (None, "built-in", "frozen"):
        core_dir = Path(core_spec.origin).resolve().parent

    if core_dir is not None and (core_dir / "asyncio_shutdown.py").is_file():
        return

    logger.warning(
        "[DISCORD] core/asyncio_shutdown.py is missing — graceful daemon shutdown "
        "is unavailable; expect import errors or asyncio warnings when Sapphire exits."
    )


def start(plugin_loader, settings):
    """Called by plugin_loader on load. Starts the daemon thread."""
    _warn_if_asyncio_shutdown_missing()
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

        loop = state._loop
        thread = state._thread

        if loop and loop.is_running():
            async def _shutdown():
                for name, client in list(state._clients.items()):
                    try:
                        await client.close()
                    except Exception:
                        pass
                state._clients.clear()

            try:
                future = asyncio.run_coroutine_threadsafe(_shutdown(), loop)
                future.result(timeout=8)
            except Exception:
                pass

        if thread and thread.is_alive():
            thread.join(timeout=8)

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
    except BaseException as e:
        if not state._stop_event.is_set():
            logger.error(f"[DISCORD] Daemon loop crashed: {e}", exc_info=True)
    finally:
        from core.asyncio_shutdown import close_event_loop
        close_event_loop(state._loop)
