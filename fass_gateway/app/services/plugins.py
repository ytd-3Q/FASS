from __future__ import annotations

import json
import re
import subprocess
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .memory import store


@dataclass(frozen=True)
class ToolSpec:
    plugin_id: str
    tool_name: str
    description: str
    parameters: dict[str, Any]
    runtime: dict[str, Any]
    postprocess: dict[str, Any] | None = None
    legacy_command: str | None = None


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_split_cmd(cmd: Any) -> list[str]:
    if isinstance(cmd, list) and all(isinstance(x, str) for x in cmd):
        return cmd
    if isinstance(cmd, str):
        return [cmd]
    raise ValueError("invalid command")


def load_v2_tools(plugins_dir: Path) -> list[ToolSpec]:
    out: list[ToolSpec] = []
    if not plugins_dir.exists():
        return out
    for plugin_json in plugins_dir.rglob("plugin.json"):
        data = _read_json(plugin_json)
        plugin_id = str(data.get("id") or plugin_json.parent.name)
        runtime = dict(data.get("runtime") or {})
        runtime.setdefault("type", "stdio")
        runtime.setdefault("cwd", str(plugin_json.parent))
        for t in data.get("tools") or []:
            out.append(
                ToolSpec(
                    plugin_id=plugin_id,
                    tool_name=str(t["name"]),
                    description=str(t.get("description") or ""),
                    parameters=dict(t.get("parameters") or {}),
                    runtime=dict(runtime),
                    postprocess=dict(t.get("postprocess") or {}) or None,
                )
            )
    return out


def load_legacy_tools(legacy_dir: Path) -> list[ToolSpec]:
    out: list[ToolSpec] = []
    if not legacy_dir.exists():
        return out
    for manifest_path in legacy_dir.rglob("plugin-manifest.json"):
        try:
            data = _read_json(manifest_path)
        except Exception:
            continue
        communication = data.get("communication") or {}
        protocol = communication.get("protocol")
        if protocol != "stdio":
            continue
        entry = data.get("entryPoint") or {}
        cmd = entry.get("command")
        script = entry.get("script")
        entry_type = entry.get("type")

        command_argv: list[str] | None = None
        if isinstance(cmd, str) and cmd.strip():
            if isinstance(script, str) and script.strip():
                command_argv = [cmd, script]
            else:
                command_argv = shlex.split(cmd)

        if not command_argv:
            continue
        invocation = (data.get("capabilities") or {}).get("invocationCommands") or []
        for inv in invocation:
            command_identifier = inv.get("commandIdentifier") or inv.get("name")
            tool_name = command_identifier
            if not tool_name:
                continue
            plugin_id = str(data.get("name") or manifest_path.parent.name)
            params_raw = inv.get("parameters")
            params_dict: dict[str, Any] = params_raw if isinstance(params_raw, dict) else {}
            out.append(
                ToolSpec(
                    plugin_id=plugin_id,
                    tool_name=f"{plugin_id}.{tool_name}",
                    description=str(inv.get("description") or ""),
                    parameters=params_dict,
                    runtime={
                        "type": "stdio",
                        "command": command_argv,
                        "cwd": str(manifest_path.parent),
                        "entry_type": str(entry_type or ""),
                    },
                    legacy_command=str(command_identifier),
                )
            )
    return out


def list_tools() -> list[ToolSpec]:
    base = Path(__file__).resolve().parents[3]
    v2 = load_v2_tools(base / "plugins")
    legacy = load_legacy_tools(base / "legacy_plugins")
    return v2 + legacy


def _run_stdio(command: list[str], *, cwd: str | None, payload: dict[str, Any]) -> dict[str, Any]:
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    assert proc.stdin and proc.stdout
    inp = json.dumps(payload, ensure_ascii=False) + "\n"
    out, err = proc.communicate(inp, timeout=30)
    stdout_lines = [ln for ln in (out or "").splitlines() if ln.strip()]
    if not stdout_lines:
        raise RuntimeError(f"plugin returned no output. stderr={(err or '')[:2000]}")
    return json.loads(stdout_lines[0])


async def invoke_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    tools = {t.tool_name: t for t in list_tools()}
    spec = tools.get(tool_name)
    if not spec:
        raise KeyError(tool_name)

    if spec.runtime.get("type") != "stdio":
        raise RuntimeError("unsupported runtime")

    cmd = _safe_split_cmd(spec.runtime.get("command"))
    cwd = spec.runtime.get("cwd")
    if spec.legacy_command:
        payload = {"command": spec.legacy_command, **arguments}
    else:
        payload = {"tool_name": tool_name, **arguments}
    result = _run_stdio(cmd, cwd=cwd, payload=payload)

    if spec.postprocess and spec.postprocess.get("memory_upsert"):
        cfg = spec.postprocess["memory_upsert"]
        collection = str(cfg.get("collection") or "external")
        path_field = str(cfg.get("path_field") or "path")
        content_field = str(cfg.get("content_field") or "content")
        if isinstance(result, dict) and path_field in result and content_field in result:
            await store.upsert_texts(collection, [{"path": result[path_field], "content": result[content_field]}])

    if spec.legacy_command and isinstance(result, dict):
        text = result.get("result") if isinstance(result.get("result"), str) else ""
        m = re.search(r" at (.+)$", text)
        if m:
            fp = Path(m.group(1).strip())
            if fp.exists() and fp.is_file():
                try:
                    content = fp.read_text(encoding="utf-8")
                except Exception:
                    content = fp.read_text(encoding="utf-8", errors="ignore")
                await store.upsert_texts("diary", [{"path": str(fp), "content": content}])

    return result

