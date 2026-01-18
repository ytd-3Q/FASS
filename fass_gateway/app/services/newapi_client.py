from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from ..settings import settings


log = logging.getLogger(__name__)


def new_request_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class UpstreamError(RuntimeError):
    request_id: str
    status_code: int | None
    detail: str


def _now_ms() -> int:
    return int(time.time() * 1000)


def _base_url(base_url: str | None) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise UpstreamError(request_id="missing_config", status_code=None, detail="New API base_url is not configured")
    return base


def _headers(api_key: str | None) -> dict[str, str]:
    token = (api_key or "").strip()
    if not token:
        raise UpstreamError(request_id="missing_config", status_code=None, detail="New API key is not configured")
    return {"Authorization": f"Bearer {token}"}


def _truncate(text: str, limit: int = 1500) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[:limit] + "…"


async def _request_json(
    method: str,
    path: str,
    *,
    request_id: str,
    base_url: str | None,
    api_key: str | None,
    json: dict | None = None,
) -> dict:
    started = _now_ms()
    url = f"{_base_url(base_url)}{path}"
    headers = _headers(api_key)
    timeout = float(settings.newapi_timeout_seconds or 60.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(method, url, headers=headers, json=json)
    except Exception as e:
        log.warning(
            "newapi network error",
            extra={"request_id": request_id, "method": method, "path": path, "ms": _now_ms() - started, "error": type(e).__name__},
        )
        raise UpstreamError(request_id=request_id, status_code=None, detail=f"upstream network error: {type(e).__name__}")

    ms = _now_ms() - started
    log.info("newapi response", extra={"request_id": request_id, "method": method, "path": path, "status": resp.status_code, "ms": ms})

    if resp.status_code >= 400:
        body = _truncate(resp.text or "")
        raise UpstreamError(request_id=request_id, status_code=resp.status_code, detail=f"upstream {resp.status_code}: {body}")

    try:
        out = resp.json()
    except Exception:
        raise UpstreamError(request_id=request_id, status_code=resp.status_code, detail="upstream returned non-json body")
    return out if isinstance(out, dict) else {"data": out}


async def list_models(*, base_url: str | None, api_key: str | None, request_id: str | None = None) -> dict:
    rid = request_id or new_request_id()
    return await _request_json("GET", "/v1/models", request_id=rid, base_url=base_url, api_key=api_key)


async def chat_completions(payload: dict[str, Any], *, base_url: str | None, api_key: str | None, request_id: str | None = None) -> dict:
    rid = request_id or new_request_id()
    return await _request_json("POST", "/v1/chat/completions", request_id=rid, base_url=base_url, api_key=api_key, json=payload)


async def embeddings(payload: dict[str, Any], *, base_url: str | None, api_key: str | None, request_id: str | None = None) -> dict:
    rid = request_id or new_request_id()
    return await _request_json("POST", "/v1/embeddings", request_id=rid, base_url=base_url, api_key=api_key, json=payload)
