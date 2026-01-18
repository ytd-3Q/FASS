from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    parameters: dict[str, Any]
    read_only: bool = True
    dangerous: bool = False
    timeout_seconds: float = 30.0
    max_output_chars: int = 8000
    func: Callable[[dict[str, Any]], Any] | Callable[[dict[str, Any]], Awaitable[Any]] = lambda _: None


_TOOLS: dict[str, McpTool] = {}


def mcp_tool(
    *,
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    read_only: bool = True,
    dangerous: bool = False,
    timeout_seconds: float = 30.0,
    max_output_chars: int = 8000,
):
    def deco(fn):
        spec = McpTool(
            name=name,
            description=description,
            parameters=parameters or {"type": "object", "properties": {}, "additionalProperties": True},
            read_only=bool(read_only),
            dangerous=bool(dangerous),
            timeout_seconds=float(timeout_seconds),
            max_output_chars=int(max_output_chars),
            func=fn,
        )
        _TOOLS[name] = spec
        return fn

    return deco


def list_tools() -> list[McpTool]:
    return list(_TOOLS.values())


def get_tool(name: str) -> McpTool | None:
    return _TOOLS.get(name)

