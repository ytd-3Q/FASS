from __future__ import annotations

import json
from pathlib import Path
from time import time

from fastapi import APIRouter, Header, HTTPException, Request

from ..db import open_db
from ..settings import settings

router = APIRouter(prefix="/api/tasks")


def _db():
    base = Path(__file__).resolve().parents[2]
    return open_db(str(base / "data" / "fass_gateway.sqlite"))


def _now_ms() -> int:
    return int(time() * 1000)


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
async def list_tasks(authorization: str | None = Header(default=None)) -> list[dict]:
    _check_api_key(authorization)
    conn = _db()
    rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@router.post("")
async def create_task(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    name = payload.get("name")
    cron = payload.get("cron")
    task_payload = payload.get("payload") or {}
    if not isinstance(name, str) or not name:
        raise HTTPException(status_code=400, detail="name is required")
    if cron is not None and not isinstance(cron, str):
        raise HTTPException(status_code=400, detail="cron must be a string or null")
    if not isinstance(task_payload, dict):
        raise HTTPException(status_code=400, detail="payload must be an object")
    now = _now_ms()
    conn = _db()
    conn.execute(
        "INSERT INTO tasks(name, cron, payload_json, enabled, created_at_unix_ms, updated_at_unix_ms) VALUES (?, ?, ?, 1, ?, ?)",
        (name, cron, json.dumps(task_payload, ensure_ascii=False), now, now),
    )
    conn.commit()
    task_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return dict(row)


@router.post("/{task_id}")
async def update_task(task_id: int, request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    fields = []
    values = []
    for k in ("name", "cron", "enabled"):
        if k in payload:
            fields.append(f"{k}=?")
            values.append(payload[k])
    if "payload" in payload:
        fields.append("payload_json=?")
        values.append(json.dumps(payload["payload"], ensure_ascii=False))
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    fields.append("updated_at_unix_ms=?")
    values.append(_now_ms())
    values.append(task_id)
    conn = _db()
    conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE id=?", values)
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="task not found")
    return dict(row)


@router.delete("/{task_id}")
async def delete_task(task_id: int, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    conn = _db()
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

