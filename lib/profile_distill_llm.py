"""LLM profile distiller — extract facts and summaries from user interactions."""

import json
import logging
import re

from plugins.leona_discord.lib.greeting_llm import _providers_config
from plugins.leona_discord.lib.think_tags import strip_think_tags

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def _build_prompt(
    *,
    display_name: str,
    disp_line: str,
    current_summary_l1: str,
    facts_blob: str,
    transcript_lines: list,
    strict_minified: bool = False,
) -> str:
    transcript = "\n".join(transcript_lines)
    base = f"""You are building a private user profile for a Discord bot persona.
Analyze the recent messages from user "{display_name}" and return STRICT JSON only.

Current disposition: {disp_line}
Current summary: {(current_summary_l1 or '(none)')[:400]}
Known facts:
{facts_blob or '(none)'}

Recent messages (newest last):
{transcript}

Return JSON with this shape (no markdown fences):
{{
  "facts_add": [{{"category": "preference|interest|identity|boundary|life_event|pet_peeve", "key": "short_key", "value": "concise fact", "confidence": 0.0-1.0}}],
  "facts_supersede": [{{"id": 0, "reason": "why outdated"}}],
  "disposition_delta": {{"warmth": 0.0, "trust": 0.0, "playfulness": 0.0, "patience": 0.0, "interest": 0.0}},
  "relationship_note": "one short sentence about rapport",
  "l1_summary": "one line profile for prompt injection (~30 words)",
  "l2_summary": "optional extra detail (~60 words max)"
}}

Rules:
- Only add facts clearly supported by the messages.
- disposition_delta values must be between -0.05 and 0.05.
- Skip empty arrays. If nothing new, return {{"facts_add": [], "disposition_delta": {{}}}}.
"""
    if strict_minified:
        base += (
            "\nIMPORTANT: Return exactly one minified JSON object on one line. "
            "No prose, no comments, no markdown fences, no trailing commas."
        )
    return base


def _extract_json_text(raw: str) -> str:
    text = strip_think_tags(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = _JSON_BLOCK_RE.search(text)
    if not match:
        return ""
    return match.group(0).strip()


def _parse_json_with_repair(raw: str) -> dict:
    block = _extract_json_text(raw)
    if not block:
        return {}
    try:
        data = json.loads(block)
        return data if isinstance(data, dict) else {}
    except Exception:
        # Cheap repair attempts for common model glitches.
        repaired = re.sub(r",\s*([}\]])", r"\1", block)  # trailing comma
        repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
        repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
        # If clearly truncated, close braces/brackets heuristically.
        if repaired.count("{") > repaired.count("}"):
            repaired += "}" * (repaired.count("{") - repaired.count("}"))
        if repaired.count("[") > repaired.count("]"):
            repaired += "]" * (repaired.count("[") - repaired.count("]"))
        try:
            data = json.loads(repaired)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _call_distill_llm(llm, provider, gen_params: dict, prompt: str):
    messages = [{"role": "user", "content": prompt}]
    return llm.tool_engine.call_llm_with_metrics(
        provider, messages, gen_params, tools=None,
    )


def distill_profile(
    system,
    *,
    account: str,
    guild_id: str,
    author_id: str,
    display_name: str,
    transcript_lines: list,
    current_summary_l1: str = "",
    current_facts: list = None,
    disposition: dict = None,
    provider_key: str = "",
    model_name: str = "",
    max_tokens: int = 400,
) -> dict:
    """Return parsed distiller JSON or empty dict on failure."""
    if not system or not getattr(system, "llm_chat", None):
        logger.warning("[LEONA-DISCORD-PROFILE] Distill LLM: no system.llm_chat")
        return {}
    if not transcript_lines:
        return {}

    facts_blob = ""
    if current_facts:
        facts_blob = "\n".join(
            f"- [{f.get('category')}] {f.get('fact_value')} (conf {f.get('confidence', 0):.2f})"
            for f in current_facts[:12]
        )

    disp = disposition or {}
    disp_line = ", ".join(
        f"{k}={disp.get(k, 0):.2f}" for k in (
            "familiarity", "warmth", "trust", "playfulness", "patience", "interest",
        )
    )

    prompt = _build_prompt(
        display_name=display_name,
        disp_line=disp_line,
        current_summary_l1=current_summary_l1,
        facts_blob=facts_blob,
        transcript_lines=transcript_lines[-24:],
        strict_minified=False,
    )

    try:
        llm = system.llm_chat
        if provider_key and model_name:
            from core.chat.llm_providers import get_provider_by_key, get_generation_params
            provider = get_provider_by_key(
                provider_key, _providers_config(), 60.0, model_override=model_name,
            )
            if not provider:
                return {}
            gen_params = get_generation_params(provider_key, model_name, _providers_config())
            gen_params["model"] = model_name
        else:
            provider_key, provider, model_override = llm._select_provider()
            from core.chat.llm_providers import get_generation_params
            effective_model = model_override or provider.model
            gen_params = get_generation_params(provider_key, effective_model, _providers_config())
            if model_override:
                gen_params["model"] = model_override

        gen_params["max_tokens"] = max(120, min(800, int(max_tokens)))

        llm_response = _call_distill_llm(llm, provider, gen_params, prompt)
        raw = ""
        if llm_response and getattr(llm_response, "content", None):
            raw = llm_response.content
        data = _parse_json_with_repair(raw)
        if data:
            return data

        logger.warning(
            "[LEONA-DISCORD-PROFILE] Distill parse failed; retrying strict JSON with trimmed context"
        )
        retry_prompt = _build_prompt(
            display_name=display_name,
            disp_line=disp_line,
            current_summary_l1=current_summary_l1,
            facts_blob="\n".join(
                f"- [{f.get('category')}] {f.get('fact_value')} (conf {f.get('confidence', 0):.2f})"
                for f in (current_facts or [])[:6]
            ),
            transcript_lines=transcript_lines[-12:],
            strict_minified=True,
        )
        retry_params = dict(gen_params)
        retry_params["max_tokens"] = min(gen_params.get("max_tokens", 400), 320)
        retry_response = _call_distill_llm(llm, provider, retry_params, retry_prompt)
        retry_raw = ""
        if retry_response and getattr(retry_response, "content", None):
            retry_raw = retry_response.content
        retry_data = _parse_json_with_repair(retry_raw)
        if retry_data:
            return retry_data
        logger.warning(
            "[LEONA-DISCORD-PROFILE] Distill retry failed (likely truncated/invalid JSON)"
        )
        return {}
    except Exception as e:
        logger.warning(f"[LEONA-DISCORD-PROFILE] Distill LLM failed: {e}")
        return {}
