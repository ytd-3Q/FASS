from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from ..settings import settings
from ..services.embedding import embed_texts
from ..services.context_packs import get_context_pack
from ..services.llm_proxy import proxy_chat_completions, proxy_models
from ..services.model_defaults import get_defaults
from ..services.newapi_client import UpstreamError, embeddings as newapi_embeddings
from ..services.upstream_config import get_upstreams
from ..services.memory import store
from ..services.model_registry import model_registry
from ..services.research import enqueue_research

router = APIRouter()


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


@router.get("/v1/models")
async def v1_models(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    try:
        return await proxy_models()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {type(e).__name__}")


@router.post("/v1/chat/completions")
async def v1_chat_completions(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise HTTPException(status_code=400, detail="invalid payload")

    profile_id = request.headers.get("x-fass-profile") or payload.get("profile_id") or model_registry.default_profile_id()
    profile = model_registry.get_profile(profile_id) if isinstance(profile_id, str) and profile_id else None
    if profile:
        payload = dict(payload)
        if not payload.get("model") or payload.get("model") == "default":
            payload["model"] = profile.model_alias_id
        if isinstance(profile.params, dict):
            for k, v in profile.params.items():
                if k not in payload:
                    payload[k] = v

    rag_ctx = None
    if isinstance(payload.get("rag"), dict):
        rag = payload.get("rag") or {}
        collection = rag.get("collection") if isinstance(rag.get("collection"), str) else None
        top_k = int(rag.get("top_k") or 5)
        auto_research = bool(rag.get("auto_research")) if "auto_research" in rag else False
        query = None
        for m in reversed(payload["messages"]):
            if isinstance(m, dict) and m.get("role") == "user" and isinstance(m.get("content"), str):
                query = m["content"]
                break
        if query:
            try:
                query_vec = (await embed_texts([query]))[0]
            except Exception:
                query_vec = None
            hits = store.search(collection=collection, query_text=query, query_vec=query_vec, top_k=top_k)
            if hits:
                ctx_lines = []
                for h in hits:
                    content = str(h.get("content") or "")
                    if len(content) > 800:
                        content = content[:800] + "…"
                    ctx_lines.append(f"[{h.get('path')}] {content}")
                rag_ctx = "以下是检索到的资料片段（用于回答问题，优先引用）：\n" + "\n\n".join(ctx_lines)
            elif auto_research:
                try:
                    await enqueue_research(query, collection=collection or "shared")
                except Exception:
                    pass

    pack = get_context_pack()
    sys_msgs = []
    if profile and profile.system_prompt:
        sys_msgs.append({"role": "system", "content": profile.system_prompt})
    if pack:
        sys_msgs.append({"role": "system", "content": pack})
    if rag_ctx:
        sys_msgs.append({"role": "system", "content": rag_ctx})
    if sys_msgs:
        payload = dict(payload)
        payload.pop("rag", None)
        payload["messages"] = [*sys_msgs, *payload["messages"]]
    try:
        return await proxy_chat_completions(payload)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"upstream error: {type(e).__name__}")


@router.post("/v1/embeddings")
async def v1_embeddings(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid payload")
    defaults = get_defaults()
    if not payload.get("model") and defaults.embedding_model_id:
        payload = dict(payload)
        payload["model"] = defaults.embedding_model_id
    try:
        cfg = get_upstreams()
        return await newapi_embeddings(payload, base_url=cfg.newapi.base_url, api_key=cfg.newapi.api_key)
    except UpstreamError as e:
        raise HTTPException(status_code=502, detail=f"{e.detail} (request_id={e.request_id})")

