"""Sentiment-based silent reactions and emoji selection."""

import asyncio
import logging
import random
import re
import threading

from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)

_vader_analyser = None
_vader_lock = threading.Lock()

_distilbert_pipeline = None
_distilbert_lock = threading.Lock()
_DISTILBERT_MODEL = "cardiffnlp/twitter-roberta-base-sentiment-latest"

# Human-like reaction timing / removal
REACTION_DELAY_MIN, REACTION_DELAY_MAX = 1.0, 5.0
REACTION_REMOVE_CHANCE = 0.04          # ~4% (midpoint of 3–5%)
REACTION_REMOVE_DELAY_MIN, REACTION_REMOVE_DELAY_MAX = 30.0, 60.0

# Per-channel reaction memory (variety + preference learning)
_reaction_prefs_lock = threading.Lock()
_last_channel_reaction: dict[str, str] = {}
_channel_reaction_counts: dict[str, dict[str, int]] = {}

_TECH_CHANNEL_RE = re.compile(
    r"\b(dev|code|coding|tech|programming|python|javascript|typescript|rust|golang|"
    r"engineering|software|hardware|linux|server|ops|sre|api|debug|helpdesk|"
    r"support|infra|network|security|data|ml|ai)\b",
    re.I,
)
_TECH_PREFERRED = frozenset({"👀", "🧐", "💡", "🧠", "📚", "🤔", "💭", "❓", "🫡", "⁉️"})
_SOFT_EMOJIS = frozenset({
    "💕", "💞", "💓", "💗", "💖", "💘", "💝", "🥰", "😍", "😘", "💌", "🫶",
})

_QUESTION_RE = re.compile(r'\?')

_SENTIMENT_EMOJIS = {
    "very_positive": [
        "🎉", "🎊", "🥳", "🎈", "🏆", "🥇", "🥈", "🥉", "🏅", "🎖️",
        "👑", "💯", "🔥", "✨", "⭐", "🌟", "💫", "❤️", "🧡", "💛",
        "💚", "💙", "💜", "🖤", "🤍", "🤎", "💕", "💞", "💓", "💗",
        "💖", "💘", "💝", "💟", "💌", "😍", "🤩", "🥰", "😘", "😗",
        "☺️", "😊", "😇", "🤗", "🤠", "🤑", "😎", "🤓", "🧐",
        "👏", "🙌", "👐", "🤝", "🙏", "💪", "🦾", "🦿", "🦵", "🦶",
        "👍", "👎", "👊", "✋", "🤚", "🖐️", "✌️", "🤞", "🤟", "🤘",
        "👋", "🤙", "🖕", "👌", "🤌", "🤏", "✝️", "☝️", "🫵", "🫶",
    ],
    "positive": [
        "👍", "👎", "👏", "🙌", "🤝", "🙏", "💪", "✊", "👊", "✋",
        "🤚", "🖐️", "🤞", "🤟", "🤘", "👌", "🤌", "🤏", "☝️", "🫵",
        "❤️", "🧡", "💛", "💚", "💙", "💜", "💕", "💞", "💓", "💗",
        "💖", "💘", "💝", "💟", "💯", "🔥", "✨", "⭐", "🌟", "💫",
        "😊", "😇", "🤗", "😌", "🙂", "🙃", "😉", "🥰", "😍", "😘",
    ],
    "curious": [
        "👀", "🧐", "🤔", "💭", "🫣", "🫢", "🫡", "🫠", "🤨", "😐",
        "😶", "😶‍🌫️", "😏", "😒", "🙄", "😬", "😮‍💨", "😌", "🤷",
        "🤷‍♀️", "🤷‍♂️", "❓", "⁉️", "💡", "🧠", "🎓", "📚",
    ],
    "negative": [
        "😢", "😿", "🙀", "😾", "😞", "😔", "😟", "🙁", "☹️", "😕",
        "😣", "😖", "😫", "😩", "😤", "😠", "😡", "🤬", "😈", "👿",
        "💔", "❣️", "💜", "🖤", "🤍", "🤎", "💀", "☠️", "💩",
    ],
    "very_negative": [
        "😢", "💔", "😭", "🥺", "😞", "😔", "😟", "🙁", "☹️",
        "😿", "🙀", "😾", "😣", "😖", "😫", "😩", "😤", "😠",
        "😡", "🤬", "💀", "☠️", "🫂", "😰", "😥", "😓", "😪",
    ],
}

_DEFAULT_BLOCKED = {
    "negative": ["👍", "😂", "🤣"],
    "very_negative": ["👍", "😂", "🤣", "💀"],
}


def _get_vader():
    global _vader_analyser
    if _vader_analyser is not None:
        return _vader_analyser
    with _vader_lock:
        if _vader_analyser is not None:
            return _vader_analyser
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _vader_analyser = SentimentIntensityAnalyzer()
            logger.info("[DISCORD] VADER sentiment analyser loaded")
        except ImportError:
            logger.warning(
                "[DISCORD] vaderSentiment not installed — silent reactions disabled. "
                "Run: pip install vaderSentiment"
            )
            _vader_analyser = False
    return _vader_analyser


def _get_distilbert():
    global _distilbert_pipeline
    if _distilbert_pipeline is not None:
        return _distilbert_pipeline
    with _distilbert_lock:
        if _distilbert_pipeline is not None:
            return _distilbert_pipeline
        try:
            from transformers import pipeline as hf_pipeline
            logger.info(f"[DISCORD] Loading DistilBERT sentiment model ({_DISTILBERT_MODEL})…")
            _distilbert_pipeline = hf_pipeline(
                "sentiment-analysis",
                model=_DISTILBERT_MODEL,
                device=-1,
                truncation=True,
                max_length=128,
            )
            logger.info("[DISCORD] DistilBERT sentiment pipeline ready")
        except ImportError:
            logger.warning("[DISCORD] transformers/torch not installed — falling back to VADER")
            _distilbert_pipeline = False
        except Exception as e:
            logger.warning(f"[DISCORD] DistilBERT failed to load ({e}) — falling back to VADER")
            _distilbert_pipeline = False
    return _distilbert_pipeline


def _scored_text(content: str, context_messages: list = None) -> str:
    if context_messages:
        recent = context_messages[-4:]
        context_text = " ".join(
            m.get("clean_content", m.get("content", "")) for m in recent
        )
        return f"{context_text} {content}".strip()
    return content


def _sentiment_tier(content: str, context_messages: list = None, backend: str = "vader") -> str:
    scored_text = _scored_text(content, context_messages)

    if backend == "distilbert":
        pipe = _get_distilbert()
        if pipe:
            try:
                result = pipe(scored_text[:512])[0]
                label = result["label"].upper()
                score = result["score"]
                if label == "POSITIVE":
                    return "very_positive" if score >= 0.85 else "positive"
                if label == "NEGATIVE":
                    return "very_negative" if score >= 0.85 else "negative"
                return "curious" if _QUESTION_RE.search(content) else ""
            except Exception as e:
                logger.debug(f"[DISCORD] DistilBERT inference failed ({e}), falling back to VADER")

    vader = _get_vader()
    if not vader:
        return ""

    compound = vader.polarity_scores(scored_text)["compound"]
    if compound >= 0.5:
        return "very_positive"
    if compound >= 0.1:
        return "positive"
    if compound <= -0.5:
        return "very_negative"
    if compound <= -0.1:
        return "negative"
    return "curious" if _QUESTION_RE.search(content) else ""


def _blocked_for_tier(settings: dict, tier: str) -> set:
    rules = settings.get("reaction_blocked_rules")
    if not isinstance(rules, dict):
        rules = _DEFAULT_BLOCKED
    return set(rules.get(tier, []) or [])


def is_tech_channel(channel_name: str) -> bool:
    """Heuristic: dev/tech channel names get calmer reaction emoji."""
    return bool(channel_name and _TECH_CHANNEL_RE.search(channel_name))


def _record_reaction_choice(account: str, channel_id: str, emoji: str):
    key = state.channel_key(account, str(channel_id))
    with _reaction_prefs_lock:
        _last_channel_reaction[key] = emoji
        counts = _channel_reaction_counts.setdefault(key, {})
        counts[emoji] = counts.get(emoji, 0) + 1
        if len(counts) > 24:
            for old in sorted(counts, key=counts.get)[: len(counts) - 20]:
                counts.pop(old, None)


def _pick_from_candidates(candidates: list, account: str, channel_id: str) -> str:
    """Weighted pick — avoids repeating the last emoji, prefers channel history."""
    if not candidates:
        return ""
    key = state.channel_key(account, str(channel_id))
    with _reaction_prefs_lock:
        last = _last_channel_reaction.get(key)
        counts = dict(_channel_reaction_counts.get(key, {}))

    pool = list(candidates)
    if last and len(pool) > 1:
        filtered = [c for c in pool if c != last]
        if filtered:
            pool = filtered

    weights = [1.0 + counts.get(c, 0) * 0.35 for c in pool]
    return random.choices(pool, weights=weights, k=1)[0]


def _apply_channel_flavor(candidates: list, channel_name: str) -> list:
    """Tech channels: skip hearts, lean toward curious / thoughtful emoji."""
    if not candidates or not is_tech_channel(channel_name):
        return candidates
    filtered = [c for c in candidates if c not in _SOFT_EMOJIS]
    if filtered:
        candidates = filtered
    tech = [c for c in candidates if c in _TECH_PREFERRED]
    if tech and random.random() < 0.65:
        return tech
    return candidates


def pick_reaction_emoji(
    content: str,
    context_messages: list = None,
    backend: str = "vader",
    settings: dict = None,
    *,
    channel_name: str = "",
    account: str = "",
    channel_id: str = "",
) -> str:
    settings = settings or {}
    from plugins.leona_discord.lib.emoji_policy import custom_allowlist, pick_custom_reaction

    # Mix in server custom emoji when configured (~35% of silent reacts).
    if custom_allowlist(settings) and random.random() < 0.35:
        custom = pick_custom_reaction(settings)
        if custom:
            if account and channel_id:
                last_key = state.channel_key(account, str(channel_id))
                with _reaction_prefs_lock:
                    last = _last_channel_reaction.get(last_key)
                if custom != last or not last:
                    return custom
            else:
                return custom

    tier = _sentiment_tier(content, context_messages, backend)
    if not tier:
        return ""
    blocked = _blocked_for_tier(settings or {}, tier)
    candidates = [e for e in _SENTIMENT_EMOJIS.get(tier, []) if e not in blocked]
    candidates = _apply_channel_flavor(candidates, channel_name)
    if account and channel_id:
        return _pick_from_candidates(candidates, account, channel_id)
    return random.choice(candidates) if candidates else ""


async def _maybe_remove_reaction_later(
    account_name: str,
    channel_id: int,
    message_id: int,
    resolved_emoji,
):
    """Occasionally remove a reaction after a delay — 'changed my mind'."""
    if random.random() >= REACTION_REMOVE_CHANCE:
        return
    delay = random.uniform(REACTION_REMOVE_DELAY_MIN, REACTION_REMOVE_DELAY_MAX)
    await asyncio.sleep(delay)
    try:
        client = state._clients.get(account_name)
        if not client or not client.is_ready():
            return
        channel = client.get_channel(channel_id)
        if not channel:
            channel = await client.fetch_channel(channel_id)
        msg = await channel.fetch_message(int(message_id))
        await msg.remove_reaction(resolved_emoji, client.user)
        logger.info(
            f"[DISCORD] Removed reaction {resolved_emoji} from {message_id} (changed mind)"
        )
    except Exception as e:
        logger.debug(f"[DISCORD] Reaction removal failed: {e}")


async def add_reaction_humanized(
    message,
    account_name: str,
    guild_id: str,
    emoji: str,
    channel_id_str: str,
):
    """Pause, react, record preference, and maybe remove later."""
    from plugins.leona_discord.lib.cooldowns import set_reaction_cooldown
    from plugins.leona_discord.lib.emoji_policy import resolve_reaction_emoji

    await asyncio.sleep(random.uniform(REACTION_DELAY_MIN, REACTION_DELAY_MAX))
    resolved = resolve_reaction_emoji(emoji, guild_id)
    await message.add_reaction(resolved)
    set_reaction_cooldown(account_name, guild_id, channel_id_str)
    _record_reaction_choice(account_name, channel_id_str, emoji)
    logger.info(
        f"[DISCORD] Silent react {resolved} → {message.id} "
        f"in #{getattr(message.channel, 'name', channel_id_str)}"
    )
    asyncio.create_task(
        _maybe_remove_reaction_later(
            account_name,
            int(channel_id_str),
            int(message.id),
            resolved,
        )
    )
    return resolved


async def try_silent_react(
    message,
    account_name: str,
    settings: dict,
    guild_id: str = "",
    *,
    force: bool = False,
):
    import asyncio
    import functools

    from plugins.leona_discord.lib.context_cache import mark_reacted
    from plugins.leona_discord.lib.gates import reaction_allowed
    from plugins.leona_discord.lib.history import get_history_snapshot
    from plugins.leona_discord.lib import state

    channel_id_str = str(message.channel.id)
    channel_name = getattr(message.channel, "name", "") or ""
    if not reaction_allowed(settings, account_name, guild_id, channel_id_str):
        return
    if not settings.get("react_to_trigger", True):
        return

    if not force:
        chance = max(0, min(100, int(settings.get("reaction_chance", 50))))
        if chance == 0:
            return
        if chance < 100 and random.random() >= (chance / 100.0):
            return

    if not (message.clean_content or "").strip():
        return

    channel_key = state.channel_key(account_name, channel_id_str)
    history_snapshot = get_history_snapshot(channel_key)
    backend = settings.get("reaction_backend", "vader")

    # Run sentiment analysis in a thread so DistilBERT/VADER never blocks
    # the Discord gateway heartbeat.
    loop = asyncio.get_running_loop()
    emoji = await loop.run_in_executor(
        None,
        functools.partial(
            pick_reaction_emoji,
            message.clean_content or "",
            context_messages=history_snapshot,
            backend=backend,
            settings=settings,
            channel_name=channel_name,
            account=account_name,
            channel_id=channel_id_str,
        ),
    )
    if not emoji:
        return

    msg_id = str(message.id)
    if not mark_reacted(account_name, channel_id_str, msg_id, emoji):
        return

    try:
        await add_reaction_humanized(
            message, account_name, guild_id, emoji, channel_id_str,
        )
    except Exception as e:
        logger.warning(f"[DISCORD] Silent react failed: {e}")


def build_reaction_hint(effective: dict) -> str:
    if not effective.get("reactions_enabled", False):
        return ""

    chance = effective.get("reaction_chance", 50)
    parts = []
    if effective.get("react_to_trigger", True):
        from plugins.leona_discord.lib.emoji_policy import custom_allowlist
        custom_list = custom_allowlist(effective)
        custom_hint = ""
        if custom_list:
            custom_hint = (
                " Prefer these server custom emojis when they fit the vibe "
                f"(copy exactly): {' '.join(custom_list)}."
                " You can also use the short form [react:<:name:>] — the name is enough."
            )
        parts.append(
            "To react to the message you're replying to, embed `[react:emoji]` "
            "anywhere in your response (e.g. `[react:🔥]` or `[react:<:BUG:>]` for a server emoji). "
            "Standard Unicode emoji always work."
            + custom_hint +
            " The tag is stripped before sending — the user won't see it."
        )
    if effective.get("react_to_any", False):
        parts.append(
            "To react to any other message, call `discord_add_reaction` "
            "with a message_id from `discord_read_messages`."
        )
    if not parts:
        return ""
    return (
        "Reactions are enabled. "
        + " ".join(parts)
        + f" React naturally and sparingly — {chance}% chance each fires (handled automatically)."
    )
