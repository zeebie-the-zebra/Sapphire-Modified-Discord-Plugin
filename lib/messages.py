"""Discord message splitting utilities."""

import random
import re

from plugins.leona_discord.lib.constants import DISCORD_MSG_LIMIT

# Chance each bullet line becomes its own Discord message (else the full list stays together).
BULLET_SPLIT_EACH_CHANCE = 0.30

_BULLET_LINE_RE = re.compile(r"^\s*([-*•]|\d+\.)\s+")
_EMOJI_LEAD_RE = re.compile(
    r"^([\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+)\s+(.+)$",
    re.DOTALL,
)


def split_natural_segments(text: str, *, split_bullets: bool | None = None) -> list[str]:
    """Split at paragraphs, bullet lines, and leading emoji clusters."""
    stripped = (text or "").strip()
    if not stripped:
        return []

    if split_bullets is None:
        split_bullets = random.random() < BULLET_SPLIT_EACH_CHANCE

    segments: list[str] = []
    for paragraph in re.split(r"\n\s*\n+", stripped):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        segments.extend(_split_bullet_lines(paragraph, split_each=split_bullets))

    out: list[str] = []
    for seg in segments:
        out.extend(_split_emoji_lead(seg))
    return [s for s in out if s.strip()]


def _split_bullet_lines(block: str, *, split_each: bool = True) -> list[str]:
    lines = block.splitlines()
    if not any(_BULLET_LINE_RE.match(line) for line in lines):
        return [block]

    segments: list[str] = []
    prose: list[str] = []
    bullet_run: list[str] = []

    def flush_prose() -> None:
        nonlocal prose
        if prose:
            joined = "\n".join(prose).strip()
            if joined:
                segments.append(joined)
            prose = []

    def flush_bullets() -> None:
        nonlocal bullet_run
        if bullet_run:
            segments.append("\n".join(bullet_run))
            bullet_run = []

    for line in lines:
        if _BULLET_LINE_RE.match(line):
            flush_prose()
            if split_each:
                segments.append(line.strip())
            else:
                bullet_run.append(line.strip())
        else:
            if split_each:
                flush_prose()
                prose.append(line)
            else:
                flush_bullets()
                prose.append(line)

    if split_each:
        flush_prose()
    else:
        flush_bullets()
        flush_prose()
    return segments or [block]


def _split_emoji_lead(segment: str) -> list[str]:
    seg = segment.strip()
    if not seg:
        return []
    match = _EMOJI_LEAD_RE.match(seg)
    if match and match.group(2).strip():
        return [match.group(1).strip(), match.group(2).strip()]
    return [seg]


def _split_to_limit(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        chunk = remaining[:limit]
        last_newline = chunk.rfind("\n")

        if last_newline > limit // 2:
            split_point = last_newline + 1
        else:
            last_punct = max(
                chunk.rfind(". "),
                chunk.rfind("! "),
                chunk.rfind("? "),
                chunk.rfind(".\n"),
                chunk.rfind("!\n"),
                chunk.rfind("?\n"),
            )
            if last_punct > limit // 2:
                split_point = last_punct + 1
            else:
                split_point = limit

        chunks.append(remaining[:split_point].strip())
        remaining = remaining[split_point:].strip()

    return chunks


def split_message(
    text: str,
    limit: int = DISCORD_MSG_LIMIT,
    *,
    split_bullets: bool | None = None,
) -> list[str]:
    """Split text into Discord-sized messages at natural boundaries."""
    segments = split_natural_segments(text, split_bullets=split_bullets)
    if not segments:
        return [text] if text else []

    chunks: list[str] = []
    for segment in segments:
        chunks.extend(_split_to_limit(segment, limit))
    return chunks or [text]
