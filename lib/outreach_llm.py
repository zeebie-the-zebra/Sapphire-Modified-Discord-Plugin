"""Generate quiet-channel outreach text via Sapphire LLM."""

import logging

from plugins.leona_discord.lib.proactive_llm import run_proactive_llm

logger = logging.getLogger(__name__)


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

    return run_proactive_llm(
        system,
        prompt=prompt,
        account=account,
        provider_key=provider_key,
        model_name=model_name,
        max_tokens=max_tokens,
        log_label="Outreach",
    )
