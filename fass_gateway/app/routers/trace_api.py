from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from time import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from ..db import open_db
from ..settings import settings
from ..services.llm_proxy import proxy_chat_completions
from ..services.trace_hub import hub


router = APIRouter(prefix="/api/trace")


def _now_ms() -> int:
    return int(time() * 1000)


def _db():
    base = Path(__file__).resolve().parents[2]
    return open_db(str(base / "data" / "fass_gateway.sqlite"))


def _check_api_key(authorization: str | None, token_query: str | None = None) -> None:
    if not settings.api_key:
        return
    if isinstance(token_query, str) and token_query.strip() == settings.api_key:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")


def _insert_trace(conversation_id: int, ev: dict[str, Any]) -> None:
    conn = _db()
    conn.execute(
        """
INSERT INTO trace_events(
  conversation_id, trace_id, parent_id, layer, from_agent, to_agent, event_kind,
  raw_command_text, content, ts_unix_ms, status, provider_id, model_id
) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
""",
        (
            conversation_id,
            ev.get("trace_id"),
            ev.get("parent_id"),
            ev.get("layer"),
            ev.get("from_agent"),
            ev.get("to_agent"),
            ev.get("event_kind"),
            ev.get("raw_command_text"),
            ev.get("content"),
            ev.get("ts_unix_ms"),
            ev.get("status"),
            ev.get("provider_id"),
            ev.get("model_id"),
        ),
    )
    conn.commit()
    conn.close()


async def _emit(conversation_id: int, ev: dict[str, Any]) -> None:
    _insert_trace(conversation_id, ev)
    await hub.publish(conversation_id, ev)


@router.post("/conversations")
async def create_conversation(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    l3_id = payload.get("l3_id")
    persona_id = payload.get("persona_id")
    title = payload.get("title")
    now = _now_ms()
    conn = _db()
    conn.execute(
        "INSERT INTO conversations(l3_id, persona_id, title, created_at_unix_ms, updated_at_unix_ms) VALUES(?,?,?,?,?)",
        (
            l3_id if isinstance(l3_id, str) else None,
            persona_id if isinstance(persona_id, str) else None,
            title if isinstance(title, str) else None,
            now,
            now,
        ),
    )
    cid = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.commit()
    conn.close()
    return {"conversation_id": cid}


@router.get("/conversations/{conversation_id}/events")
async def stream_events(conversation_id: int, token: str | None = None, authorization: str | None = Header(default=None)):
    _check_api_key(authorization, token_query=token)
    q = await hub.subscribe(conversation_id)

    async def gen():
        try:
            yield {"event": "ready", "data": json.dumps({"ok": True})}
            while True:
                ev = await q.get()
                yield {"event": "trace", "data": json.dumps(ev, ensure_ascii=False)}
        finally:
            await hub.unsubscribe(conversation_id, q)

    return EventSourceResponse(gen())


async def _fake_stream_chunks(conversation_id: int, base: dict[str, Any], text: str) -> None:
    chunk_size = 24
    buf = ""
    for i in range(0, len(text), chunk_size):
        buf += text[i : i + chunk_size]
        await _emit(conversation_id, {**base, "content": buf})
        await asyncio.sleep(0.05)


@router.post("/conversations/{conversation_id}/send")
async def send_message(conversation_id: int, request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise HTTPException(status_code=400, detail="text is required")
    text = text.strip()
    trace_id = str(uuid.uuid4())
    now = _now_ms()

    l3_base = {
        "trace_id": trace_id,
        "parent_id": None,
        "layer": "L3",
        "from_agent": "L3",
        "to_agent": "L2",
        "event_kind": "instruction",
        "raw_command_text": f"将用户需求拆分为可执行子任务，并指派给 L2/L1：{text}",
        "content": "正在制定调度指令…",
        "ts_unix_ms": now,
        "status": "running",
        "provider_id": None,
        "model_id": None,
    }
    await _emit(conversation_id, l3_base)

    l2_trace_id = str(uuid.uuid4())
    l2_base = {
        "trace_id": l2_trace_id,
        "parent_id": trace_id,
        "layer": "L2",
        "from_agent": "L2",
        "to_agent": "L1",
        "event_kind": "analysis",
        "raw_command_text": f"分析用户输入并提出执行步骤：{text}",
        "content": "",
        "ts_unix_ms": _now_ms(),
        "status": "running",
        "provider_id": None,
        "model_id": None,
    }
    try:
        resp_l2 = await proxy_chat_completions(
            {
                "model": "default",
                "messages": [
                    {"role": "system", "content": "你是执行层(L2)。给出条理清晰的分析与可执行步骤，简短。" },
                    {"role": "user", "content": text},
                ],
            }
        )
        l2_text = resp_l2.get("choices", [{}])[0].get("message", {}).get("content") or ""
    except Exception:
        l2_text = "L2 分析失败，降级为直接回答。"
    await _fake_stream_chunks(conversation_id, l2_base, l2_text)

    l1_trace_id = str(uuid.uuid4())
    l1_base = {
        "trace_id": l1_trace_id,
        "parent_id": l2_trace_id,
        "layer": "L1",
        "from_agent": "L1",
        "to_agent": "L3",
        "event_kind": "execution",
        "raw_command_text": "根据 L2 结果给出最终回复草案。",
        "content": "",
        "ts_unix_ms": _now_ms(),
        "status": "running",
        "provider_id": None,
        "model_id": None,
    }
    try:
        resp_l1 = await proxy_chat_completions(
            {
                "model": "default",
                "messages": [
                    {"role": "system", "content": "你是执行层(L1)。输出最终回复草案，语言自然，简洁但完整。"},
                    {"role": "user", "content": f"用户：{text}\n\nL2：{l2_text}"},
                ],
            }
        )
        l1_text = resp_l1.get("choices", [{}])[0].get("message", {}).get("content") or ""
    except Exception:
        l1_text = "执行失败。"
    await _fake_stream_chunks(conversation_id, l1_base, l1_text)

    await _emit(conversation_id, {**l3_base, "to_agent": "user", "event_kind": "final", "content": "已汇总。", "ts_unix_ms": _now_ms(), "status": "done"})
    return {"ok": True, "assistant": l1_text, "trace_id": trace_id}
