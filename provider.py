"""Jina (Search + Reader) web backend for Hermes — fallback/alternative to You.com.

Official usage (https://jina.ai/reader; entry docs https://s.jina.ai/docs
and https://r.jina.ai/docs):
  search : GET {search_base}/?q={query}&num={n}  (Accept: application/json)
           -> {code, status, data: [{title, url, description, content, usage}], meta}
  reader : GET {reader_base}/{url}  (Authorization: Bearer key) -> markdown text

Env (JINA_ prefix; JINA_API_KEY matches the existing BWS secret name):
  JINA_API_KEY          (required — via BWS or .env, whichever the machine uses)
  JINA_SEARCH_BASE_URL  (optional override, default https://s.jina.ai)
  JINA_READER_BASE_URL  (optional override, default https://r.jina.ai)
Two vars (not one) because Jina runs two distinct services on two hosts,
unlike You.com's single host. Plugin appends paths itself.

Hardening carried over from the web-backend benchmark (22 Sep 2026):
thin-guard (<500 chars = honest error, never silent-thin) + 1x retry on 429.
Known Jina traits: search is slow (median ~4s, tail 26s) and returns full
page content per hit (~200KB/10 hits) — the envelope carries `description`
only; `content` is NOT forwarded to keep token cost down.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

import httpx

from agent.web_search_provider import WebSearchProvider, get_provider_env

logger = logging.getLogger(__name__)

_DEFAULT_SEARCH_BASE = "https://s.jina.ai"
_DEFAULT_READER_BASE = "https://r.jina.ai"
_MIN_EXTRACT_CHARS = 500
_SEARCH_CAP = 10
_KEY_DOC_URL = "https://jina.ai/reader"


def _search_base() -> str:
    return (get_provider_env("JINA_SEARCH_BASE_URL") or _DEFAULT_SEARCH_BASE).rstrip("/")


def _reader_base() -> str:
    return (get_provider_env("JINA_READER_BASE_URL") or _DEFAULT_READER_BASE).rstrip("/")


def _api_key() -> str:
    return (get_provider_env("JINA_API_KEY") or "").strip()


def _missing_key_error() -> str:
    return "JINA_API_KEY is not set (BWS secret or ~/.hermes/.env)"


class JinaProvider(WebSearchProvider):
    """Jina Search + Reader backend."""

    name = "jina"

    def is_available(self) -> bool:
        return bool(_api_key())

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    # --- search ---

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        api_key = _api_key()
        if not api_key:
            return {"success": False, "error": _missing_key_error()}
        count = max(1, min(int(limit or 5), _SEARCH_CAP))
        url = f"{_search_base()}/"
        try:
            resp = httpx.get(
                url,
                params={"q": query, "num": count},
                headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                timeout=60,
            )
            if resp.status_code == 429:
                time.sleep(3)
                resp = httpx.get(
                    url,
                    params={"q": query, "num": count},
                    headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
                    timeout=60,
                )
            if resp.status_code >= 400:
                return {"success": False, "error": (resp.text or "").strip()[:300] or f"HTTP {resp.status_code}"}
            return _normalize_search(resp.json(), count)
        except Exception as exc:  # noqa: BLE001 — httpx errors surface verbatim
            logger.warning("Jina search error: %s", exc)
            return {"success": False, "error": f"Jina search failed: {exc}"}

    # --- extract (Reader) ---

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        api_key = _api_key()
        if not api_key:
            return [{"url": u, "title": "", "content": "", "error": _missing_key_error()} for u in urls]
        docs: List[Dict[str, Any]] = []
        for u in urls:
            try:
                resp = httpx.get(
                    f"{_reader_base()}/{u}",
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=90,
                )
                if resp.status_code == 429:
                    time.sleep(3)
                    resp = httpx.get(
                        f"{_reader_base()}/{u}",
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=90,
                    )
                if resp.status_code >= 400:
                    err = (resp.text or "").strip()[:300] or f"HTTP {resp.status_code}"
                    docs.append({"url": u, "title": "", "content": "", "error": f"Jina reader failed: {err}"})
                    continue
                content = resp.text or ""
                if len(content.strip()) < _MIN_EXTRACT_CHARS:
                    docs.append(
                        {
                            "url": u,
                            "title": "",
                            "content": "",
                            "error": f"Jina reader too thin ({len(content.strip())} chars < {_MIN_EXTRACT_CHARS}) — treated as failure, not success",
                        }
                    )
                else:
                    docs.append({"url": u, "title": "", "content": content})
            except Exception as exc:  # noqa: BLE001
                logger.warning("Jina extract error: %s", exc)
                docs.append({"url": u, "title": "", "content": "", "error": f"Jina reader failed: {exc}"})
        return docs

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Jina",
            "badge": "paid",
            "tag": "Jina Search + Reader. Requires JINA_API_KEY.",
            "env_vars": [
                {"key": "JINA_API_KEY", "prompt": "Jina API key", "url": _KEY_DOC_URL},
                {"key": "JINA_SEARCH_BASE_URL", "prompt": "Search base override (optional)", "url": _KEY_DOC_URL},
                {"key": "JINA_READER_BASE_URL", "prompt": "Reader base override (optional)", "url": _KEY_DOC_URL},
            ],
            "docs_url": _KEY_DOC_URL,
        }


def _normalize_search(payload: Dict[str, Any], count: int) -> Dict[str, Any]:
    """Map {data: [{title,url,description}]} to the tool envelope."""
    web = []
    items = payload.get("data", []) if isinstance(payload, dict) else []
    for i, item in enumerate(items[:count] or []):
        if not isinstance(item, dict):
            continue
        web.append(
            {
                "title": str(item.get("title", "") or ""),
                "url": str(item.get("url", "") or ""),
                "description": str(item.get("description", "") or ""),
                "position": i + 1,
            }
        )
    return {"success": True, "data": {"web": web}}
