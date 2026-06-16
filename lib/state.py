"""Module-level daemon state shared across Leona Discord components."""

import asyncio
import threading

from plugins.leona_discord.lib.constants import CONNECT_COOLDOWN

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_clients: dict = {}
_stop_event = threading.Event()
_plugin_loader = None
_lifecycle_lock = threading.Lock()
_last_connect_time: float = 0

_batches: dict = {}
_batches_lock = threading.Lock()

_reply_contexts: dict = {}
_reply_contexts_lock = threading.Lock()

_pending_payloads: dict = {}
_pending_payloads_lock = threading.Lock()

_reacted_messages: dict = {}
_reacted_messages_lock = threading.Lock()

_mention_maps: dict = {}
_mention_maps_lock = threading.Lock()

_cooldowns: dict = {}
_cooldowns_lock = threading.Lock()

_reaction_cooldowns: dict = {}
_reaction_cooldowns_lock = threading.Lock()

_gif_cooldowns: dict = {}
_gif_cooldowns_lock = threading.Lock()

# Engagement window: tracks when the bot last replied in a channel.
# While engaged, response chance is boosted (humans stay in conversation).
_engagement: dict = {}
_engagement_lock = threading.Lock()
ENGAGEMENT_WINDOW_SECS = 180  # 3 minutes — bot stays "in the conversation"


def channel_key(account: str, channel_id: str) -> str:
    return f"{account}:{channel_id}"


def get_plugin_loader():
    return _plugin_loader


def set_plugin_loader(loader):
    global _plugin_loader
    _plugin_loader = loader
