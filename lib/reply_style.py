"""Human-like quote-reply, emoji, and post-send edit behavior."""

import logging
import random
import re
from typing import Optional, Tuple

from plugins.leona_discord.lib.cooldowns import is_engaged
from plugins.leona_discord.lib.history import get_history_snapshot
from plugins.leona_discord.lib import state

logger = logging.getLogger(__name__)

# Quote-reply probability bands
QUOTE_BASE = 0.40
QUOTE_DM_MIN, QUOTE_DM_MAX = 0.10, 0.20
QUOTE_BUSY_BATCH = 0.65
QUOTE_BUSY_HISTORY = 0.55
QUOTE_THREAD_BOOST = 0.55
BUSY_BATCH_THRESHOLD = 5
BUSY_HISTORY_THRESHOLD = 2

# Post-send edits
EDIT_CHANCE = 0.04          # ~4% (midpoint of 3–5%)
EDIT_DELAY_MIN, EDIT_DELAY_MAX = 2.0, 5.0
THOUGHT_SUFFIXES = (
    " lol",
    " haha",
    " anyway",
    " — wait nvm",
    " actually",
    " idk",
)

# Casual emoji suffix on short positive replies
EMOJI_SUFFIX_CHANCE = 0.125  # ~12.5% (midpoint of 10–15%)
SHORT_REPLY_EMOJI_MAX_CHARS = 80
CASUAL_POSITIVE_EMOJIS = ("😊", "😄", "🙂", "✨", "👍", "😅", "💀", "🔥")

_QUESTION_RE = re.compile(r"\?\s*$|^\s*(who|what|when|where|why|how|is|are|do|does|did|can|could|would|will|should)\b", re.I)
_JOKE_MARKERS = ("lol", "lmao", "haha", "hehe", "😂", "🤣", "jk", "nah", "bruh")
_EMOJI_TAIL_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+$",
)


def _is_question(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    # Use the last non-empty line — trigger may be multi-line in a batch
    last_line = stripped.split("\n")[-1].strip()
    return bool(_QUESTION_RE.search(last_line))


def _trigger_has_media(event_data: dict) -> bool:
    if event_data.get("image_urls"):
        return True
    if event_data.get("images"):
        return True
    if event_data.get("image_described"):
        return True
    return False


def _looks_like_joke_or_comment(trigger_content: str, reply_text: str) -> bool:
    """Casual banter — better as a standalone channel message."""
    if _is_question(trigger_content):
        return False
    reply = (reply_text or "").strip()
    if not reply or "?" in reply:
        return False
    lower = reply.lower()
    if any(marker in lower for marker in _JOKE_MARKERS):
        return True
    # Short non-answer aside
    return len(reply) <= 120 and not _is_question(reply)


def _is_conversation_thread(channel_key: str, trigger_author_id: str) -> bool:
    """Back-and-forth with the same user in recent history."""
    if not trigger_author_id:
        return False
    history = get_history_snapshot(channel_key)[-8:]
    bot_msgs = sum(
        1 for m in history
        if m.get("is_bot") or str(m.get("author_id")) == "bot"
    )
    user_msgs = sum(
        1 for m in history
        if str(m.get("author_id")) == str(trigger_author_id)
    )
    return bot_msgs >= 1 and user_msgs >= 2


def _ends_with_emoji(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    return bool(_EMOJI_TAIL_RE.search(stripped[-1]))


def _positive_sentiment(text: str) -> bool:
    from plugins.leona_discord.lib.reactions import _sentiment_tier
    tier = _sentiment_tier(text or "")
    return tier in ("positive", "very_positive")


def compute_quote_reply_chance(
    event_data: dict,
    trigger_content: str,
    reply_text: str,
    *,
    account: str,
    channel_id: str,
) -> float:
    """Return the probability [0, 1] of sending as a quote-reply."""
    if _is_question(trigger_content):
        return 1.0
    if _trigger_has_media(event_data):
        return 0.0
    if _looks_like_joke_or_comment(trigger_content, reply_text):
        return 0.0
    # Bot just replied — avoid double-quoting in rapid back-and-forth
    if is_engaged(account, channel_id):
        return 0.0

    chance = QUOTE_BASE

    if event_data.get("is_dm"):
        chance = random.uniform(QUOTE_DM_MIN, QUOTE_DM_MAX)
    elif int(event_data.get("batch_size") or 1) > BUSY_BATCH_THRESHOLD:
        chance = QUOTE_BUSY_BATCH
    elif len(event_data.get("recent_history") or []) > BUSY_HISTORY_THRESHOLD:
        chance = max(chance, QUOTE_BUSY_HISTORY)

    channel_key = state.channel_key(account, str(channel_id))
    if _is_conversation_thread(channel_key, event_data.get("author_id", "")):
        chance = max(chance, QUOTE_THREAD_BOOST)

    return min(1.0, max(0.0, chance))


def should_quote_reply(
    event_data: dict,
    trigger_content: str,
    reply_text: str,
    *,
    account: str,
    channel_id: str,
) -> bool:
    chance = compute_quote_reply_chance(
        event_data, trigger_content, reply_text,
        account=account, channel_id=channel_id,
    )
    if chance >= 1.0:
        return True
    if chance <= 0.0:
        return False
    return random.random() < chance


def maybe_append_casual_emoji(text: str) -> str:
    """Occasionally suffix a casual emoji on short positive replies."""
    stripped = (text or "").strip()
    if not stripped or len(stripped) > SHORT_REPLY_EMOJI_MAX_CHARS:
        return text
    if _ends_with_emoji(stripped):
        return text
    if not _positive_sentiment(stripped):
        return text
    if random.random() >= EMOJI_SUFFIX_CHANCE:
        return text
    emoji = random.choice(CASUAL_POSITIVE_EMOJIS)
    return f"{stripped} {emoji}"


def _introduce_subtle_typo(text: str) -> str:
    words = text.split()
    candidates = [
        i for i, w in enumerate(words)
        if len(w) >= 5 and any(c.isalpha() for c in w)
    ]
    if not candidates:
        return text
    idx = random.choice(candidates)
    word = words[idx]
    alpha_positions = [i for i, c in enumerate(word) if c.isalpha()]
    if len(alpha_positions) < 2:
        return text
    pos = random.choice(alpha_positions[1:-1] if len(alpha_positions) > 2 else alpha_positions[1:])
    words[idx] = word[:pos] + word[pos] + word[pos:]
    return " ".join(words)


def _replace_trailing_typo_phrase(sent: str, edited: str) -> Optional[str]:
    """Replace a trailing typo phrase with the corrected text (single-line replies)."""
    if not sent or not edited or edited in sent or sent == edited:
        return None
    words_sent = sent.split()
    words_edit = edited.split()
    if not words_sent or not words_edit:
        return None
    for n in range(min(6, len(words_sent)), 0, -1):
        tail = " ".join(words_sent[-n:])
        if tail == edited:
            return None
        if words_sent[-1].lower() == words_edit[-1].lower():
            prefix = " ".join(words_sent[:-n])
            return f"{prefix} {edited}".strip() if prefix else edited
    return None


def plan_explicit_edit(sent_text: str, edited_text: str) -> Optional[Tuple[float, str, str]]:
    """Plan a Discord message edit requested by the LLM via ``[edit:…]``."""
    sent = (sent_text or "").strip()
    edited = (edited_text or "").strip()
    if not sent or not edited or sent == edited:
        return None
    delay = random.uniform(EDIT_DELAY_MIN, EDIT_DELAY_MAX)

    # Multiline replies: [edit:…] usually fixes the last line, not the whole message.
    if "\n" in sent and edited not in sent:
        lines = sent.splitlines()
        if len(lines) > 1:
            fixed = "\n".join(lines[:-1] + [edited])
            if fixed != sent:
                return delay, sent, fixed

    trailing = _replace_trailing_typo_phrase(sent, edited)
    if trailing and trailing != sent:
        return delay, sent, trailing

    return delay, sent, edited


def plan_post_send_edit(text: str) -> Optional[Tuple[float, str, str]]:
    """Plan an occasional typo-fix or trailing-thought edit.

    Returns ``(delay_secs, text_to_send, text_after_edit)`` or ``None``.
    """
    stripped = (text or "").strip()
    if len(stripped) < 8:
        return None
    if random.random() >= EDIT_CHANCE:
        return None

    delay = random.uniform(EDIT_DELAY_MIN, EDIT_DELAY_MAX)
    if random.random() < 0.5:
        typo = _introduce_subtle_typo(stripped)
        if typo == stripped:
            return None
        return delay, typo, stripped

    suffix = random.choice(THOUGHT_SUFFIXES)
    if stripped.lower().endswith(suffix.strip().lower()):
        return None
    return delay, stripped, stripped + suffix
