from __future__ import annotations

import asyncio
import json
from multiprocessing import Pipe, Process
from typing import Any

from .mcp_registry import get_tool


def _truncate(obj: Any, max_chars: int) -> Any:
    try:
        s = json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    if len(s) <= max_chars:
        return obj
    return {"truncated": True, "text": s[:max_chars]}


def _child(tool_name: str, arguments: dict[str, Any], conn) -> None:
    try:
        from .mcp_loader import load_builtin_tools

        load_builtin_tools()
        tool = get_tool(tool_name)
        if not tool:
            conn.send({"ok": False, "error": "tool_not_found"})
            return
        fn = tool.func
        if asyncio.iscoroutinefunction(fn):
            result = asyncio.run(fn(arguments))  # type: ignore[misc]
        else:
            result = fn(arguments)  # type: ignore[misc]
        conn.send({"ok": True, "result": _truncate(result, tool.max_output_chars)})
    except Exception as e:
        conn.send({"ok": False, "error": type(e).__name__})


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tool = get_tool(tool_name)
    if not tool:
        raise KeyError(tool_name)
    parent, child = Pipe(duplex=False)
    p = Process(target=_child, args=(tool_name, arguments, child), daemon=True)
    p.start()
    child.close()
    try:
        if parent.poll(tool.timeout_seconds):
            out = parent.recv()
        else:
            out = {"ok": False, "error": "timeout"}
    finally:
        if p.is_alive():
            p.terminate()
        p.join(timeout=1)
        parent.close()
    return out
