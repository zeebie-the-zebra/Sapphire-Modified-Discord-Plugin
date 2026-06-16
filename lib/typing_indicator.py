"""Typing indicator with realistic hold durations.

Discord's typing indicator auto-expires after ~5-10 seconds. For longer
"typing" periods we pulse it in a loop.  All durations include jitter so
the bot doesn't look robotic.
"""

import asyncio
import logging
import random
from typing import Optional

from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)

# Defaults — configurable via settings later if desired
DEFAULT_WPM = 65           # average human typing speed (words per minute)
WPM_JITTER = 0.2           # ±20% randomness
MIN_TYPING_SECS = 0.5
MAX_TYPING_SECS = 12.0     # cap — Discord re-shows indicator every ~5s
READ_DELAY_MIN = 0.3       # seconds before "reading" the message
READ_DELAY_MAX = 1.2
HUMAN_PAUSE_MIN = 0.5      # post-LLM jitter before sending
HUMAN_PAUSE_MAX = 3.0
INTER_CHUNK_MIN = 0.5      # pause between multi-chunk replies
INTER_CHUNK_MAX = 1.5
CHARS_PER_WORD = 5          # average word length for WPM calculation

# Contextual WPM bands (words per minute)
WPM_SHORT_MIN, WPM_SHORT_MAX = 80, 100      # <50 chars — excited / quick
WPM_LONG_MIN, WPM_LONG_MAX = 45, 55         # >200 chars — thoughtful
WPM_CODE_MIN, WPM_CODE_MAX = 30, 40         # code / technical content
SHORT_REPLY_CHARS = 50
LONG_REPLY_CHARS = 200


def _chars_per_second(wpm: int = DEFAULT_WPM) -> float:
    """Convert words-per-minute to characters-per-second."""
    return (wpm * CHARS_PER_WORD) / 60.0


def _looks_like_code(text: str) -> bool:
    """Heuristic: fenced blocks, inline code, or dense technical punctuation."""
    if not text:
        return False
    if "```" in text or text.count("`") >= 2:
        return True
    special = sum(1 for c in text if c in "{}[]();=<>/#\\|&$@")
    return len(text) >= 20 and (special / len(text)) > 0.08


def contextual_wpm(text: str = "") -> int:
    """Pick a typing speed that matches reply tone and content."""
    length = len(text or "")
    if _looks_like_code(text):
        return random.randint(WPM_CODE_MIN, WPM_CODE_MAX)
    if length < SHORT_REPLY_CHARS:
        return random.randint(WPM_SHORT_MIN, WPM_SHORT_MAX)
    if length > LONG_REPLY_CHARS:
        return random.randint(WPM_LONG_MIN, WPM_LONG_MAX)
    return DEFAULT_WPM


def typing_duration_seconds(
    text_length: int,
    wpm: Optional[int] = None,
    *,
    text: str = "",
) -> float:
    """Calculate how long a human would take to type `text_length` characters."""
    if wpm is None:
        wpm = contextual_wpm(text) if text else DEFAULT_WPM
    cps = _chars_per_second(wpm)
    base = text_length / cps if cps > 0 else 0
    # Apply jitter
    jitter = 1.0 + random.uniform(-WPM_JITTER, WPM_JITTER)
    return max(MIN_TYPING_SECS, min(MAX_TYPING_SECS, base * jitter))


def human_pause_seconds() -> float:
    """Small random pause after LLM generation, before typing/sending."""
    return random.uniform(HUMAN_PAUSE_MIN, HUMAN_PAUSE_MAX)


def read_delay_seconds(trigger_length: int = 0) -> float:
    """Short pause before the bot starts 'typing' — simulates reading.

    Scales slightly with the length of the incoming message.
    """
    base = random.uniform(READ_DELAY_MIN, READ_DELAY_MAX)
    # Longer messages get a slightly longer read delay (up to +0.5s)
    extra = min(0.5, trigger_length / 2000.0)
    return base + extra


# ---------------------------------------------------------------------------
# Async helpers — run on the daemon event loop
# ---------------------------------------------------------------------------

async def _hold_typing_async(account_name: str, channel_id: int, duration: float):
    """Pulse the typing indicator for `duration` seconds.

    Discord refreshes the indicator every ~5s while the context is open,
    so we hold `channel.typing()` in a loop until the duration elapses.
    """
    client = state._clients.get(account_name)
    if not client or not client.is_ready():
        return
    try:
        channel = client.get_channel(channel_id)
        if not channel:
            return
    except Exception:
        return

    try:
        end_time = asyncio.get_event_loop().time() + duration
        async with channel.typing():
            while asyncio.get_event_loop().time() < end_time:
                await asyncio.sleep(min(4.0, duration))
        logger.debug(f"[DISCORD] Typing held for {duration:.1f}s in {channel_id}")
    except Exception as e:
        logger.debug(f"[DISCORD] Typing hold failed: {e}")


# ---------------------------------------------------------------------------
# Public API — callable from threads
# ---------------------------------------------------------------------------

def hold_typing(account_name: str, channel_id: int, duration: float):
    """Schedule a typing hold on the daemon event loop (thread-safe)."""
    if not state._loop or not state._loop.is_running():
        return
    asyncio.run_coroutine_threadsafe(
        _hold_typing_async(account_name, channel_id, duration),
        state._loop,
    )


def hold_typing_sync(account_name: str, channel_id: int, duration: float):
    """Block the current thread until the typing hold completes.

    Use this when you need to wait for the typing indicator before sending
    (e.g. in the reply handler which runs on the executor thread).
    """
    if not state._loop or not state._loop.is_running():
        return
    try:
        future = asyncio.run_coroutine_threadsafe(
            _hold_typing_async(account_name, channel_id, duration),
            state._loop,
        )
        future.result(timeout=duration + 5)
    except Exception:
        pass


def fire_typing(account_name: str, channel_id: int):
    """Fire-and-forget single typing pulse (legacy API, kept for compatibility)."""
    if not state._loop or not state._loop.is_running():
        return
    asyncio.run_coroutine_threadsafe(
        _send_typing_once(account_name, channel_id),
        state._loop,
    )


async def _send_typing_once(account_name: str, channel_id: int):
    client = state._clients.get(account_name)
    if not client or not client.is_ready():
        return
    try:
        channel = client.get_channel(channel_id)
        if not channel:
            return
    except Exception:
        return
    try:
        async with channel.typing():
            pass
        logger.debug(f"[DISCORD] typing pulse sent to {channel_id}")
    except Exception as e:
        logger.debug(f"[DISCORD] typing pulse failed: {e}")
