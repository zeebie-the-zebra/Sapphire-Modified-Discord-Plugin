"""Parse and strip LLM inline Discord tags ([edit:], [react:], [gif:], [break])."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from plugins.leona_discord.lib.think_tags import strip_think_tags

_PLACEHOLDER_EMOJI_MAP = {
    "flame": "🔥",
    "fire": "🔥",
    "thumbs up": "👍",
    "thumbsup": "👍",
    "thumb up": "👍",
    "heart": "❤️",
    "smile": "😊",
    "grin": "😄",
    "laugh": "😂",
    "cry": "😭",
    "sad": "😢",
    "eyes": "👀",
    "sparkles": "✨",
    "moon": "🌙",
    "wave": "👋",
}


def normalize_placeholder_emoji(text: str) -> str:
    """Convert common LLM emoji placeholders like <flame emoji> to real emoji."""
    if not text:
        return text

    def repl(match):
        inner = (match.group(1) or "").strip().lower()
        inner = re.sub(r"\s+", " ", inner)
        inner = inner.replace("emoji:", "").replace("emote:", "").strip()
        inner = inner.replace(" emoji", "").strip()
        return _PLACEHOLDER_EMOJI_MAP.get(inner, match.group(0))

    return re.sub(r"<\s*([^<>]{1,40}?)\s*>", repl, text)


def strip_unknown_emoji_placeholders(text: str) -> str:
    """Remove unresolved angle-bracket emoji placeholders from model output."""
    if not text:
        return text

    def repl(match):
        inner = (match.group(1) or "").strip().lower()
        if inner.startswith("@") or inner.startswith("#"):
            return match.group(0)
        if "emoji" in inner or "emote" in inner:
            return ""
        return match.group(0)

    return re.sub(r"<\s*([^<>]{1,60}?)\s*>", repl, text)


def strip_malformed_react_tag(text: str) -> str:
    """Drop trailing malformed [react:... fragments missing closing bracket."""
    if not text:
        return text
    return re.sub(r"\s*\[react:[^\]\n]{1,64}$", "", text, flags=re.IGNORECASE).rstrip()


def strip_malformed_gif_tag(text: str) -> str:
    """Drop trailing malformed [gif:... fragments missing closing bracket."""
    if not text:
        return text
    return re.sub(r"\s*\[gif:[^\]\n]{1,120}$", "", text, flags=re.IGNORECASE).rstrip()


def strip_malformed_edit_tag(text: str) -> str:
    """Drop trailing malformed [edit:... fragments missing closing bracket."""
    if not text:
        return text
    return re.sub(r"\s*\[edit:[^\]\n]{1,1900}$", "", text, flags=re.IGNORECASE).rstrip()


def strip_orphan_inline_tag_fragments(text: str) -> str:
    """Remove any remaining inline tag syntax the model left in visible text."""
    if not text:
        return text
    cleaned = text
    cleaned = re.sub(r"\[react:[^\]\n]{0,64}\]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[gif:[^\]\n]{0,120}\]?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\[edit:[^\]\n]{0,1900}\]?", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


@dataclass
class ParsedInlineTags:
    clean: str
    react_tags: List[str] = field(default_factory=list)
    gif_tags: List[str] = field(default_factory=list)
    edit_tags: List[str] = field(default_factory=list)

    @property
    def inline_gif_query(self) -> str:
        return self.gif_tags[0].strip() if self.gif_tags else ""

    @property
    def inline_edit_text(self) -> str:
        return self.edit_tags[-1].strip() if self.edit_tags else ""

    def has_inline_tags(self) -> bool:
        return bool(self.react_tags or self.gif_tags or self.edit_tags)


def parse_inline_tags(text: str, *, strip_think: bool = True) -> ParsedInlineTags:
    """Extract inline tags and return Discord-safe visible text."""
    clean = (text or "").strip()
    if strip_think:
        clean = strip_think_tags(clean)
    clean = normalize_placeholder_emoji(clean)
    clean = strip_unknown_emoji_placeholders(clean)

    malformed_edits: List[str] = []
    malformed_edit = re.search(r"\[edit:([^\]\n]{1,1900})$", clean, flags=re.IGNORECASE)
    if malformed_edit:
        malformed_edits.append(malformed_edit.group(1).strip())
        clean = clean[:malformed_edit.start()].rstrip()

    clean = strip_malformed_react_tag(clean)
    clean = strip_malformed_gif_tag(clean)

    react_tags = re.findall(r"\[react:([^\]]{1,64})\]", clean)
    clean = re.sub(r"\[react:[^\]]{1,64}\]", "", clean).strip()

    gif_tags = re.findall(r"\[gif:([^\]]{1,120})\]", clean)
    clean = re.sub(r"\[gif:[^\]]{1,120}\]", "", clean).strip()

    edit_tags = re.findall(r"\[edit:([^\]]{1,1900})\]", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\[edit:[^\]]{1,1900}\]", "", clean, flags=re.IGNORECASE).strip()
    edit_tags.extend(malformed_edits)

    clean = strip_orphan_inline_tag_fragments(clean)

    return ParsedInlineTags(
        clean=clean,
        react_tags=react_tags,
        gif_tags=gif_tags,
        edit_tags=edit_tags,
    )


def sanitize_discord_text(text: str) -> str:
    """Strip inline tags for paths that send text directly (e.g. discord_send_message)."""
    return parse_inline_tags(text).clean
