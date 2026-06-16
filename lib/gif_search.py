"""GIF search — Klipy (default), Giphy, or legacy Tenor."""

import logging
import random

logger = logging.getLogger(__name__)

_KLIPY_SEARCH = "https://api.klipy.com/v2/search"
_GIPHY_SEARCH = "https://api.giphy.com/v1/gifs/search"
_TENOR_SEARCH = "https://tenor.googleapis.com/v2/search"

_VALID_PROVIDERS = ("klipy", "giphy", "tenor")


def search_gif_url(
    query: str,
    api_key: str,
    *,
    provider: str = "klipy",
    limit: int = 8,
    content_filter: str = "medium",
) -> str:
    """Return a GIF URL for the query, or empty string on failure."""
    query = (query or "").strip()
    api_key = (api_key or "").strip()
    if not query or not api_key:
        return ""

    prov = (provider or "klipy").strip().lower()
    if prov not in _VALID_PROVIDERS:
        prov = "klipy"

    if prov == "giphy":
        return _search_giphy(query, api_key, limit=limit, content_filter=content_filter)
    if prov == "tenor":
        return _search_tenor(query, api_key, limit=limit, content_filter=content_filter)
    return _search_klipy(query, api_key, limit=limit, content_filter=content_filter)


def _search_klipy(query: str, api_key: str, *, limit: int, content_filter: str) -> str:
    """Klipy v2 — Tenor-compatible drop-in (api.klipy.com)."""
    try:
        import requests

        resp = requests.get(
            _KLIPY_SEARCH,
            params={
                "q": query[:120],
                "key": api_key,
                "limit": max(1, min(20, int(limit))),
                "media_filter": "gif,tinygif,mediumgif",
                "contentfilter": _normalize_tenor_filter(content_filter),
            },
            timeout=12,
        )
        if resp.status_code != 200:
            logger.warning(f"[LEONA-DISCORD] Klipy HTTP {resp.status_code} for q={query!r}")
            return ""
        return _pick_tenor_style_url(resp.json().get("results") or [])
    except Exception as e:
        logger.warning(f"[LEONA-DISCORD] Klipy search failed: {e}")
        return ""


def _search_giphy(query: str, api_key: str, *, limit: int, content_filter: str) -> str:
    try:
        import requests

        params = {
            "api_key": api_key,
            "q": query[:50],
            "limit": max(1, min(20, int(limit))),
            "rating": _map_giphy_rating(content_filter),
        }
        resp = requests.get(_GIPHY_SEARCH, params=params, timeout=12)
        if resp.status_code != 200:
            logger.warning(f"[LEONA-DISCORD] Giphy HTTP {resp.status_code} for q={query!r}")
            return ""
        items = resp.json().get("data") or []
        if not items:
            logger.info(f"[LEONA-DISCORD] Giphy returned 0 results for q={query!r}")
        random.shuffle(items)
        for item in items:
            url = _pick_giphy_url(item)
            if url:
                return url
    except Exception as e:
        logger.warning(f"[LEONA-DISCORD] Giphy search failed: {e}")
    return ""


def _search_tenor(query: str, api_key: str, *, limit: int, content_filter: str) -> str:
    """Legacy Google Tenor API (deprecated June 2026)."""
    try:
        import requests

        resp = requests.get(
            _TENOR_SEARCH,
            params={
                "q": query[:120],
                "key": api_key,
                "limit": max(1, min(20, int(limit))),
                "media_filter": "gif,tinygif",
                "contentfilter": _normalize_tenor_filter(content_filter),
            },
            timeout=12,
        )
        if resp.status_code != 200:
            logger.warning(f"[LEONA-DISCORD] Tenor HTTP {resp.status_code} for q={query!r}")
            return ""
        return _pick_tenor_style_url(resp.json().get("results") or [])
    except Exception as e:
        logger.warning(f"[LEONA-DISCORD] Tenor search failed: {e}")
    return ""


def _normalize_tenor_filter(value: str) -> str:
    v = (value or "medium").strip().lower()
    if v in ("off", "low", "medium", "high"):
        return v
    return "medium"


def _map_giphy_rating(content_filter: str) -> str:
    v = (content_filter or "medium").strip().lower()
    return {
        "off": "g",
        "low": "g",
        "medium": "pg",
        "high": "pg-13",
    }.get(v, "pg")


def _pick_tenor_style_url(results: list) -> str:
    random.shuffle(results)
    for item in results:
        media = item.get("media_formats") or {}
        for key in ("gif", "mediumgif", "tinygif", "nanogif"):
            fmt = media.get(key) or {}
            url = (fmt.get("url") or "").strip()
            if url:
                return url
    return ""


def _pick_giphy_url(item: dict) -> str:
    images = item.get("images") or {}
    for key in ("downsized", "fixed_height", "original"):
        fmt = images.get(key) or {}
        url = (fmt.get("url") or "").strip()
        if url:
            return url
    return ""
