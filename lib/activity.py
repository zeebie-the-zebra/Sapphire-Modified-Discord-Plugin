"""Per-channel activity tracking for reply-chance decay."""

import time
from collections import deque

from plugins.leona_discord.lib import state

_WINDOW_SECONDS = 300.0
_activity: dict = {}
_activity_lock = __import__("threading").Lock()


def record_message(channel_key: str):
    now = time.time()
    with _activity_lock:
        if channel_key not in _activity:
            _activity[channel_key] = deque(maxlen=200)
        _activity[channel_key].append(now)


def recent_count(channel_key: str, window_seconds: float = _WINDOW_SECONDS) -> int:
    cutoff = time.time() - window_seconds
    with _activity_lock:
        dq = _activity.get(channel_key)
        if not dq:
            return 0
        while dq and dq[0] < cutoff:
            dq.popleft()
        return len(dq)


def apply_activity_decay(settings: dict, channel_key: str) -> dict:
    if not settings.get("activity_decay_enabled", False):
        return settings
    try:
        threshold = max(2, int(settings.get("activity_decay_threshold", 10)))
        multiplier = float(settings.get("activity_decay_multiplier", 0.5))
    except (TypeError, ValueError):
        return settings
    multiplier = max(0.0, min(1.0, multiplier))
    if recent_count(channel_key) < threshold:
        return settings
    out = dict(settings)
    for key in ("human_response_chance", "bot_response_chance"):
        try:
            val = int(out.get(key, 0))
            out[key] = max(0, min(100, int(val * multiplier)))
        except (TypeError, ValueError):
            pass
    return out
