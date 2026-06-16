"""Generate quiet-channel outreach text via Sapphire LLM."""

import logging

from plugins.leona_discord.lib.think_tags import strip_think_tags

logger = logging.getLogger(__name__)


def _providers_config():
    import config as app_config
    return {
        **(getattr(app_config, "LLM_PROVIDERS", None) or {}),
        **(getattr(app_config, "LLM_CUSTOM_PROVIDERS", None) or {}),
    }


def generate_outreach(
    system,
    *,
    account: str = "",
    guild_name: str = "",
    channel_name: str = "",
    instructions: str = "",
    recent_chat: list = None,
    quiet_hours: float = 0.0,
    provider_key: str = "",
    model_name: str = "",
    max_tokens: int = 180,
) -> str:
    """Return outreach text from the LLM, or empty string on failure."""
    if not system or not getattr(system, "llm_chat", None):
        logger.warning("[LEONA-DISCORD] Outreach LLM: no system.llm_chat available")
        return ""

    from plugins.leona_discord.lib.bot_identity import (
        bot_identity_fields,
        build_proactive_post_hint,
        strip_self_address,
    )

    fields = bot_identity_fields(account) if account else {}
    identity_hint = build_proactive_post_hint(fields, purpose="outreach")

    instructions = (instructions or "").strip() or (
        "Casually restart conversation in this Discord channel. "
        "Write one short message like a friend checking in — not an announcement or bot greeting. "
        "A question or light observation works well. Vary your wording."
    )

    context_parts = []
    if identity_hint:
        context_parts.append(identity_hint)
    if guild_name:
        context_parts.append(f"Server: {guild_name}")
    if channel_name:
        context_parts.append(f"Channel: #{channel_name}")
    if quiet_hours >= 1.0:
        context_parts.append(f"The channel has been quiet for about {int(quiet_hours)} hour(s).")
    if recent_chat:
        lines = recent_chat[-10:]
        if lines:
            context_parts.append("Recent channel activity (may be stale):\n" + "\n".join(lines))

    prompt = instructions
    if context_parts:
        prompt += "\n\n---\nContext:\n" + "\n".join(context_parts)
    prompt += (
        "\n\n---\nWrite ONLY the message to post in Discord — no quotes, labels, or explanation. "
        "Keep it to one casual sentence unless a second short clause feels natural. "
        "Address the channel or humans in it — never yourself by name."
    )

    try:
        llm = system.llm_chat
        if provider_key and model_name:
            from core.chat.llm_providers import get_provider_by_key, get_generation_params
            provider = get_provider_by_key(provider_key, _providers_config(), 60.0, model_override=model_name)
            if not provider:
                logger.warning(f"[LEONA-DISCORD] Outreach model {provider_key}/{model_name} unavailable")
                return ""
            gen_params = get_generation_params(provider_key, model_name, _providers_config())
            gen_params["model"] = model_name
        else:
            provider_key, provider, model_override = llm._select_provider()
            from core.chat.llm_providers import get_generation_params
            effective_model = model_override or provider.model
            gen_params = get_generation_params(provider_key, effective_model, _providers_config())
            if model_override:
                gen_params["model"] = model_override

        gen_params["max_tokens"] = max(40, min(500, int(max_tokens)))

        messages = [{"role": "user", "content": prompt}]
        llm_response = llm.tool_engine.call_llm_with_metrics(
            provider, messages, gen_params, tools=None,
        )
        raw = ""
        if llm_response and getattr(llm_response, "content", None):
            raw = llm_response.content
        text = strip_think_tags(raw)
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1].strip()
        if len(text) > 2000:
            text = text[:1997].rstrip() + "…"
        return strip_self_address(text, fields)
    except Exception as e:
        logger.warning(f"[LEONA-DISCORD] Outreach LLM failed: {e}")
        return ""
