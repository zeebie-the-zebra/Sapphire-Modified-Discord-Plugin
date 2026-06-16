"""Automatic GIF follow-ups after bot replies (LLM query + sentiment fallback)."""

import asyncio
import logging
import random
import re

from plugins.leona_discord.lib.cooldowns import is_gif_cooldown_active, set_gif_cooldown
from plugins.leona_discord.lib.settings import get_effective_settings, get_plugin_settings
from plugins.leona_discord.lib.gif_search import search_gif_url

logger = logging.getLogger(__name__)

_SENTIMENT_GIF_QUERIES = {
    "very_positive": ["celebration", "party", "let's go", "awesome"],
    "positive": ["nice", "cool", "thumbs up", "well done"],
    "curious": ["thinking", "hmm interesting", "wait what"],
    "negative": ["oh no", "that's rough", "sympathy hug"],
    "very_negative": ["oh no", "i'm sorry", "sad"],
}


def _resolve_api_key(stored: dict) -> str:
    return (stored.get("gif_api_key") or stored.get("tenor_api_key") or "").strip()


def get_gif_settings(guild_id: str = "") -> dict:
    stored = get_plugin_settings()
    merged = get_effective_settings(guild_id=guild_id)
    global_s = stored.get("global", {}) or {}

    def _pick(key, default=None):
        if key in stored:
            return stored[key]
        if key in global_s:
            return global_s[key]
        return merged.get(key, default)

    content_filter = _pick("gif_content_filter") or _pick("tenor_content_filter", "medium")
    return {
        "gif_replies_enabled": bool(_pick("gif_replies_enabled", False)),
        "gif_reply_chance": int(_pick("gif_reply_chance", 15) or 15),
        "gif_reply_cooldown_seconds": int(_pick("gif_reply_cooldown_seconds", 120) or 120),
        "gif_use_llm": _pick("gif_use_llm", True) is not False,
        "gif_model_provider": str(_pick("gif_model_provider", "") or ""),
        "gif_model_name": str(_pick("gif_model_name", "") or ""),
        "gif_model_max_tokens": int(_pick("gif_model_max_tokens", 80) or 80),
        "gif_provider": str(_pick("gif_provider", "klipy") or "klipy"),
        "gif_api_key": _resolve_api_key(stored),
        "gif_content_filter": content_filter or "medium",
        "reaction_backend": merged.get("reaction_backend", "vader"),
    }


_GIF_REQUEST_RE = re.compile(
    r"\b(gifs?|giphy|tenor|klipy|meme\s*gif|send\s+a\s+gif|respond\s+with\s+gifs?)\b",
    re.I,
)


def build_gif_hint(guild_id: str = "") -> str:
    settings = get_gif_settings(guild_id)
    if not settings.get("gif_replies_enabled"):
        return ""
    if not settings.get("gif_api_key"):
        return ""
    return (
        "GIF replies are enabled. To send a GIF, call `discord_send_gif` with a search query "
        '(e.g. query="celebration clapping"). Do NOT use web_search or get_website to hunt for '
        "Do NOT use web_search or get_website to hunt for "
        "Tenor/Giphy URLs — that will not embed in Discord. You can also embed `[gif:search terms]` "
        "in your text reply for an automatic follow-up GIF (the tag is stripped before sending). "
        "There is no per-channel GIF toggle — if this tool errors, read the exact tool result."
    )


def user_requested_gif(user_text: str) -> bool:
    return bool(_GIF_REQUEST_RE.search(user_text or ""))


def send_gif_query(
    account: str,
    channel_id: str,
    query: str,
    guild_id: str = "",
    *,
    event_data: dict = None,
    bot_reply: str = "",
    force: bool = False,
    explicit: bool = False,
) -> tuple:
    """Search and post a GIF. Returns (status_message, success_bool).

    explicit=True for discord_send_gif tool calls — only requires API key, not the
    automatic follow-up toggle (gif_replies_enabled).
    """
    settings = get_gif_settings(guild_id)
    if not explicit and not settings.get("gif_replies_enabled"):
        logger.info(
            f"[LEONA-DISCORD] GIF blocked (auto follow-up disabled) "
            f"guild={guild_id} channel={channel_id}"
        )
        return "GIF replies are disabled in Leona Discord settings.", False

    api_key = settings.get("gif_api_key", "")
    if not api_key:
        return "GIF API key is not configured (Klipy or Giphy in plugin settings).", False

    account = (account or "").strip()
    channel_id = str(channel_id or "").strip()
    if not account or not channel_id:
        return "Missing Discord account or channel.", False

    if not force:
        cooldown = float(settings.get("gif_reply_cooldown_seconds", 120))
        if is_gif_cooldown_active(account, guild_id, channel_id, cooldown):
            return "GIF cooldown active for this channel.", False

    query = (query or "").strip()
    if not query and event_data:
        user_text = _extract_user_text(event_data)
        query = resolve_gif_query(
            user_text,
            bot_reply,
            event_data.get("recent_history") or [],
            settings,
        )
    if not query:
        return "Could not determine a GIF search query.", False

    gif_url = search_gif_url(
        query,
        api_key,
        provider=settings.get("gif_provider", "klipy"),
        content_filter=settings.get("gif_content_filter", "medium"),
    )
    if not gif_url:
        return f"No GIF found for query: {query}", False

    if not _send_gif_url(account, channel_id, gif_url):
        return "Failed to send GIF to Discord.", False

    set_gif_cooldown(account, guild_id, channel_id)
    logger.info(
        f"[LEONA-DISCORD] GIF sent (q={query!r}) in channel {channel_id} via {account}"
    )
    return f"Sent GIF ({query}).", True


def try_gif_followup(event_data: dict, bot_reply: str, *, inline_query: str = "") -> bool:
    """Maybe send a GIF after a text reply. Returns True if a GIF was sent."""
    guild_id = str(event_data.get("guild_id") or "")
    settings = get_gif_settings(guild_id)

    if not settings.get("gif_replies_enabled"):
        logger.debug("[LEONA-DISCORD] GIF follow-up skipped: disabled in settings")
        return False

    if not settings.get("gif_api_key"):
        logger.info("[LEONA-DISCORD] GIF follow-up skipped: no GIF API key configured")
        return False

    account = event_data.get("account", "")
    channel_id = str(event_data.get("channel_id") or "")
    user_text = _extract_user_text(event_data)
    force = bool(inline_query) or user_requested_gif(user_text)

    if not force:
        chance = max(0, min(100, int(settings.get("gif_reply_chance", 15))))
        if chance <= 0:
            logger.debug("[LEONA-DISCORD] GIF follow-up skipped: chance is 0%")
            return False
        if chance < 100 and random.random() >= (chance / 100.0):
            logger.debug(f"[LEONA-DISCORD] GIF follow-up skipped: lost {chance}% roll")
            return False

    query = (inline_query or "").strip()
    if not query:
        query = resolve_gif_query(
            user_text,
            bot_reply,
            event_data.get("recent_history") or [],
            settings,
        )
    if not query:
        logger.info("[LEONA-DISCORD] GIF follow-up skipped: empty search query")
        return False

    msg, ok = send_gif_query(
        account,
        channel_id,
        query,
        guild_id,
        force=force,
    )
    if not ok:
        logger.info(f"[LEONA-DISCORD] GIF follow-up failed: {msg}")
    return ok


def pick_sentiment_gif_query(content: str, context_messages: list = None, backend: str = "vader") -> str:
    from plugins.leona_discord.lib.reactions import _sentiment_tier

    tier = _sentiment_tier(content or "", context_messages, backend)
    if not tier:
        return ""
    candidates = _SENTIMENT_GIF_QUERIES.get(tier, [])
    return random.choice(candidates) if candidates else ""


def resolve_gif_query(
    user_text: str,
    bot_reply: str,
    recent_chat: list,
    settings: dict,
) -> str:
    query = ""
    if settings.get("gif_use_llm", True):
        from plugins.leona_discord.lib.gif_query_llm import generate_gif_query

        query = generate_gif_query(
            user_text=user_text,
            bot_reply=bot_reply,
            recent_chat=recent_chat,
            provider_key=settings.get("gif_model_provider", ""),
            model_name=settings.get("gif_model_name", ""),
            max_tokens=settings.get("gif_model_max_tokens", 80),
        )
    if not query:
        query = pick_sentiment_gif_query(
            user_text or bot_reply,
            context_messages=_history_to_messages(recent_chat),
            backend=settings.get("reaction_backend", "vader"),
        )
    return (query or "").strip()


def _history_to_messages(recent_chat: list) -> list:
    out = []
    for line in recent_chat or []:
        if not isinstance(line, str):
            continue
        text = line
        if "]" in text and text.startswith("["):
            text = text.split("]", 1)[-1].strip()
        out.append({"clean_content": text, "content": text})
    return out


def _extract_user_text(event_data: dict) -> str:
    history = event_data.get("recent_history") or []
    if history:
        last = history[-1]
        if isinstance(last, str):
            if "]" in last and last.startswith("["):
                return last.split("]", 1)[-1].strip()
            return last.strip()
    content = str(event_data.get("content") or "").strip()
    if content:
        for marker in ("\n\nReactions are enabled.", "\n\n---\n", "[Pinned memory"):
            if marker in content:
                content = content.split(marker, 1)[0].strip()
        return content[:800]
    return ""


def _send_gif_url(account: str, channel_id: str, gif_url: str) -> bool:
    from plugins.leona_discord.lib import state
    from plugins.leona_discord.lib.send import send_message

    client = state._clients.get(account)
    loop = state._loop
    if not client or not loop or not client.is_ready():
        return False

    async def _do():
        try:
            await send_message(account, int(channel_id), gif_url)
            return True
        except Exception:
            return False

    try:
        future = asyncio.run_coroutine_threadsafe(_do(), loop)
        return bool(future.result(timeout=15))
    except Exception as e:
        logger.warning(f"[LEONA-DISCORD] GIF send failed: {e}")
        return False
