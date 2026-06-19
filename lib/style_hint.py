"""Channel vibe guidance injected into the LLM prompt.

Tells the bot how to behave in each channel: message length norms,
time of day awareness, "you're in a casual Discord chat" framing.
"""

from datetime import datetime


def _local_hour() -> int:
    """Hour (0–23) in the user's configured timezone, matching continuity prompts."""
    try:
        import config as _cfg
        tz_name = getattr(_cfg, "USER_TIMEZONE", "") or ""
        if tz_name:
            from zoneinfo import ZoneInfo
            return datetime.now(ZoneInfo(tz_name)).hour
        return datetime.now().astimezone().hour
    except Exception:
        return datetime.now().hour


def build_style_hint(guild_name: str, channel_name: str, batch_size: int,
                     is_dm: bool = False) -> str:
    """Generate a short style hint for the LLM based on channel context.

    Returns 1-2 sentences of framing guidance.  Injected after the
    user message and before reaction/gif hints.
    """
    parts = []

    # Time-of-day awareness (user timezone — same clock as "Current time:" in the prompt)
    hour = _local_hour()
    if 5 <= hour < 12:
        parts.append("It's morning — keep the energy warm and fresh.")
    elif 12 <= hour < 17:
        parts.append("It's afternoon — casual and relaxed tone.")
    elif 17 <= hour < 22:
        parts.append("It's evening — winding down, conversational pace.")
    else:
        parts.append("It's late — brief and low-key if you respond at all.")

    # Channel context
    if is_dm:
        parts.append(
            "This is a DM — talk like a friend in a private conversation. "
            "Short, natural messages. No performative energy."
        )
    elif batch_size > 3:
        parts.append(
            "The conversation is active — keep your message short "
            "(1-2 sentences). Don't interrupt the flow."
        )
    else:
        parts.append(
            "You're in a Discord chat. Write like a real person texting — "
            "casual, concise, natural. Avoid essays. "
            "Use [break] to split into 2-3 short messages when you have "
            "multiple thoughts. Vary your length."
        )

    return "\n".join(parts)
