from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from ..services.control_store import get_json, set_json
from ..services.mcp_executor import execute_tool
from ..services.mcp_registry import get_tool, list_tools
from ..services.model_catalog import list_cached
from ..services.provider_registry import registry
from ..settings import settings


router = APIRouter(prefix="/api/mcp")


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


def _enabled_tools() -> set[str]:
    data = get_json("mcp.enabled_tools")
    if isinstance(data, list) and all(isinstance(x, str) for x in data):
        return set(data)
    return {t.name for t in list_tools()}


def _save_enabled(enabled: set[str]) -> None:
    set_json("mcp.enabled_tools", sorted(enabled))


@router.get("/tools")
async def tools(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    enabled = _enabled_tools()
    out = []
    for t in list_tools():
        out.append(
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "read_only": t.read_only,
                "dangerous": t.dangerous,
                "timeout_seconds": t.timeout_seconds,
                "enabled": t.name in enabled,
            }
        )
    return {"tools": out}


@router.post("/tools/{tool_name}/enable")
async def enable_tool(tool_name: str, request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    enabled_flag = payload.get("enabled")
    if not isinstance(enabled_flag, bool):
        raise HTTPException(status_code=400, detail="enabled must be boolean")
    if not get_tool(tool_name):
        raise HTTPException(status_code=404, detail="tool not found")
    enabled = _enabled_tools()
    if enabled_flag:
        enabled.add(tool_name)
    else:
        enabled.discard(tool_name)
    _save_enabled(enabled)
    return {"ok": True}


@router.post("/execute")
async def execute(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()
    tool_name = payload.get("tool_name")
    arguments = payload.get("arguments") or {}
    if not isinstance(tool_name, str) or not tool_name:
        raise HTTPException(status_code=400, detail="tool_name is required")
    if not isinstance(arguments, dict):
        raise HTTPException(status_code=400, detail="arguments must be an object")
    tool = get_tool(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail="tool not found")
    if tool_name not in _enabled_tools():
        raise HTTPException(status_code=403, detail="tool disabled")
    if tool.dangerous:
        raise HTTPException(status_code=403, detail="dangerous tools are disabled")
    result = await execute_tool(tool_name, arguments)
    return result


@router.get("/models")
async def models(authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    cfg = registry.get()
    out: dict[str, dict] = {}
    for p in cfg.providers:
        out[p.id] = {"models": [x.get("model_id") for x in list_cached(p.id, status="online", limit=500)]}
    return {"providers": out}
