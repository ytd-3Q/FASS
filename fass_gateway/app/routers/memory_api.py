from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from ..settings import settings
from ..services.embedding import embed_texts
from ..services.ingest import ingest_diary, ingest_workspace
from ..services.file_store import iter_texts
from ..services.memory import store

router = APIRouter(prefix="/api/memory")


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


@router.post("/upsert")
async def upsert(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    collection = payload.get("collection")
    items = payload.get("items")
    if not isinstance(collection, str) or not collection:
        raise HTTPException(status_code=400, detail="collection is required")
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="items must be a list")
    changed = await store.upsert_texts(collection, items)
    return {"changed": changed}


@router.post("/search")
async def search(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    query = payload.get("query")
    collection = payload.get("collection")
    top_k = int(payload.get("top_k") or 8)
    if not isinstance(query, str) or not query:
        raise HTTPException(status_code=400, detail="query is required")
    query_vec = None
    if payload.get("use_vector", True):
        try:
            query_vec = (await embed_texts([query]))[0]
        except Exception:
            query_vec = None
    results = store.search(collection=collection if isinstance(collection, str) else None, query_text=query, query_vec=query_vec, top_k=top_k)
    return {"results": results}


@router.post("/ingest")
async def ingest(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    diary_root = payload.get("diary_root")
    workspace_root = payload.get("workspace_root")
    results: dict = {"diary": None, "workspace": None}
    if isinstance(diary_root, str) and diary_root:
        results["diary"] = await ingest_diary(Path(diary_root))
    if isinstance(workspace_root, str) and workspace_root:
        results["workspace"] = await ingest_workspace(Path(workspace_root))
    return results


@router.post("/rebuild")
async def rebuild(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    collection = payload.get("collection")
    if collection is not None and not isinstance(collection, str):
        raise HTTPException(status_code=400, detail="collection must be a string or null")

    items_by_col: dict[str, list[dict]] = {}
    for col, rel, content in iter_texts(collection if isinstance(collection, str) else None, store_dir=Path(settings.fs_store_dir)):
        items_by_col.setdefault(col, []).append({"path": rel, "content": content})

    out: dict[str, dict] = {}
    for col, items in items_by_col.items():
        changed = await store.upsert_texts(col, items)
        out[col] = {"changed": changed, "files": len(items)}
    return out

