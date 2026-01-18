from __future__ import annotations

import os
import platform
import shutil
import time

from ..services.mcp_registry import mcp_tool


@mcp_tool(
    name="system.get_server_stats",
    description="返回当前主机的基础状态信息（负载、CPU 核数、内存、磁盘等）",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
    read_only=True,
    dangerous=False,
    timeout_seconds=5.0,
    max_output_chars=8000,
)
def get_server_stats(_: dict) -> dict:
    load = os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
    mem_total = None
    mem_free = None
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("MemTotal:"):
                    mem_total = int(ln.split()[1]) * 1024
                if ln.startswith("MemAvailable:"):
                    mem_free = int(ln.split()[1]) * 1024
    except Exception:
        pass
    du = shutil.disk_usage("/")
    return {
        "time_unix_ms": int(time.time() * 1000),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "loadavg": {"1m": load[0], "5m": load[1], "15m": load[2]},
        "memory": {"total_bytes": mem_total, "available_bytes": mem_free},
        "disk_root": {"total_bytes": du.total, "used_bytes": du.used, "free_bytes": du.free},
    }


@mcp_tool(
    name="system.read_file_head",
    description="读取指定文件的前 N 行（只读）",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}, "max_lines": {"type": "integer", "minimum": 1, "maximum": 200}},
        "required": ["path"],
        "additionalProperties": False,
    },
    read_only=True,
    dangerous=False,
    timeout_seconds=5.0,
    max_output_chars=8000,
)
def read_file_head(args: dict) -> dict:
    path = str(args.get("path") or "")
    max_lines = int(args.get("max_lines") or 50)
    max_lines = min(max(1, max_lines), 200)
    out = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for i, ln in enumerate(f):
            if i >= max_lines:
                break
            out.append(ln.rstrip("\n"))
    return {"path": path, "lines": out}

