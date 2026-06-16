"""Think-tag stripping — shared regex used by reply_handler, greeting_llm, outreach_llm, gif_query_llm."""

import re

# Matches <think>...</think>, <seed:think>...</seed:think>, <seed:cot_budget_reflect>...</seed:cot_budget_reflect>
_THINK_CLOSE_RE = re.compile(
    r"<(?:seed:)?think[^>]*>[\s\S]*?</(?:seed:think|seed:cot_budget_reflect|think)>",
    re.IGNORECASE,
)
# Matches unclosed think tags (everything from <think...> to end of string)
_THINK_OPEN_RE = re.compile(
    r"<(?:seed:)?think[^>]*>.*$",
    re.DOTALL | re.IGNORECASE,
)
# Matches leading text before a closing think tag (e.g. junk before </think>)
_THINK_LEAD_RE = re.compile(
    r"^[\s\S]*</(?:seed:think|seed:cot_budget_reflect|think)>",
    re.IGNORECASE,
)


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> blocks from LLM output."""
    text = _THINK_CLOSE_RE.sub("", text)
    text = _THINK_OPEN_RE.sub("", text)
    text = _THINK_LEAD_RE.sub("", text)
    return text.strip()
