"""Configurable post-send spelling mistakes for more human-like replies."""

from __future__ import annotations

import logging
import random
import re
from typing import Dict, List, Optional, Tuple

from plugins.leona_discord.lib.typo_wordlist import RAW_MISSPELLINGS

logger = logging.getLogger(__name__)

# 700+ correct→typo mappings live in typo_wordlist.py (function words, fat-finger
# transpositions, ie/ei traps, doubled letters, homophone slips, chat/tech terms).
COMMON_MISSPELLINGS: Dict[str, List[str]] = RAW_MISSPELLINGS

_WORD_RE_CACHE: Dict[str, re.Pattern] = {}


def _word_pattern(word: str) -> re.Pattern:
    key = word.lower()
    pat = _WORD_RE_CACHE.get(key)
    if pat is None:
        pat = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        _WORD_RE_CACHE[key] = pat
    return pat


def _apply_case(typo: str, original: str) -> str:
    if not original:
        return typo
    if original.isupper():
        return typo.upper()
    if original[0].isupper():
        return typo[0].upper() + typo[1:] if typo else typo
    return typo.lower()


def trigger_has_question_mark(trigger_content: str) -> bool:
    """True when the user's message contains a question mark."""
    return "?" in (trigger_content or "")


def introduce_common_typo(text: str) -> Optional[Tuple[str, str]]:
    """Replace one dictionary word with a misspelling.

    Returns ``(typo_text, corrected_text)`` or ``None`` if no substitution applied.
    """
    stripped = (text or "").strip()
    if len(stripped) < 8:
        return None

    candidates: List[Tuple[int, int, str, str, str]] = []
    for correct, typos in COMMON_MISSPELLINGS.items():
        for match in _word_pattern(correct).finditer(stripped):
            original = match.group(0)
            typo_form = random.choice(typos)
            candidates.append((
                match.start(),
                match.end(),
                original,
                correct,
                _apply_case(typo_form, original),
            ))

    if not candidates:
        return None

    start, end, original, _correct, typo_word = random.choice(candidates)
    typo_text = stripped[:start] + typo_word + stripped[end:]
    if typo_text == stripped:
        return None
    return typo_text, stripped


def plan_auto_typo(
    text: str,
    settings: dict,
    trigger_content: str,
) -> Optional[Tuple[float, str, str]]:
    """Plan a typo-then-fix edit when settings allow.

    Returns ``(delay_secs, text_to_send, text_after_edit)`` or ``None``.
    """
    if not settings.get("auto_typo_enabled", False):
        return None
    if not settings.get("message_edits_enabled", True):
        return None
    if trigger_has_question_mark(trigger_content):
        return None

    chance = max(0, min(100, int(settings.get("auto_typo_chance", 12) or 0)))
    if chance <= 0 or random.random() >= (chance / 100.0):
        return None

    pair = introduce_common_typo(text)
    if not pair:
        return None

    typo_text, corrected = pair
    delay_min = float(settings.get("auto_typo_delay_min", 2.0) or 2.0)
    delay_max = float(settings.get("auto_typo_delay_max", 6.0) or 6.0)
    if delay_max < delay_min:
        delay_min, delay_max = delay_max, delay_min
    delay = random.uniform(max(0.5, delay_min), max(delay_min, delay_max))

    logger.info(
        "[DISCORD] Auto-typo planned (delay=%.1fs): %r → %r",
        delay,
        typo_text[:80],
        corrected[:80],
    )
    return delay, typo_text, corrected


def misspelling_entry_count() -> int:
    """Return how many correct words have typo mappings (for tests/diagnostics)."""
    return len(COMMON_MISSPELLINGS)
