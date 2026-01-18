from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Header, HTTPException

from ..settings import settings
from ..services import newapi_client
from ..services.upstream_config import get_upstreams


log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/models")


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


@router.get("/list")
async def list_models(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    cfg = get_upstreams()
    items: list[dict] = []

    newapi_err: str | None = None
    ollama_err: str | None = None

    if cfg.newapi.base_url and cfg.newapi.api_key:
        rid = newapi_client.new_request_id()
        try:
            r = await newapi_client.list_models(base_url=cfg.newapi.base_url, api_key=cfg.newapi.api_key, request_id=rid)
            for x in (r.get("data") or []):
                if isinstance(x, dict) and isinstance(x.get("id"), str):
                    items.append({"id": x["id"], "source": "newapi", "legacy": False})
        except newapi_client.UpstreamError as e:
            newapi_err = f"{e.detail} (request_id={e.request_id})"
    else:
        newapi_err = "New API 未配置"

    base = (cfg.ollama.base_url or "").rstrip("/")
    if base:
        headers: dict[str, str] = {}
        if cfg.ollama.api_key:
            headers["Authorization"] = f"Bearer {cfg.ollama.api_key}"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(f"{base}/api/tags", headers=headers)
                resp.raise_for_status()
                data = resp.json() or {}
                for m in (data.get("models") or []):
                    name = m.get("name") if isinstance(m, dict) else None
                    if isinstance(name, str) and name:
                        items.append({"id": name, "source": "ollama", "legacy": True})
        except Exception as e:
            log.info("ollama models fetch failed", extra={"error": type(e).__name__})
            ollama_err = f"Ollama 拉取失败：{type(e).__name__}"
    else:
        ollama_err = "Ollama 未配置"

    items.sort(key=lambda x: (0 if x.get("source") == "newapi" else 1, str(x.get("id") or "")))
    return {"items": items, "errors": {"newapi": newapi_err, "ollama": ollama_err}}

