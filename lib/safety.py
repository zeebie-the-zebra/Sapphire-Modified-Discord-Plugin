"""Moderation and safety checks before processing messages."""

import time
from collections import deque

from plugins.leona_discord.lib import state

_user_events: dict = {}
_user_events_lock = __import__("threading").Lock()


def _normalize_blocklist(value) -> list:
    if not value:
        return []
    if isinstance(value, str):
        parts = value.replace(",", "\n").split()
        return [p.strip().lower() for p in parts if p.strip()]
    if isinstance(value, list):
        return [str(v).strip().lower() for v in value if str(v).strip()]
    return []


async def check_channel_permissions(message, settings: dict) -> tuple:
    if not settings.get("safety_check_permissions", True):
        return True, ""
    if not message.guild:
        return True, ""
    me = message.guild.me
    if not me:
        return True, ""
    perms = message.channel.permissions_for(me)
    if not perms.send_messages:
        return False, "no_send_permission"
    return True, ""


def check_content(content: str, settings: dict) -> tuple:
    blocklist = _normalize_blocklist(settings.get("content_blocklist"))
    if not blocklist or not content:
        return True, ""
    lower = content.lower()
    for term in blocklist:
        if term and term in lower:
            return False, "content_blocklist"
    return True, ""


def check_rate_limit(author_id: str, channel_key: str, settings: dict) -> tuple:
    try:
        min_gap = float(settings.get("rate_limit_seconds", 0))
        burst = max(1, int(settings.get("rate_limit_burst", 5)))
        window = max(10.0, float(settings.get("rate_limit_window", 60)))
    except (TypeError, ValueError):
        return True, ""

    if min_gap <= 0 and burst >= 999:
        return True, ""

    now = time.time()
    key = f"{channel_key}:{author_id}"
    with _user_events_lock:
        dq = _user_events.setdefault(key, deque(maxlen=50))
        if min_gap > 0 and dq and (now - dq[-1]) < min_gap:
            return False, "rate_limit_gap"
        while dq and dq[0] < now - window:
            dq.popleft()
        if burst < 999 and len(dq) >= burst:
            return False, "rate_limit_burst"
        dq.append(now)
    return True, ""


async def run_safety_checks(message, settings: dict, account: str, channel_key: str) -> tuple:
    perm_ok, perm_reason = await check_channel_permissions(message, settings)
    if not perm_ok:
        return False, perm_reason

    content = message.clean_content or message.content or ""
    content_ok, content_reason = check_content(content, settings)
    if not content_ok:
        return False, content_reason

    author_id = str(message.author.id)
    rate_ok, rate_reason = check_rate_limit(author_id, channel_key, settings)
    if not rate_ok:
        return False, rate_reason

    return True, ""
