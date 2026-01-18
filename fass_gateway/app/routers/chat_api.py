from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from ..settings import settings
from ..services.llm_proxy import proxy_chat_completions

router = APIRouter(prefix="/api/chat")


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


@router.post("/roundtable")
async def roundtable(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    topic = payload.get("topic")
    participants = payload.get("participants")
    if not isinstance(topic, str) or not topic:
        raise HTTPException(status_code=400, detail="topic is required")
    if not isinstance(participants, list) or not participants:
        raise HTTPException(status_code=400, detail="participants must be a non-empty list")

    messages: list[dict] = [{"role": "user", "content": topic}]
    transcript: list[dict] = []

    for p in participants:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name") or "Participant")
        model = str(p.get("model") or "default")
        sys = {
            "role": "system",
            "content": f"你在圆桌会议中发言。你的称呼是：{name}。请围绕议题给出结构化观点，避免重复他人观点。",
        }
        resp = await proxy_chat_completions({"model": model, "messages": [sys, *messages]})
        content = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
        msg = {"role": "assistant", "name": name, "content": content}
        transcript.append(msg)
        messages.append({"role": "assistant", "content": f"[{name}] {content}"})

    return {"messages": transcript}

