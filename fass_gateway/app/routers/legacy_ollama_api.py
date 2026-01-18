from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request

from ..settings import settings
from ..services.upstream_config import get_upstreams


log = logging.getLogger(__name__)

router = APIRouter(prefix="/legacy/ollama")


def _check_api_key(authorization: str | None) -> None:
    if not settings.api_key:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")


@router.post("/chat")
async def legacy_ollama_chat(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise HTTPException(status_code=400, detail="invalid payload")
    model = payload.get("model") or "default"
    messages = payload.get("messages") or []
    ollama_payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}

    cfg = get_upstreams()
    base = (cfg.ollama.base_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="Ollama base_url is not configured")
    headers: dict[str, str] = {}
    if cfg.ollama.api_key:
        headers["Authorization"] = f"Bearer {cfg.ollama.api_key}"
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(f"{base}/api/chat", headers=headers, json=ollama_payload)
            resp.raise_for_status()
            out = resp.json() or {}
    except Exception as e:
        log.info("legacy ollama error", extra={"error": type(e).__name__})
        raise HTTPException(status_code=502, detail=f"legacy ollama upstream error: {type(e).__name__}")
    msg = (out.get("message") or {}).get("content") or ""
    return {
        "id": out.get("id") or "ollama",
        "object": "chat.completion",
        "created": 0,
        "model": out.get("model") or model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": msg}, "finish_reason": "stop"}],
        "x_fass_legacy": "ollama",
    }

