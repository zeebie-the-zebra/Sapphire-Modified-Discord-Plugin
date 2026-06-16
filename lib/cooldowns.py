"""Per-channel cooldown tracking for probabilistic reply throttling."""

import time

from plugins.leona_discord.lib import state


def cooldown_key(scope: str, account: str, guild_id: str, channel_id: str) -> str:
    if scope == "global":
        return f"global:{account}:{guild_id}"
    return f"channel:{account}:{channel_id}"


def is_cooldown_active(scope: str, account: str, guild_id: str,
                       channel_id: str, cooldown_seconds: float) -> bool:
    if cooldown_seconds <= 0:
        return False
    key = cooldown_key(scope, account, guild_id, channel_id)
    with state._cooldowns_lock:
        last = state._cooldowns.get(key)
    if last is None:
        return False
    return (time.time() - last) < cooldown_seconds


def set_cooldown(scope: str, account: str, guild_id: str, channel_id: str):
    key = cooldown_key(scope, account, guild_id, channel_id)
    with state._cooldowns_lock:
        state._cooldowns[key] = time.time()


def reaction_cooldown_key(account: str, guild_id: str, channel_id: str) -> str:
    return f"react:{account}:{guild_id}:{channel_id}"


def is_reaction_cooldown_active(account: str, guild_id: str, channel_id: str,
                                cooldown_seconds: float) -> bool:
    if cooldown_seconds <= 0:
        return False
    key = reaction_cooldown_key(account, guild_id, channel_id)
    with state._reaction_cooldowns_lock:
        last = state._reaction_cooldowns.get(key)
    if last is None:
        return False
    return (time.time() - last) < cooldown_seconds


def set_reaction_cooldown(account: str, guild_id: str, channel_id: str):
    key = reaction_cooldown_key(account, guild_id, channel_id)
    with state._reaction_cooldowns_lock:
        state._reaction_cooldowns[key] = time.time()


def gif_cooldown_key(account: str, guild_id: str, channel_id: str) -> str:
    return f"gif:{account}:{guild_id}:{channel_id}"


def is_gif_cooldown_active(account: str, guild_id: str, channel_id: str,
                           cooldown_seconds: float) -> bool:
    if cooldown_seconds <= 0:
        return False
    key = gif_cooldown_key(account, guild_id, channel_id)
    with state._gif_cooldowns_lock:
        last = state._gif_cooldowns.get(key)
    if last is None:
        return False
    return (time.time() - last) < cooldown_seconds


def set_gif_cooldown(account: str, guild_id: str, channel_id: str):
    key = gif_cooldown_key(account, guild_id, channel_id)
    with state._gif_cooldowns_lock:
        state._gif_cooldowns[key] = time.time()


# ---------------------------------------------------------------------------
# Engagement window — boosts response chance after the bot replies
# ---------------------------------------------------------------------------

def mark_engaged(account: str, channel_id: str):
    """Record that the bot just replied — starts the engagement window."""
    key = state.channel_key(account, str(channel_id))
    with state._engagement_lock:
        state._engagement[key] = time.time()


def is_engaged(account: str, channel_id: str) -> bool:
    """Check if the bot is still in the engagement window for this channel."""
    key = state.channel_key(account, str(channel_id))
    with state._engagement_lock:
        last = state._engagement.get(key)
    if last is None:
        return False
    return (time.time() - last) < state.ENGAGEMENT_WINDOW_SECS


def engagement_boost(settings: dict, account: str, channel_id: str) -> dict:
    """If engaged, boost response chances. Returns a modified settings copy."""
    if not is_engaged(account, channel_id):
        return settings
    out = dict(settings)
    # Double the human response chance while engaged, capped at 80%
    base = out.get("human_response_chance", 15)
    out["human_response_chance"] = min(80, base * 2)
    return out
