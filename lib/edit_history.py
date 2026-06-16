"""Track bot message edits for natural follow-up patterns."""

import threading
import time
from collections import deque

_EDIT_HISTORY: dict[str, deque] = {}
_EDIT_LOCK = threading.Lock()
_MAX_EDITS_PER_CHANNEL = 8
_EDIT_HINT_MAX_AGE_SECS = 3600.0


def record_edit(
    channel_key: str,
    message_id,
    sent_text: str,
    edited_text: str,
    *,
    kind: str = "edit",
):
    """Remember a post-send edit in this channel."""
    if not channel_key or sent_text == edited_text:
        return
    entry = {
        "message_id": str(message_id),
        "sent": sent_text.strip(),
        "edited": edited_text.strip(),
        "kind": kind,
        "at": time.time(),
    }
    with _EDIT_LOCK:
        dq = _EDIT_HISTORY.setdefault(channel_key, deque(maxlen=_MAX_EDITS_PER_CHANNEL))
        dq.append(entry)


def build_edit_awareness_hint(channel_key: str) -> str:
    """Inject recent self-edit context so the LLM can use 'wait' / 'i mean' naturally."""
    now = time.time()
    with _EDIT_LOCK:
        entries = list(_EDIT_HISTORY.get(channel_key, []))

    recent = [
        e for e in entries
        if (now - e.get("at", 0)) <= _EDIT_HINT_MAX_AGE_SECS
    ][-3:]
    if not recent:
        return ""

    lines = []
    for e in recent:
        sent = e.get("sent", "")
        edited = e.get("edited", "")
        if len(sent) > 80:
            sent = sent[:77] + "…"
        if len(edited) > 80:
            edited = edited[:77] + "…"
        lines.append(f'- You edited "{sent}" → "{edited}"')

    return (
        "Recent self-edits in this channel:\n"
        + "\n".join(lines)
        + "\nHumans sometimes correct themselves inline (\"wait\", \"i mean\", \"edit:\") "
        "or via a quick message edit — match that vibe when it fits."
    )


def build_message_edit_hint(enabled: bool = True) -> str:
    """Tell the LLM how to request an occasional post-send message edit."""
    if not enabled:
        return ""
    return (
        "You may occasionally edit your message after sending — like fixing a typo or "
        "adding a quick thought. Write what should appear first, then append "
        "`[edit:corrected or expanded text]` (stripped before display; Discord shows the "
        "edit after a short pause). Use sparingly — roughly 1 in 15–20 replies, not every "
        "message. Examples: `your absolutly right [edit:you're absolutely right]` or "
        "`sounds good [edit:sounds good anyway]`. The initial text is what users see "
        "briefly; the edit replaces it."
    )
