from __future__ import annotations

from pathlib import Path

from .memory import store


def _iter_text_files(root: Path, *, include_suffixes: set[str], ignore_dirs: set[str]) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_dir():
            continue
        if p.suffix.lower() not in include_suffixes:
            continue
        if any(part in ignore_dirs for part in p.parts):
            continue
        out.append(p)
    return out


async def ingest_diary(diary_root: Path) -> dict:
    files = _iter_text_files(diary_root, include_suffixes={".txt", ".md"}, ignore_dirs={".git", "node_modules"})
    items = []
    for fp in files:
        try:
            content = fp.read_text(encoding="utf-8")
        except Exception:
            content = fp.read_text(encoding="utf-8", errors="ignore")
        items.append({"path": str(fp), "content": content})
    changed = await store.upsert_texts("diary", items)
    return {"changed": changed, "files": len(files)}


async def ingest_workspace(workspace_root: Path) -> dict:
    files = _iter_text_files(
        workspace_root,
        include_suffixes={".py", ".md", ".txt", ".rs", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".toml"},
        ignore_dirs={".git", "node_modules", "__pycache__", ".venv", "target", ".trae"},
    )
    items = []
    for fp in files:
        if fp.stat().st_size > 512 * 1024:
            continue
        try:
            content = fp.read_text(encoding="utf-8")
        except Exception:
            content = fp.read_text(encoding="utf-8", errors="ignore")
        items.append({"path": str(fp), "content": content})
    changed = await store.upsert_texts("workspace", items)
    return {"changed": changed, "files": len(items)}

