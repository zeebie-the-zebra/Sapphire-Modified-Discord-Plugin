"""Micro-LLM: pick a GIF search query from a Discord exchange."""

import logging
import re

from plugins.leona_discord.lib.think_tags import strip_think_tags

logger = logging.getLogger(__name__)
_NONE_RE = re.compile(r"^(none|n/a|no gif|skip)$", re.I)


def _providers_config():
    import config as app_config
    return {
        **(getattr(app_config, "LLM_PROVIDERS", None) or {}),
        **(getattr(app_config, "LLM_CUSTOM_PROVIDERS", None) or {}),
    }


def generate_gif_query(
    *,
    user_text: str = "",
    bot_reply: str = "",
    recent_chat: list = None,
    provider_key: str = "",
    model_name: str = "",
    max_tokens: int = 80,
) -> str:
    """Return a GIF search query, or empty string if LLM says NONE / fails."""
    provider_key = (provider_key or "").strip()
    model_name = (model_name or "").strip()
    if not provider_key or not model_name:
        return ""

    user_text = (user_text or "").strip()[:800]
    bot_reply = (bot_reply or "").strip()[:800]
    if not user_text and not bot_reply:
        return ""

    context = []
    if recent_chat:
        lines = recent_chat[-6:]
        if lines:
            context.append("Recent chat:\n" + "\n".join(lines))

    prompt = (
        "You pick GIF search queries for casual Discord meme reactions.\n"
        "Given the exchange below, output 2–5 words for a fitting, light-hearted GIF "
        "(not slurs, not NSFW, not mean-spirited).\n"
        "If a GIF would feel forced, awkward, or inappropriate, output exactly: NONE\n\n"
    )
    if context:
        prompt += "\n".join(context) + "\n\n"
    if user_text:
        prompt += f"User message: {user_text}\n"
    if bot_reply:
        prompt += f"Bot reply: {bot_reply}\n"
    prompt += "\nOutput ONLY the search query or NONE."

    try:
        from core.chat.llm_providers import get_provider_by_key, get_generation_params

        provider = get_provider_by_key(
            provider_key, _providers_config(), 45.0, model_override=model_name,
        )
        if not provider:
            logger.warning(f"[LEONA-DISCORD] GIF query model {provider_key}/{model_name} unavailable")
            return ""

        gen_params = get_generation_params(provider_key, model_name, _providers_config())
        gen_params["model"] = model_name
        gen_params["max_tokens"] = max(20, min(120, int(max_tokens)))

        messages = [{"role": "user", "content": prompt}]
        response = provider.chat_completion(messages, tools=None, generation_params=gen_params)
        raw = ""
        if hasattr(response, "content") and response.content:
            raw = response.content
        elif isinstance(response, dict):
            raw = response.get("content", "")

        text = strip_think_tags(raw).strip().strip('"').strip("'")
        if not text or _NONE_RE.match(text):
            return ""
        if len(text) > 80:
            text = text[:80].rstrip()
        return text
    except Exception as e:
        logger.warning(f"[LEONA-DISCORD] GIF query LLM failed: {e}")
        return ""
