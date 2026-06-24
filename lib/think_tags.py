"""Think-tag stripping — shared regex used by reply_handler, greeting_llm, outreach_llm, gif_query_llm."""

import re

# Matches common thinking blocks (closed).
_THINK_CLOSE_RE = re.compile(
    r"<(?:redacted_thinking|thinking|(?:seed:)?think|seed:cot_budget_reflect)[^>]*>"
    r"[\s\S]*?</(?:redacted_thinking|thinking|(?:seed:)?think|seed:cot_budget_reflect)>",
    re.IGNORECASE,
)
# Matches unclosed thinking blocks (everything from the opening tag to end of string).
_THINK_OPEN_RE = re.compile(
    r"<(?:redacted_thinking|thinking|(?:seed:)?think|seed:cot_budget_reflect)[^>]*>.*$",
    re.DOTALL | re.IGNORECASE,
)
# Matches leading text before a closing think tag.
_THINK_LEAD_RE = re.compile(
    r"^[\s\S]*</(?:redacted_thinking|thinking|(?:seed:)?think|seed:cot_budget_reflect)>",
    re.IGNORECASE,
)


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output."""
    text = _THINK_CLOSE_RE.sub("", text)
    text = _THINK_OPEN_RE.sub("", text)
    text = _THINK_LEAD_RE.sub("", text)
    return text.strip()
