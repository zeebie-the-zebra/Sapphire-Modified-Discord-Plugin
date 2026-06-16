"""Image URL collection, media sniffing, and vision-model description."""

import asyncio
import base64
import logging
import re
import time

logger = logging.getLogger(__name__)

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif")
_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v")


def is_image_or_video_url(url: str, content_type: str = "") -> bool:
    ct = (content_type or "").lower()
    if ct.startswith("image/") or ct.startswith("video/"):
        return True
    url_lower = (url or "").lower().split("?", 1)[0]
    return any(url_lower.endswith(ext) for ext in _IMAGE_EXTS + _VIDEO_EXTS)


def collect_image_urls(message) -> list:
    for att in (message.attachments or []):
        if is_image_or_video_url(att.url, att.content_type):
            return [att.url]
    for embed in (message.embeds or []):
        etype = (getattr(embed, "type", "") or "").lower()
        if etype and etype not in ("image", "gifv", "video", "rich", "article"):
            continue
        img = getattr(embed, "image", None)
        if img and getattr(img, "url", None):
            chosen = _pick_best_image_url(getattr(img, "url", ""), getattr(img, "proxy_url", None))
            if is_image_or_video_url(chosen):
                return [chosen]
        thumb = getattr(embed, "thumbnail", None)
        if thumb and getattr(thumb, "url", None):
            chosen = _pick_best_image_url(getattr(thumb, "url", ""), getattr(thumb, "proxy_url", None))
            if is_image_or_video_url(chosen):
                return [chosen]
        vid = getattr(embed, "video", None)
        if vid and getattr(vid, "url", None):
            if is_image_or_video_url(vid.url):
                return [vid.url]
    return []


def _pick_best_image_url(original_url: str, proxy_url) -> str:
    """Choose between original and proxy URL, preferring the animated version.

    Discord's image proxy (images-ext-1.discordapp.net) converts animated GIFs
    to static PNGs, losing the animation.  When the original URL is a GIF,
    use it directly so the vision model sees the full animation.
    """
    proxy = proxy_url or ""
    orig = original_url or ""
    # If the original is a GIF, prefer it over the (likely de-animated) proxy
    if orig.lower().split("?", 1)[0].endswith(".gif"):
        return orig
    # Otherwise prefer proxy (faster, cached) — fall back to original
    return proxy or orig


def sniff_media_type(data: bytes, url: str = ""):
    if not data or len(data) < 12:
        return ("image/jpeg", False)
    head = data[:16]
    if head.startswith(b"\xff\xd8\xff"):
        return ("image/jpeg", False)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("image/png", False)
    if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
        return ("image/gif", False)
    if head.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ("image/webp", False)
    if head[4:8] == b"ftyp":
        return ("video/mp4", True)
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return ("video/webm", True)
    url_lower = (url or "").lower()
    if any(url_lower.endswith(ext) for ext in (".mp4", ".mov", ".webm", ".mkv", ".avi")):
        return (None, True)
    if any(url_lower.endswith(ext) for ext in (".gif", ".png", ".jpg", ".jpeg", ".webp")):
        return ("image/jpeg", False)
    logger.debug(f"[DISCORD] _sniff_media_type: unknown magic bytes {head.hex()} for {url}")
    return ("image/jpeg", False)


_GIF_MAX_FRAMES = 4  # max frames to sample from animated GIFs
_GIF_EVENT_MAX_FRAMES = 2  # fewer frames for native-vision event payloads
# ExecutionContext pre-check counts base64 in multimodal content as text tokens
# (~1:1 on the b64 string). Keep event images small enough for typical task limits.
_VISION_TARGET_B64_CHARS = 80_000
_VISION_MAX_LONG_EDGE = 1024
# Vision describe calls: keep images smaller — VLMs spend context on pixels.
_VISION_DESCRIBE_B64_CHARS = 50_000
_VISION_DESCRIBE_MAX_EDGE = 768
_VISION_DESCRIBE_MIN_TOKENS = 1024


def _shrink_image_bytes(image_bytes: bytes, media_type: str,
                        target_b64_chars: int = _VISION_TARGET_B64_CHARS,
                        max_long_edge: int = _VISION_MAX_LONG_EDGE) -> tuple:
    """Downscale/compress an image so its base64 fits the context pre-check."""
    if not image_bytes:
        return image_bytes, media_type

    try:
        from PIL import Image
        import io
    except ImportError:
        return image_bytes, media_type

    try:
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        long_edge = max(w, h)
    except Exception:
        return image_bytes, media_type

    orig_b64_len = len(base64.b64encode(image_bytes))
    if orig_b64_len <= target_b64_chars and long_edge <= max_long_edge:
        return image_bytes, media_type

    if img.mode in ("RGBA", "P", "LA"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        rgba = img.convert("RGBA") if img.mode == "P" else img
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    long_edge = max(w, h)
    best = None

    edge_steps = [max_long_edge]
    for edge in (768, 512, 384):
        if edge < edge_steps[-1]:
            edge_steps.append(edge)

    for max_edge in edge_steps:
        if long_edge > max_edge:
            scale = max_edge / long_edge
            scaled = img.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.Resampling.LANCZOS,
            )
        else:
            scaled = img

        for quality in (85, 75, 65, 50, 40):
            buf = io.BytesIO()
            scaled.save(buf, format="JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            b64_len = len(base64.b64encode(data))
            best = (data, "image/jpeg", b64_len, scaled.size)
            if b64_len <= target_b64_chars:
                logger.info(
                    f"[DISCORD] Shrunk image for context budget: "
                    f"{len(image_bytes)} raw bytes → {len(data)} JPEG "
                    f"({b64_len} b64 chars, {scaled.size[0]}×{scaled.size[1]})"
                )
                return data, "image/jpeg"

    if best:
        data, _, b64_len, size = best
        logger.info(
            f"[DISCORD] Shrunk image for context budget (best effort): "
            f"{len(image_bytes)} raw bytes → {len(data)} JPEG "
            f"({b64_len} b64 chars, {size[0]}×{size[1]})"
        )
        return data, "image/jpeg"

    return image_bytes, media_type


def _pick_gif_describe_frame(gif_frames: list) -> tuple:
    """Pick a GIF frame for vision description.

    Frame 0 of animated GIFs is often blank or a loading slide — prefer a
    later sampled frame.
    """
    if not gif_frames:
        return b"", "image/png"
    if len(gif_frames) == 1:
        frame_bytes, frame_type = gif_frames[0]
    else:
        frame_bytes, frame_type = gif_frames[len(gif_frames) // 2]
    return _shrink_image_bytes(frame_bytes, frame_type)


def _extract_llm_description(response) -> str:
    """Pull visible description text from an LLMResponse (incl. thinking models)."""
    description = ""
    if hasattr(response, "content") and response.content:
        description = str(response.content).strip()
    elif isinstance(response, dict):
        description = str(response.get("content") or "").strip()

    if not description and hasattr(response, "thinking") and response.thinking:
        description = str(response.thinking).strip()

    if description:
        from plugins.leona_discord.lib.think_tags import strip_think_tags
        description = strip_think_tags(description).strip()
    return description


def _vision_describe_prompt(from_gif: bool) -> str:
    prompt_text = (
        "You are describing an image to someone who cannot see it. "
        "Give a brief description of what you see in this image in 1-2 sentences. "
        "Be concrete and specific — describe actual objects, people, text, or scenes you see. "
        "Do not describe the act of viewing or mention the image itself."
    )
    if from_gif:
        prompt_text += (
            " This is a single frame from an animated GIF — describe what is "
            "visible in this frame, including any text, characters, or motion implied."
        )
    return prompt_text


def _log_empty_vision_response(provider_key: str, model_name: str, response, frame_idx=None):
    raw = getattr(response, "content", None)
    thinking = getattr(response, "thinking", None)
    finish = getattr(response, "finish_reason", None)
    usage = getattr(response, "usage", None) or {}
    frame_note = f" frame={frame_idx}" if frame_idx is not None else ""
    logger.warning(
        f"[DISCORD] Image description empty from {provider_key}/{model_name}{frame_note} "
        f"(finish={finish!r}, completion_tok={usage.get('completion_tokens')}, "
        f"content={repr(raw)[:120]}, thinking_len={len(thinking or '')})"
    )


def _describe_token_budgets(max_tokens: int) -> list:
    """Token limits to try — Gemma-class VLMs can hit finish=length on small caps."""
    base = max(int(max_tokens or 0), _VISION_DESCRIBE_MIN_TOKENS)
    seen = set()
    out = []
    for val in (base, max(base * 2, 1536), 2048):
        if val not in seen:
            seen.add(val)
            out.append(val)
    return out


def _attachment_kind(image_urls: list) -> str:
    is_gif = any(".gif" in (u or "").lower().split("?", 1)[0] for u in image_urls)
    return "GIF" if is_gif else "image"


def format_vision_description(description: str, image_urls: list) -> str:
    """Wrap a vision-model description so the reply LLM treats it as the attachment."""
    kind = _attachment_kind(image_urls)
    desc = (description or "").strip()
    return (
        f"[Attached {kind} — automated vision description of what the user sent: "
        f"{desc}]\n"
        f"[Vision pipeline note: you did not receive the raw {kind} file. The "
        f"description above is what it shows — including for GIFs. Respond to "
        f"that content directly; do not say you cannot see {kind.lower()}s.]\n"
    )


def is_vision_description_block(text: str) -> bool:
    return bool(text and "automated vision description of what the user sent" in text)


def _ollama_list_model_names(base_url: str = "") -> list:
    """Return model names from a local Ollama instance (empty list on failure)."""
    try:
        import requests as req
        root = (base_url or "http://127.0.0.1:11434/v1").rstrip("/")
        if root.endswith("/v1"):
            root = root[:-3]
        resp = req.get(f"{root}/api/tags", timeout=3)
        if resp.status_code != 200:
            return []
        data = resp.json()
        return [
            str(m.get("name") or "").strip()
            for m in (data.get("models") or [])
            if m.get("name")
        ]
    except Exception:
        return []


def _suggest_vision_model_name(requested: str, available: list) -> str:
    """Best-effort match when the configured model name is wrong."""
    if not requested or not available:
        return ""
    req = requested.lower()
    for name in available:
        if name.lower() == req:
            return name
    for name in available:
        low = name.lower()
        if req in low or low in req:
            return name
    # LM Studio / GGUF filenames often differ — match on family token
    tokens = [t for t in re.split(r"[^a-z0-9]+", req) if len(t) >= 4]
    best = ""
    best_score = 0
    for name in available:
        low = name.lower()
        score = sum(1 for t in tokens if t in low)
        if score > best_score:
            best_score = score
            best = name
    return best if best_score >= 2 else ""


def _log_vision_describe_error(exc, provider_key: str, model_name: str, provider=None):
    """Log vision describe failures with actionable hints for common misconfig."""
    err_str = str(exc)
    low = err_str.lower()
    base_url = getattr(provider, "base_url", None) or ""

    if "not found" in low or "not_found" in low or "404" in err_str:
        msg = (
            f"[DISCORD] Vision model {provider_key}/{model_name!r} not found on the server. "
            f"Use the exact model id from your provider's model list "
            f"(for Ollama: `ollama list` — not GGUF/LM Studio filenames)."
        )
        is_ollama = (
            provider_key == "ollama"
            or "11434" in base_url
            or "ollama" in base_url.lower()
        )
        if is_ollama:
            available = _ollama_list_model_names(base_url)
            if available:
                msg += f" Available on Ollama: {', '.join(available[:10])}"
                if len(available) > 10:
                    msg += f" (+{len(available) - 10} more)"
                suggestion = _suggest_vision_model_name(model_name, available)
                if suggestion and suggestion != model_name:
                    msg += f" Did you mean {suggestion!r}?"
        logger.warning(msg)
        return

    logger.warning(f"[DISCORD] Image description failed ({provider_key}/{model_name}): {exc}")


def image_unavailable_hint(image_urls: list) -> str:
    """Honest fallback when vision description failed — discourages LLM hallucination."""
    kind = _attachment_kind(image_urls)
    return (
        f"[User sent an attached {kind}. Automated vision description failed — "
        f"you CANNOT see this attachment. Do NOT guess or invent what it shows. "
        f"If asked about it, say you couldn't see it and ask the user to describe it.]\n"
    )


def _gif_to_sampled_frames(data: bytes) -> list:
    """Sample up to _GIF_MAX_FRAMES evenly-spaced frames from a GIF, each as PNG.

    Returns a list of (png_bytes, 'image/png') tuples.
    Falls back to a single entry with original bytes if conversion fails.
    """
    if not (data[:6] in (b"GIF87a", b"GIF89a")):
        return []
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(data))
        n_frames = getattr(img, "n_frames", 1)
        if n_frames <= 1:
            # Single-frame GIF — just convert it
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            logger.info(f"[DISCORD] Converted single-frame GIF to PNG ({len(data)} -> {buf.tell()} bytes)")
            return [(buf.getvalue(), "image/png")]

        # Pick evenly-spaced frame indices
        count = min(n_frames, _GIF_MAX_FRAMES)
        indices = [round(i * (n_frames - 1) / max(count - 1, 1)) for i in range(count)]

        frames = []
        for idx in indices:
            img.seek(idx)
            frame = img.convert("RGB")
            buf = io.BytesIO()
            frame.save(buf, format="PNG")
            frames.append((buf.getvalue(), "image/png"))

        logger.info(
            f"[DISCORD] Sampled {len(frames)}/{n_frames} frames from GIF "
            f"({len(data)} bytes raw, {sum(len(f) for f, _ in frames)} bytes as PNG)"
        )
        return frames
    except Exception as e:
        logger.warning(f"[DISCORD] GIF frame sampling failed: {e}; falling back to first-frame extraction")
        # Last resort: try to just grab the first frame
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(data))
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return [(buf.getvalue(), "image/png")]
        except Exception:
            return [(data, "image/gif")]


# ---------------------------------------------------------------------------
# Sync helper — runs in a thread executor so it never blocks the event loop.
# ---------------------------------------------------------------------------

def _describe_image_sync(image_url: str, guild_id: str = "") -> str:
    """Synchronous image-fetch + vision-LLM description.  Called via run_in_executor."""
    from plugins.leona_discord.lib.settings import get_image_settings

    img_settings = get_image_settings(guild_id)
    if not img_settings.get("image_enabled"):
        return ""
    provider_key = img_settings.get("image_model_provider", "")
    model_name = img_settings.get("image_model_name", "")
    max_tokens = int(img_settings.get("image_model_max_tokens", 1024))
    if not provider_key or not model_name:
        return ""

    # --- Fetch image bytes (I/O-bound) ---
    try:
        import requests as req
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,video/*;q=0.9,*/*;q=0.8",
        }
        image_bytes = None
        last_err = None
        for attempt in range(3):
            try:
                resp = req.get(image_url, headers=headers, timeout=15, allow_redirects=True)
                if resp.status_code == 200 and resp.content:
                    image_bytes = resp.content
                    break
                last_err = f"HTTP {resp.status_code}"
                logger.warning(
                    f"[DISCORD] Image fetch attempt {attempt+1}/3 got {last_err} "
                    f"for {image_url}"
                )
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                logger.warning(f"[DISCORD] Image fetch attempt {attempt+1}/3 error: {last_err} for {image_url}")
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
        if not image_bytes:
            logger.warning(f"[DISCORD] Image fetch failed after 3 attempts: {last_err} for {image_url}")
            return ""
    except Exception as e:
        logger.warning(f"[DISCORD] Image fetch fatal error: {e}")
        return ""

    media_type, is_video = sniff_media_type(image_bytes, image_url)
    if is_video or not media_type:
        logger.info(f"[DISCORD] Skipping vision description for {image_url} (video or unknown type)")
        return ""

    # GIFs: sample multiple frames. Static images: always normalize dimensions.
    from_gif = media_type == "image/gif"
    if not from_gif:
        image_bytes, media_type = _shrink_image_bytes(
            image_bytes, media_type,
            target_b64_chars=_VISION_DESCRIBE_B64_CHARS,
            max_long_edge=_VISION_DESCRIBE_MAX_EDGE,
        )

    # --- Call vision LLM (I/O-bound) ---
    provider = None
    try:
        import json as _json
        import os as _os
        from core.chat.llm_providers import get_provider_by_key
        from core.settings_manager import settings

        providers_config = {}
        # The settings manager flattens nested dicts — LLM_PROVIDERS and
        # LLM_CUSTOM_PROVIDERS both land at the top level after _flatten_dict.
        top = settings.get('LLM_PROVIDERS', {})
        if isinstance(top, dict) and top:
            providers_config = dict(top)
        custom = settings.get('LLM_CUSTOM_PROVIDERS', {})
        if isinstance(custom, dict) and custom:
            for k, v in custom.items():
                providers_config[k] = v
        # Fallback: read directly from settings.json on disk.
        # __file__ = .../sapphire/plugins/leona_discord/lib/images.py
        # We need sapphire/ as the base.
        base = _os.path.dirname(_os.path.dirname(_os.path.dirname(
            _os.path.dirname(__file__))))
        settings_path = _os.path.join(base, 'user', 'settings.json')
        if _os.path.exists(settings_path):
            with open(settings_path, encoding='utf-8') as f:
                file_settings = _json.load(f)
            # Same structure: LLM_CUSTOM_PROVIDERS under "llm" namespace
            file_llm = file_settings.get('llm', {}) or {}
            file_custom = dict(file_llm.get('LLM_CUSTOM_PROVIDERS', {}))
            for k, v in file_custom.items():
                providers_config[k] = v

        provider = get_provider_by_key(provider_key, providers_config, 30.0, model_override=model_name)
        if not provider:
            logger.warning(f"[DISCORD] Image model provider '{provider_key}' not available")
            return ""

        if not getattr(provider, "supports_images", False):
            logger.warning(
                f"[DISCORD] Image model {provider_key}/{model_name} does not support vision — "
                f"description skipped. Pick a VLM (llava, qwen-vl, gemma-3 vision, etc.) or "
                f"enable the vision checkbox on the provider in Settings → LLM."
            )
            return ""

        frames_to_try = []
        if from_gif:
            gif_frames = _gif_to_sampled_frames(image_bytes)
            if not gif_frames:
                logger.warning(f"[DISCORD] GIF frame sampling returned nothing for {image_url}")
                return ""
            for frame_bytes, frame_type in gif_frames:
                shrunk, out_type = _shrink_image_bytes(
                    frame_bytes, frame_type,
                    target_b64_chars=_VISION_DESCRIBE_B64_CHARS,
                    max_long_edge=_VISION_DESCRIBE_MAX_EDGE,
                )
                if shrunk:
                    frames_to_try.append((shrunk, out_type))
        else:
            frames_to_try.append((image_bytes, media_type))

        if not frames_to_try:
            return ""

        token_budgets = _describe_token_budgets(max_tokens)
        for idx, (frame_bytes, frame_media) in enumerate(frames_to_try):
            messages = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": _vision_describe_prompt(from_gif)},
                    {
                        "type": "image",
                        "media_type": frame_media,
                        "data": base64.b64encode(frame_bytes).decode("ascii"),
                    },
                ],
            }]
            for tok_idx, tok_limit in enumerate(token_budgets):
                last_response = provider.chat_completion(
                    messages, tools=None,
                    generation_params={"max_tokens": tok_limit},
                )
                description = _extract_llm_description(last_response)
                if description:
                    if from_gif and idx > 0:
                        logger.info(
                            f"[DISCORD] Image described from GIF frame {idx}: "
                            f"{description[:80]}"
                        )
                    elif tok_idx > 0:
                        logger.info(
                            f"[DISCORD] Image described at max_tokens={tok_limit}: "
                            f"{description[:80]}"
                        )
                    else:
                        logger.info(f"[DISCORD] Image described: {description[:80]}")
                    return description
                finish = getattr(last_response, "finish_reason", None)
                if finish != "length" or tok_idx == len(token_budgets) - 1:
                    break
                logger.info(
                    f"[DISCORD] Vision describe hit finish=length at max_tokens={tok_limit}"
                    f"{f' frame={idx}' if from_gif else ''} — retrying with more tokens"
                )
            _log_empty_vision_response(
                provider_key, model_name, last_response,
                frame_idx=idx if from_gif else None,
            )

        return ""

    except Exception as e:
        _log_vision_describe_error(e, provider_key, model_name, provider)
        return ""


# ---------------------------------------------------------------------------
# Fetch image bytes and return multimodal content blocks for native-vision
# models.  Returns a list suitable for extending a user-message content list,
# e.g.  [{"type": "text", "text": "..."}, {"type": "image", ...}]
# ---------------------------------------------------------------------------

def _fetch_image_blocks_sync(image_url: str) -> list:
    """Download an image and return a multimodal content block (or empty list).

    Unlike ``_describe_image_sync`` this does NOT call any LLM — it just
    fetches the bytes, sniffs the media type, base64-encodes them and wraps
    them in the OpenAI / Anthropic ``image`` content-block format so the
    *main* model can see the pixels directly.
    """
    try:
        import requests as req
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,video/*;q=0.9,*/*;q=0.8",
        }
        image_bytes = None
        last_err = None
        for attempt in range(3):
            try:
                resp = req.get(image_url, headers=headers, timeout=15, allow_redirects=True)
                if resp.status_code == 200 and resp.content:
                    image_bytes = resp.content
                    break
                last_err = f"HTTP {resp.status_code}"
                logger.warning(
                    f"[DISCORD] Image fetch attempt {attempt+1}/3 got {last_err} "
                    f"for {image_url}"
                )
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                logger.warning(f"[DISCORD] Image fetch attempt {attempt+1}/3 error: {last_err} for {image_url}")
            if attempt < 2:
                time.sleep(0.5 * (attempt + 1))
        if not image_bytes:
            logger.warning(f"[DISCORD] Image fetch failed after 3 attempts: {last_err} for {image_url}")
            return []
    except Exception as e:
        logger.warning(f"[DISCORD] Image fetch fatal error: {e}")
        return []

    media_type, is_video = sniff_media_type(image_bytes, image_url)
    if is_video or not media_type:
        logger.info(f"[DISCORD] Skipping multimodal block for {image_url} (video or unknown type)")
        return []

    # GIFs are rejected by Ollama vision models (400 "invalid image input").
    # Sample multiple frames so the vision model sees the full animation.
    if media_type == "image/gif":
        frames = _gif_to_sampled_frames(image_bytes)[:_GIF_EVENT_MAX_FRAMES]
        if frames:
            blocks = []
            per_frame_target = max(
                20_000,
                _VISION_TARGET_B64_CHARS // max(len(frames), 1),
            )
            for frame_bytes, frame_type in frames:
                shrunk, out_type = _shrink_image_bytes(
                    frame_bytes, frame_type, target_b64_chars=per_frame_target,
                )
                try:
                    b64 = base64.b64encode(shrunk).decode("ascii")
                except Exception:
                    continue
                blocks.append({"type": "image", "media_type": out_type, "data": b64})
            if blocks:
                logger.info(
                    f"[DISCORD] Prepared {len(blocks)} multimodal frame blocks from GIF for {image_url}"
                )
                return blocks
            return []
        # Fallback: send original GIF bytes as-is
        logger.warning(f"[DISCORD] GIF frame sampling failed for {image_url}; sending raw GIF")

    image_bytes, media_type = _shrink_image_bytes(image_bytes, media_type)

    try:
        b64_data = base64.b64encode(image_bytes).decode("ascii")
    except Exception as e:
        logger.warning(f"[DISCORD] Image base64 encode error: {e}")
        return []

    logger.info(f"[DISCORD] Prepared multimodal image block: {media_type} ({len(b64_data)} b64 chars) for {image_url}")
    return [
        {
            "type": "image",
            "media_type": media_type,
            "data": b64_data,
        }
    ]


async def fetch_image_blocks(image_url: str) -> list:
    """Async wrapper — offloads the sync fetch to a thread executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_image_blocks_sync, image_url)


def blocks_to_event_images(blocks: list) -> list:
    """Convert internal multimodal blocks to core's daemon event ``images`` format.

    Core expects: [{"data": "<base64>", "media_type": "image/png"}, ...]
    with raw base64 (no data: URI prefix) and no extra keys.
    """
    out = []
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        data = block.get("data")
        media_type = block.get("media_type")
        if not isinstance(data, str) or not data:
            continue
        if data.startswith("data:") and ";base64," in data:
            header, data = data.split(";base64,", 1)
            if not media_type and ":" in header:
                media_type = header.split(":", 1)[1]
        if not isinstance(media_type, str) or not media_type:
            continue
        out.append({"data": data, "media_type": media_type})
    return out


# ---------------------------------------------------------------------------
# Async entry-point — offloads the sync body to a thread executor so the
# Discord event loop (gateway heartbeat) is never blocked.
# ---------------------------------------------------------------------------

async def describe_image(image_url: str, guild_id: str = "") -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _describe_image_sync, image_url, guild_id)
