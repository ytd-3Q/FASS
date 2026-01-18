from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from ..db import open_db
from ..settings import settings
from ..services.research import enqueue_research
from ..services.dreaming import run_dreaming


router = APIRouter(prefix="/api/automations")


def _db():
    base = Path(__file__).resolve().parents[2]
    return open_db(str(base / "data" / "fass_gateway.sqlite"))


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


@router.get("/research/jobs")
async def list_research_jobs(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    conn = _db()
    rows = conn.execute("SELECT * FROM research_jobs ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    return {"jobs": [dict(r) for r in rows]}


@router.post("/research/enqueue")
async def enqueue(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    query = payload.get("query")
    collection = payload.get("collection") or "shared"
    if not isinstance(query, str) or not query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    if not isinstance(collection, str) or not collection.strip():
        raise HTTPException(status_code=400, detail="collection must be string")
    return await enqueue_research(query, collection=collection)


@router.post("/dreaming/run")
async def dreaming_run(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    max_items = payload.get("max_items", 10)
    collection = payload.get("collection", "shared")
    if not isinstance(max_items, int):
        max_items = 10
    if not isinstance(collection, str):
        collection = "shared"
    return await run_dreaming(max_items=max_items, collection=collection)
