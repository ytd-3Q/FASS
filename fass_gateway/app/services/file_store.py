from __future__ import annotations

import re
from pathlib import Path


def sanitize_rel_path(p: str) -> str:
    p = p.replace("\\", "/").strip()
    p = re.sub(r"^[a-zA-Z]:", "", p)
    p = p.lstrip("/")
    p = re.sub(r"\.\.+", ".", p)
    p = p.replace(":", "_")
    return p or "item.txt"


def default_fs_store_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "fs_store"


def write_text(collection: str, path: str, content: str, *, store_dir: Path | None = None) -> Path:
    base = store_dir or default_fs_store_dir()
    rel = sanitize_rel_path(path)
    out = base / sanitize_rel_path(collection) / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return out


def iter_texts(collection: str | None = None, *, store_dir: Path | None = None) -> list[tuple[str, str, str]]:
    base = store_dir or default_fs_store_dir()
    out: list[tuple[str, str, str]] = []
    if not base.exists():
        return out
    collections = [collection] if collection else [p.name for p in base.iterdir() if p.is_dir()]
    for col in collections:
        col_dir = base / sanitize_rel_path(col)
        if not col_dir.exists():
            continue
        for fp in col_dir.rglob("*"):
            if not fp.is_file():
                continue
            rel = fp.relative_to(col_dir).as_posix()
            try:
                content = fp.read_text(encoding="utf-8")
            except Exception:
                content = fp.read_text(encoding="utf-8", errors="ignore")
            out.append((col, rel, content))
    return out

