"""LLM profile distiller — extract facts and summaries from user interactions."""

import json
import logging
import re

from plugins.leona_discord.lib.greeting_llm import _providers_config
from plugins.leona_discord.lib.think_tags import strip_think_tags

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)

EMPTY_DISTILL_RESULT = {
    "facts_add": [],
    "facts_supersede": [],
    "disposition_delta": {},
    "relationship_note": "",
    "l1_summary": "",
    "l2_summary": "",
}

_VALID_CATEGORIES = frozenset({
    "preference", "interest", "identity", "boundary", "life_event", "pet_peeve", "in_joke",
})

_DISPOSITION_DIMS = ("warmth", "trust", "playfulness", "patience", "interest")

_MINIMAL_MAX_TOKENS = 160
_FULL_MIN_TOKENS = 480


def _build_minimal_prompt(
    *,
    display_name: str,
    facts_blob: str,
    transcript_lines: list,
) -> str:
    transcript = "\n".join(transcript_lines)
    empty = '{"has_updates":false,"facts_add":[],"disposition_delta":{}}'
    return f"""You are updating a private Discord user profile for "{display_name}".
Read the recent messages and return STRICT JSON only — one minified object, no markdown fences.

Known facts (do not repeat):
{facts_blob or '(none)'}

Recent messages (newest last):
{transcript}

Return JSON with exactly this shape:
{{"has_updates":true|false,"facts_add":[{{"category":"preference|interest|identity|boundary|life_event|pet_peeve","key":"short_key","value":"concise fact","confidence":0.0-1.0}}],"disposition_delta":{{"warmth":0.0,"trust":0.0,"playfulness":0.0,"patience":0.0,"interest":0.0}}}}

Rules:
- Set has_updates to false when nothing new is worth storing.
- If has_updates is false, facts_add must be [] and disposition_delta must be {{}}.
- If has_updates is true, include at most 3 new facts_add items clearly supported by the messages.
- disposition_delta values must be between -0.05 and 0.05; omit keys that are 0.
- If nothing new, return exactly: {empty}
"""


def _build_full_prompt(
    *,
    display_name: str,
    disp_line: str,
    current_summary_l1: str,
    facts_blob: str,
    transcript_lines: list,
    minimal_facts: list,
) -> str:
    transcript = "\n".join(transcript_lines)
    draft_facts = json.dumps(minimal_facts, ensure_ascii=False)
    return f"""You are refining a Discord user profile for "{display_name}".
Facts were already extracted; now add summaries and any superseded fact ids. Return STRICT JSON only.

Current disposition: {disp_line}
Current summary: {(current_summary_l1 or '(none)')[:400]}
Known facts:
{facts_blob or '(none)'}

Draft facts_add (already captured — do not repeat):
{draft_facts}

Recent messages (newest last):
{transcript}

Return JSON with this shape (no markdown fences):
{{
  "facts_supersede": [{{"id": 0, "reason": "why outdated"}}],
  "relationship_note": "one short sentence about rapport",
  "l1_summary": "one line profile (~30 words)",
  "l2_summary": "optional extra detail (~60 words max)"
}}

Rules:
- Only include facts_supersede when an existing fact id is clearly outdated.
- Keep l1_summary and relationship_note concise.
- If nothing to add beyond the draft facts, return {{"facts_supersede":[],"relationship_note":"","l1_summary":"","l2_summary":""}}
"""


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
        repaired = re.sub(r",\s*([}\]])", r"\1", block)
        repaired = repaired.replace("\u201c", '"').replace("\u201d", '"')
        repaired = repaired.replace("\u2018", "'").replace("\u2019", "'")
        if repaired.count("{") > repaired.count("}"):
            repaired += "}" * (repaired.count("{") - repaired.count("}"))
        if repaired.count("[") > repaired.count("]"):
            repaired += "]" * (repaired.count("[") - repaired.count("]"))
        try:
            data = json.loads(repaired)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


def _response_content(response) -> str:
    if response and getattr(response, "content", None):
        return response.content or ""
    return ""


def _response_truncated(response) -> bool:
    reason = str(getattr(response, "finish_reason", "") or "").lower()
    return reason in ("length", "max_tokens", "model_length")


def _normalize_disposition_delta(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out = {}
    for dim in _DISPOSITION_DIMS:
        if dim not in raw:
            continue
        try:
            val = max(-0.05, min(0.05, float(raw[dim])))
        except (TypeError, ValueError):
            continue
        if abs(val) > 0.0001:
            out[dim] = val
    return out


def _normalize_fact_item(item) -> dict | None:
    if not isinstance(item, dict):
        return None
    value = str(item.get("value") or "").strip()
    if not value:
        return None
    category = str(item.get("category") or "preference").strip().lower()
    if category not in _VALID_CATEGORIES:
        category = "preference"
    key = str(item.get("key") or "note").strip()[:80] or "note"
    try:
        confidence = max(0.0, min(1.0, float(item.get("confidence", 0.7))))
    except (TypeError, ValueError):
        confidence = 0.7
    return {
        "category": category,
        "key": key,
        "value": value[:500],
        "confidence": confidence,
    }


def _normalize_minimal_result(data: dict) -> dict:
    facts = []
    for item in (data.get("facts_add") or [])[:3]:
        normalized = _normalize_fact_item(item)
        if normalized:
            facts.append(normalized)
    delta = _normalize_disposition_delta(data.get("disposition_delta"))
    has_updates = bool(data.get("has_updates"))
    if facts or delta:
        has_updates = True
    return {
        "has_updates": has_updates,
        "facts_add": facts,
        "disposition_delta": delta,
    }


def _merge_distill_results(minimal: dict, full: dict | None) -> dict:
    out = dict(EMPTY_DISTILL_RESULT)
    out["facts_add"] = list(minimal.get("facts_add") or [])
    out["disposition_delta"] = dict(minimal.get("disposition_delta") or {})
    if not full:
        return out

    supersede = []
    for item in (full.get("facts_supersede") or [])[:10]:
        if not isinstance(item, dict):
            continue
        try:
            fact_id = int(item.get("id", 0))
        except (TypeError, ValueError):
            continue
        if fact_id > 0:
            supersede.append({
                "id": fact_id,
                "reason": str(item.get("reason") or "").strip()[:200],
            })
    out["facts_supersede"] = supersede
    out["relationship_note"] = str(full.get("relationship_note") or "").strip()[:500]
    out["l1_summary"] = str(full.get("l1_summary") or "").strip()[:800]
    out["l2_summary"] = str(full.get("l2_summary") or "").strip()[:1600]
    return out


def _has_distill_updates(result: dict) -> bool:
    if not result:
        return False
    if result.get("facts_add") or result.get("disposition_delta"):
        return True
    if result.get("facts_supersede"):
        return True
    if (result.get("relationship_note") or "").strip():
        return True
    if (result.get("l1_summary") or "").strip() or (result.get("l2_summary") or "").strip():
        return True
    return False


def _call_distill_llm(llm, provider, gen_params: dict, prompt: str):
    messages = [{"role": "user", "content": prompt}]
    return llm.tool_engine.call_llm_with_metrics(
        provider, messages, gen_params, tools=None,
    )


def _resolve_provider(llm, provider_key: str, model_name: str):
    if provider_key and model_name:
        from core.chat.llm_providers import get_provider_by_key, get_generation_params
        provider = get_provider_by_key(
            provider_key, _providers_config(), 60.0, model_override=model_name,
        )
        if not provider:
            return None, None
        gen_params = get_generation_params(provider_key, model_name, _providers_config())
        gen_params["model"] = model_name
        return provider, gen_params

    provider_key, provider, model_override = llm._select_provider()
    from core.chat.llm_providers import get_generation_params
    effective_model = model_override or provider.model
    gen_params = get_generation_params(provider_key, effective_model, _providers_config())
    if model_override:
        gen_params["model"] = model_override
    return provider, gen_params


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
    """Return parsed distiller JSON or empty result on failure / no-op."""
    if not system or not getattr(system, "llm_chat", None):
        logger.warning("[LEONA-DISCORD-PROFILE] Distill LLM: no system.llm_chat")
        return {}
    if not transcript_lines:
        return {}

    facts_blob = ""
    if current_facts:
        facts_blob = "\n".join(
            f"- [id={f.get('id')}] [{f.get('category')}] {f.get('fact_value')} "
            f"(conf {f.get('confidence', 0):.2f})"
            for f in current_facts[:12]
            if f.get("id") is not None
        ) or "\n".join(
            f"- [{f.get('category')}] {f.get('fact_value')} (conf {f.get('confidence', 0):.2f})"
            for f in current_facts[:12]
        )

    disp = disposition or {}
    disp_line = ", ".join(
        f"{k}={disp.get(k, 0):.2f}" for k in (
            "familiarity", "warmth", "trust", "playfulness", "patience", "interest",
        )
    )

    try:
        llm = system.llm_chat
        provider, gen_params = _resolve_provider(llm, provider_key, model_name)
        if not provider:
            return {}

        minimal_prompt = _build_minimal_prompt(
            display_name=display_name,
            facts_blob=facts_blob,
            transcript_lines=transcript_lines[-16:],
        )
        minimal_params = dict(gen_params)
        minimal_params["max_tokens"] = _MINIMAL_MAX_TOKENS

        minimal_response = _call_distill_llm(llm, provider, minimal_params, minimal_prompt)
        minimal_raw = _response_content(minimal_response)
        minimal_data = _normalize_minimal_result(_parse_json_with_repair(minimal_raw))

        if not minimal_data and _response_truncated(minimal_response):
            logger.info(
                "[LEONA-DISCORD-PROFILE] Minimal distill truncated — treating as no-op this cycle"
            )
            return {}

        if not minimal_data:
            logger.warning(
                "[LEONA-DISCORD-PROFILE] Minimal distill parse failed; treating as no-op"
            )
            return {}

        if not minimal_data.get("has_updates"):
            logger.debug("[LEONA-DISCORD-PROFILE] Minimal distill: no updates")
            return {}

        full_max = max(_FULL_MIN_TOKENS, min(800, int(max_tokens)))
        full_prompt = _build_full_prompt(
            display_name=display_name,
            disp_line=disp_line,
            current_summary_l1=current_summary_l1,
            facts_blob=facts_blob,
            transcript_lines=transcript_lines[-16:],
            minimal_facts=minimal_data.get("facts_add") or [],
        )
        full_params = dict(gen_params)
        full_params["max_tokens"] = full_max

        full_response = _call_distill_llm(llm, provider, full_params, full_prompt)
        full_raw = _response_content(full_response)
        full_data = _parse_json_with_repair(full_raw)

        if not full_data and _response_truncated(full_response):
            logger.warning(
                "[LEONA-DISCORD-PROFILE] Full distill truncated — applying facts/deltas only"
            )
            merged = _merge_distill_results(minimal_data, None)
            return merged if _has_distill_updates(merged) else {}

        if not full_data:
            logger.warning(
                "[LEONA-DISCORD-PROFILE] Full distill parse failed — applying facts/deltas only"
            )
            merged = _merge_distill_results(minimal_data, None)
            return merged if _has_distill_updates(merged) else {}

        merged = _merge_distill_results(minimal_data, full_data)
        return merged if _has_distill_updates(merged) else {}
    except Exception as e:
        logger.warning(f"[LEONA-DISCORD-PROFILE] Distill LLM failed: {e}")
        return {}
