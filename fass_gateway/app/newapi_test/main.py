from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from ..services import newapi_client
from ..services.model_defaults import get_defaults, set_defaults
from ..services.upstream_config import get_upstreams, set_upstreams
from ..settings import settings


log = logging.getLogger(__name__)

app = FastAPI(title="FASS NewAPI Local Test", version="0.1.0")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _check_local_key(authorization: str | None) -> None:
    expected = (settings.local_test_api_key or "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="LOCAL_TEST_API_KEY is not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")


def _cors_allowed_origins() -> list[str] | None:
    raw = (settings.cors_allowed_origins or "").strip()
    if not raw:
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://192.168.1.5:5173",
        ]
    return [x.strip() for x in raw.split(",") if x.strip()]


if settings.allow_all_cors:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    origins = _cors_allowed_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _defaults_dict() -> dict[str, str | None]:
    d = get_defaults()
    return {"chat_model_id": d.chat_model_id, "embedding_model_id": d.embedding_model_id}


@app.get("/api/config/models")
async def get_model_defaults(authorization: str | None = Header(default=None)) -> dict:
    _check_local_key(authorization)
    return _defaults_dict()


@app.get("/api/config/upstreams")
async def get_upstream_config(authorization: str | None = Header(default=None)) -> dict:
    _check_local_key(authorization)
    cfg = get_upstreams()
    return {
        "newapi_base_url": cfg.newapi.base_url,
        "newapi_has_key": bool(cfg.newapi.api_key),
        "ollama_base_url": cfg.ollama.base_url,
        "ollama_has_key": bool(cfg.ollama.api_key),
    }


@app.post("/api/config/upstreams")
async def set_upstream_config(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_local_key(authorization)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    out = set_upstreams(
        newapi_base_url=payload.get("newapi_base_url"),
        newapi_api_key=payload.get("newapi_api_key"),
        ollama_base_url=payload.get("ollama_base_url"),
        ollama_api_key=payload.get("ollama_api_key"),
    )
    return {
        "ok": True,
        "newapi_base_url": out.newapi.base_url,
        "newapi_has_key": bool(out.newapi.api_key),
        "ollama_base_url": out.ollama.base_url,
        "ollama_has_key": bool(out.ollama.api_key),
    }


@app.get("/api/models/list")
async def list_models(authorization: str | None = Header(default=None)) -> dict:
    _check_local_key(authorization)
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
            ollama_err = f"Ollama 拉取失败：{type(e).__name__}"
    else:
        ollama_err = "Ollama 未配置"

    items.sort(key=lambda x: (0 if x.get("source") == "newapi" else 1, str(x.get("id") or "")))
    return {"items": items, "errors": {"newapi": newapi_err, "ollama": ollama_err}}


@app.post("/api/config/models")
async def set_model_defaults(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_local_key(authorization)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    chat_model_id = payload.get("chat_model_id")
    embedding_model_id = payload.get("embedding_model_id")
    if chat_model_id is not None and not isinstance(chat_model_id, str):
        raise HTTPException(status_code=400, detail="chat_model_id must be a string or null")
    if embedding_model_id is not None and not isinstance(embedding_model_id, str):
        raise HTTPException(status_code=400, detail="embedding_model_id must be a string or null")

    cfg = get_upstreams()
    rid = newapi_client.new_request_id()
    models = await newapi_client.list_models(base_url=cfg.newapi.base_url, api_key=cfg.newapi.api_key, request_id=rid)
    ids = {x.get("id") for x in (models.get("data") or []) if isinstance(x, dict) and isinstance(x.get("id"), str)}
    if chat_model_id and chat_model_id not in ids:
        raise HTTPException(status_code=400, detail="unknown chat_model_id")
    if embedding_model_id and embedding_model_id not in ids:
        raise HTTPException(status_code=400, detail="unknown embedding_model_id")

    out = set_defaults(chat_model_id=chat_model_id, embedding_model_id=embedding_model_id)
    return {"ok": True, "chat_model_id": out.chat_model_id, "embedding_model_id": out.embedding_model_id}


@app.get("/v1/models")
async def v1_models(authorization: str | None = Header(default=None)) -> dict:
    _check_local_key(authorization)
    rid = newapi_client.new_request_id()
    try:
        cfg = get_upstreams()
        return await newapi_client.list_models(base_url=cfg.newapi.base_url, api_key=cfg.newapi.api_key, request_id=rid)
    except newapi_client.UpstreamError as e:
        raise HTTPException(status_code=502, detail=f"{e.detail} (request_id={e.request_id})")


@app.post("/v1/chat/completions")
async def v1_chat_completions(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_local_key(authorization)
    payload = await request.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise HTTPException(status_code=400, detail="invalid payload")
    defaults = get_defaults()
    if not payload.get("model") and defaults.chat_model_id:
        payload = dict(payload)
        payload["model"] = defaults.chat_model_id
    rid = newapi_client.new_request_id()
    try:
        cfg = get_upstreams()
        return await newapi_client.chat_completions(payload, base_url=cfg.newapi.base_url, api_key=cfg.newapi.api_key, request_id=rid)
    except newapi_client.UpstreamError as e:
        raise HTTPException(status_code=502, detail=f"{e.detail} (request_id={e.request_id})")


@app.post("/v1/embeddings")
async def v1_embeddings(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_local_key(authorization)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    defaults = get_defaults()
    if not payload.get("model") and defaults.embedding_model_id:
        payload = dict(payload)
        payload["model"] = defaults.embedding_model_id
    rid = newapi_client.new_request_id()
    try:
        cfg = get_upstreams()
        return await newapi_client.embeddings(payload, base_url=cfg.newapi.base_url, api_key=cfg.newapi.api_key, request_id=rid)
    except newapi_client.UpstreamError as e:
        raise HTTPException(status_code=502, detail=f"{e.detail} (request_id={e.request_id})")


@app.post("/legacy/ollama/chat")
async def legacy_ollama_chat(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_local_key(authorization)
    payload = await request.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise HTTPException(status_code=400, detail="invalid payload")
    model = payload.get("model") or "default"
    messages = payload.get("messages") or []
    ollama_payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
    base = (settings.ollama_base_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=500, detail="OLLAMA_BASE_URL is not configured")
    started = _now_ms()
    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(f"{base}/api/chat", json=ollama_payload)
            resp.raise_for_status()
            out = resp.json() or {}
    except Exception as e:
        log.warning("ollama legacy error", extra={"ms": _now_ms() - started, "error": type(e).__name__})
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
