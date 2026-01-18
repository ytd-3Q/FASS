from __future__ import annotations

import argparse
import asyncio
from collections import defaultdict
from pathlib import Path

from ..settings import settings
from ..services.file_store import iter_texts
from ..services.memory import store


async def _run(collection: str | None, *, fs_store_dir: str | None, no_vector: bool) -> dict[str, dict]:
    old_fs_enabled = settings.fs_store_enabled
    old_fs_dir = settings.fs_store_dir
    old_provider = settings.embedding_provider
    try:
        settings.fs_store_enabled = False
        if fs_store_dir:
            settings.fs_store_dir = fs_store_dir
        if no_vector:
            settings.embedding_provider = "disabled"

        items_by_col: dict[str, list[dict]] = defaultdict(list)
        for col, rel, content in iter_texts(collection, store_dir=Path(settings.fs_store_dir)):
            items_by_col[col].append({"path": rel, "content": content})

        out: dict[str, dict] = {}
        for col, items in items_by_col.items():
            changed = await store.upsert_texts(col, items)
            out[col] = {"changed": changed, "files": len(items)}
        return out
    finally:
        settings.fs_store_enabled = old_fs_enabled
        settings.fs_store_dir = old_fs_dir
        settings.embedding_provider = old_provider


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--collection", default=None, help="限定重建某个集合；不填表示全部")
    ap.add_argument("--fs-store-dir", default=None, help="指定 fs_store 目录；默认使用 settings.fs_store_dir")
    ap.add_argument("--no-vector", action="store_true", help="不生成向量，仅重建文本索引/兜底库")
    args = ap.parse_args()
    result = asyncio.run(_run(args.collection, fs_store_dir=args.fs_store_dir, no_vector=args.no_vector))
    for col, info in result.items():
        print(f"{col}: changed={info['changed']} files={info['files']}")


if __name__ == "__main__":
    main()

