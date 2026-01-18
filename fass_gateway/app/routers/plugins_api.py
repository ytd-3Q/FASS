from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from ..settings import settings
from ..services.plugins import invoke_tool, list_tools

router = APIRouter(prefix="/api/plugins")


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


@router.get("/tools")
async def tools(authorization: str | None = Header(default=None)) -> list[dict]:
    _check_api_key(authorization)
    return [
        {
            "plugin_id": t.plugin_id,
            "name": t.tool_name,
            "description": t.description,
            "parameters": t.parameters,
        }
        for t in list_tools()
    ]


@router.post("/invoke")
async def invoke(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    tool_name = payload.get("tool_name")
    arguments = payload.get("arguments") or {}
    if not isinstance(tool_name, str) or not tool_name:
        raise HTTPException(status_code=400, detail="tool_name is required")
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="arguments must be an object")
    try:
        result = await invoke_tool(tool_name, arguments)
    except KeyError:
        raise HTTPException(status_code=404, detail="tool not found")
    return {"result": result}

