from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from ..db import open_db
from ..settings import settings

router = APIRouter(prefix="/api/settings")


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


@router.get("")
async def get_settings(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    conn = _db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    stored = {r["key"]: json.loads(r["value"]) for r in rows}
    return {
        "stored": stored,
        "effective": {
            "fs_store_enabled": settings.fs_store_enabled,
            "fs_store_dir": settings.fs_store_dir,
            "embedding_provider": settings.embedding_provider,
            "embedding_model_path": settings.embedding_model_path,
            "embedding_model": settings.embedding_model,
            "llm_provider": settings.llm_provider,
            "llm_base_url": settings.llm_base_url,
            "llm_model": settings.llm_model,
        },
    }


@router.post("")
async def set_settings(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    conn = _db()
    for k, v in payload.items():
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(k), json.dumps(v, ensure_ascii=False)),
        )
        if k == "embedding_provider":
            settings.embedding_provider = str(v)
        if k == "embedding_model_path":
            settings.embedding_model_path = str(v)
        if k == "llm_provider":
            settings.llm_provider = str(v)
        if k == "llm_base_url":
            settings.llm_base_url = str(v)
        if k == "llm_model":
            settings.llm_model = str(v)
        if k == "embedding_model":
            settings.embedding_model = str(v)
        if k == "fs_store_enabled":
            settings.fs_store_enabled = bool(v)
        if k == "fs_store_dir":
            settings.fs_store_dir = str(v)
        if k == "api_key":
            settings.api_key = str(v) if v else None
        if k == "llm_api_key":
            settings.llm_api_key = str(v) if v else None
    conn.commit()
    conn.close()
    return {"ok": True}

