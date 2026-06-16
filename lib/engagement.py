"""Engagement patterns: topics, threads, channel lurk weights, reply length."""

import random
import re
import threading
from collections import deque

# Topic interest (per channel)
_TOPIC_SCORES: dict[str, dict[str, float]] = {}
_TOPIC_LOCK = threading.Lock()
_TOPIC_MIN_WORD_LEN = 4
_TOPIC_BOOST_FACTOR = 1.28
_TOPIC_SUPPRESS_FACTOR = 0.72
_TOPIC_SCORE_THRESHOLD = 0.45
_TOPIC_SUPPRESS_THRESHOLD = -0.35
_MAX_TOPICS_PER_CHANNEL = 48

# Thread continuation
THREAD_REPLY_FLOOR_CHANCE = 65
THREAD_REPLY_MULTIPLIER = 1.45

# Reply length memory
_REPLY_LENGTHS: dict[str, deque] = {}
_REPLY_LENGTH_LOCK = threading.Lock()
_REPLY_LENGTH_WINDOW = 6
_LONG_REPLY_AVG_CHARS = 150
_BREVITY_HINT_CHANCE = 0.35
_BREVITY_TARGET_CHARS = 60

_STOPWORDS = frozenset({
    "about", "after", "again", "also", "been", "before", "being", "could",
    "does", "doing", "done", "from", "have", "having", "here", "into",
    "just", "like", "make", "more", "much", "only", "really", "should",
    "some", "than", "that", "their", "them", "then", "there", "these",
    "they", "this", "those", "very", "want", "what", "when", "where",
    "which", "while", "will", "with", "would", "your", "you're", "youre",
    "https", "http", "discord", "message", "channel",
})

_WORD_RE = re.compile(r"[a-z][a-z0-9'-]{3,}", re.I)


def extract_topics(text: str) -> set[str]:
    if not text:
        return set()
    return {
        m.group(0).lower()
        for m in _WORD_RE.finditer(text)
        if m.group(0).lower() not in _STOPWORDS
    }


def _decay_topic_scores(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return scores
    age_factor = 0.98  # gentle decay on read
    return {k: v * age_factor for k, v in scores.items() if v * age_factor > 0.05}


def record_topics_on_reply(channel_key: str, content: str):
    """Boost topic scores when the bot replies."""
    topics = extract_topics(content)
    if not topics:
        return
    with _TOPIC_LOCK:
        scores = _decay_topic_scores(_TOPIC_SCORES.setdefault(channel_key, {}))
        for topic in topics:
            scores[topic] = scores.get(topic, 0.0) + 1.0
        if len(scores) > _MAX_TOPICS_PER_CHANNEL:
            for stale in sorted(scores, key=scores.get)[: len(scores) - _MAX_TOPICS_PER_CHANNEL]:
                scores.pop(stale, None)
        _TOPIC_SCORES[channel_key] = scores


def record_topics_skipped(channel_key: str, content: str):
    """Nudge topic scores down when the bot saw a topic but chose not to reply."""
    topics = extract_topics(content)
    if not topics:
        return
    with _TOPIC_LOCK:
        scores = _decay_topic_scores(_TOPIC_SCORES.setdefault(channel_key, {}))
        for topic in topics:
            scores[topic] = scores.get(topic, 0.0) - 0.35
        _TOPIC_SCORES[channel_key] = scores


def _topic_score_for_message(channel_key: str, content: str) -> float:
    topics = extract_topics(content)
    if not topics:
        return 0.0
    with _TOPIC_LOCK:
        scores = _TOPIC_SCORES.get(channel_key, {})
        return sum(scores.get(t, 0.0) for t in topics) / len(topics)


def apply_topic_interest(settings: dict, channel_key: str, content: str) -> dict:
    score = _topic_score_for_message(channel_key, content)
    if score >= _TOPIC_SCORE_THRESHOLD:
        factor = _TOPIC_BOOST_FACTOR
    elif score <= _TOPIC_SUPPRESS_THRESHOLD:
        factor = _TOPIC_SUPPRESS_FACTOR
    else:
        return settings
    out = dict(settings)
    for key in ("human_response_chance", "bot_response_chance"):
        try:
            val = int(out.get(key, 0))
            out[key] = max(0, min(100, int(val * factor)))
        except (TypeError, ValueError):
            pass
    return out


def apply_channel_engagement_weight(settings: dict) -> dict:
    """Scale reply chances by per-channel engagement_weight (1–100)."""
    try:
        weight = int(settings.get("engagement_weight", 100))
    except (TypeError, ValueError):
        return settings
    weight = max(1, min(100, weight))
    if weight == 100:
        return settings
    out = dict(settings)
    for key in ("human_response_chance", "bot_response_chance"):
        try:
            val = int(out.get(key, 0))
            out[key] = max(0, min(100, int(val * weight / 100)))
        except (TypeError, ValueError):
            pass
    return out


def apply_thread_reply_boost(settings: dict, is_thread_reply: bool) -> dict:
    """Stronger continuation when someone replies directly to the bot's message."""
    if not is_thread_reply:
        return settings
    out = dict(settings)
    try:
        base = int(out.get("human_response_chance", 15))
    except (TypeError, ValueError):
        base = 15
    boosted = int(base * THREAD_REPLY_MULTIPLIER)
    out["human_response_chance"] = min(95, max(THREAD_REPLY_FLOOR_CHANCE, boosted))
    return out


def apply_engagement_adjustments(
    settings: dict,
    *,
    channel_key: str,
    message_content: str,
    is_thread_reply: bool = False,
) -> dict:
    """Apply topic, thread, and per-channel engagement modifiers."""
    out = apply_channel_engagement_weight(settings)
    out = apply_topic_interest(out, channel_key, message_content)
    out = apply_thread_reply_boost(out, is_thread_reply)
    return out


async def is_reply_to_bot_message(message, client) -> bool:
    """True when this message is a direct reply to one of the bot's messages."""
    ref = message.reference
    if not ref or not ref.message_id:
        return False
    resolved = getattr(ref, "resolved", None)
    if resolved is not None:
        try:
            return resolved.author.id == client.user.id
        except Exception:
            pass
    try:
        parent = await message.channel.fetch_message(ref.message_id)
        return parent.author.id == client.user.id
    except Exception:
        return False


def record_reply_length(channel_key: str, length: int):
    with _REPLY_LENGTH_LOCK:
        if channel_key not in _REPLY_LENGTHS:
            _REPLY_LENGTHS[channel_key] = deque(maxlen=_REPLY_LENGTH_WINDOW)
        _REPLY_LENGTHS[channel_key].append(max(0, int(length)))


def average_recent_reply_length(channel_key: str) -> float:
    with _REPLY_LENGTH_LOCK:
        dq = _REPLY_LENGTHS.get(channel_key)
        if not dq:
            return 0.0
        return sum(dq) / len(dq)


def reply_length_hint(channel_key: str) -> str:
    """Occasionally nudge the LLM toward a short one-liner after long replies."""
    avg = average_recent_reply_length(channel_key)
    if avg < _LONG_REPLY_AVG_CHARS:
        return ""
    if random.random() >= _BREVITY_HINT_CHANCE:
        return ""
    return (
        f"Your recent messages in this channel have averaged ~{int(avg)} characters — "
        f"this time aim for one short line (under ~{_BREVITY_TARGET_CHARS} chars) "
        "if it fits. Match the conversation pace; don't force brevity if a longer "
        "answer is needed."
    )
