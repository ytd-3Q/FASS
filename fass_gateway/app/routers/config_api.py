from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from ..settings import settings
from ..services.upstream_config import get_upstreams, set_upstreams


router = APIRouter(prefix="/api/config")


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


@router.get("/upstreams")
async def get_config_upstreams(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    cfg = get_upstreams()
    return {
        "newapi_base_url": cfg.newapi.base_url,
        "newapi_has_key": bool(cfg.newapi.api_key),
        "ollama_base_url": cfg.ollama.base_url,
        "ollama_has_key": bool(cfg.ollama.api_key),
    }


@router.post("/upstreams")
async def set_config_upstreams(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")

    newapi_base_url = payload.get("newapi_base_url")
    newapi_api_key = payload.get("newapi_api_key")
    ollama_base_url = payload.get("ollama_base_url")
    ollama_api_key = payload.get("ollama_api_key")

    if newapi_base_url is not None and not isinstance(newapi_base_url, str):
        raise HTTPException(status_code=400, detail="newapi_base_url must be a string or null")
    if newapi_api_key is not None and not isinstance(newapi_api_key, str):
        raise HTTPException(status_code=400, detail="newapi_api_key must be a string or null")
    if ollama_base_url is not None and not isinstance(ollama_base_url, str):
        raise HTTPException(status_code=400, detail="ollama_base_url must be a string or null")
    if ollama_api_key is not None and not isinstance(ollama_api_key, str):
        raise HTTPException(status_code=400, detail="ollama_api_key must be a string or null")

    out = set_upstreams(
        newapi_base_url=newapi_base_url,
        newapi_api_key=newapi_api_key,
        ollama_base_url=ollama_base_url,
        ollama_api_key=ollama_api_key,
    )
    return {
        "ok": True,
        "newapi_base_url": out.newapi.base_url,
        "newapi_has_key": bool(out.newapi.api_key),
        "ollama_base_url": out.ollama.base_url,
        "ollama_has_key": bool(out.ollama.api_key),
    }

