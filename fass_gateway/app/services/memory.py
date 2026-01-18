from __future__ import annotations

from pathlib import Path
from typing import Any
from time import time

from ..settings import settings
from .embedding import embed_texts
from .file_store import write_text


def _default_store_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "memoscore"

class _FallbackCore:
    def __init__(self, db_path: Path) -> None:
        import sqlite3
        import json

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute(
            """
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  collection TEXT NOT NULL,
  path TEXT NOT NULL,
  content TEXT NOT NULL,
  embedding_json TEXT,
  UNIQUE(collection, path)
);
"""
        )
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(documents)").fetchall()}
        if "embedding_json" not in cols:
            self.conn.execute("ALTER TABLE documents ADD COLUMN embedding_json TEXT")
        self._json = json
        self.conn.commit()

    def upsert_documents(self, collection: str, docs: list[dict[str, Any]]) -> int:
        changed = 0
        for d in docs:
            emb_json = None
            if d.get("embedding") is not None:
                emb_json = self._json.dumps(d["embedding"])
            self.conn.execute(
                """
INSERT INTO documents(collection, path, content, embedding_json) VALUES (?, ?, ?, ?)
ON CONFLICT(collection, path) DO UPDATE SET content=excluded.content, embedding_json=excluded.embedding_json
""",
                (collection, d["path"], d["content"], emb_json),
            )
            changed += 1
        self.conn.commit()
        return changed

    def search(self, collection: str | None, query_text: str | None, query_vec: list[float] | None, top_k: int) -> list[dict[str, Any]]:
        if not query_text:
            return []
        if query_vec:
            if collection:
                rows = self.conn.execute(
                    "SELECT id, collection, path, content, embedding_json FROM documents WHERE collection=? AND embedding_json IS NOT NULL",
                    (collection,),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT id, collection, path, content, embedding_json FROM documents WHERE embedding_json IS NOT NULL"
                ).fetchall()

            qn = sum(float(x) * float(x) for x in query_vec) ** 0.5 or 1.0
            scored: list[tuple[float, Any]] = []
            for r in rows:
                try:
                    emb = self._json.loads(r["embedding_json"])
                except Exception:
                    continue
                if not isinstance(emb, list) or not emb:
                    continue
                dn = sum(float(x) * float(x) for x in emb) ** 0.5 or 1.0
                dot = 0.0
                for a, b in zip(query_vec, emb):
                    dot += float(a) * float(b)
                score = dot / (qn * dn)
                scored.append((score, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            out = []
            for score, r in scored[:top_k]:
                out.append(
                    {
                        "id": int(r["id"]),
                        "collection": r["collection"],
                        "path": r["path"],
                        "content": r["content"],
                        "score": float(score),
                        "source": "fallback_vector",
                    }
                )
            return out

        q = f"%{query_text}%"
        if collection:
            rows = self.conn.execute(
                "SELECT id, collection, path, content FROM documents WHERE collection=? AND content LIKE ? LIMIT ?",
                (collection, q, top_k),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, collection, path, content FROM documents WHERE content LIKE ? LIMIT ?",
                (q, top_k),
            ).fetchall()
        return [{"id": int(r["id"]), "collection": r["collection"], "path": r["path"], "content": r["content"], "score": 1.0, "source": "fallback"} for r in rows]


class MemoryStore:
    def __init__(self, store_dir: Path | None = None) -> None:
        self.store_dir = store_dir or _default_store_dir()
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._core = None

    def _get_core(self):
        if self._core is not None:
            return self._core
        try:
            import memoscore  # type: ignore

            self._core = memoscore.MemosCore(str(self.store_dir), 768, 200_000)
        except Exception:
            self._core = _FallbackCore(self.store_dir / "fallback.sqlite")
        return self._core

    async def upsert_texts(self, collection: str, items: list[dict[str, Any]]) -> int:
        docs: list[dict[str, Any]] = []
        contents: list[str] = []
        now_ms = int(time() * 1000)
        for it in items:
            content = str(it["content"])
            p = str(it["path"])
            docs.append({"path": p, "content": content, "updated_at_unix_ms": now_ms})
            contents.append(content)
            if settings.fs_store_enabled:
                try:
                    write_text(collection, p, content, store_dir=Path(settings.fs_store_dir))
                except Exception:
                    pass

        try:
            embeddings = await embed_texts(contents)
            for d, e in zip(docs, embeddings, strict=True):
                d["embedding"] = e
        except Exception:
            pass

        core = self._get_core()
        return int(core.upsert_documents(collection, docs))

    def sync_indexes(self, limit: int = 200) -> int:
        core = self._get_core()
        fn = getattr(core, "sync_index_tasks", None)
        if not fn:
            return 0
        try:
            return int(fn(limit))
        except Exception:
            return 0

    def search(self, *, collection: str | None, query_text: str | None, query_vec: list[float] | None, top_k: int) -> list[dict[str, Any]]:
        core = self._get_core()
        return [r for r in core.search(collection, query_text, query_vec, top_k)]


store = MemoryStore()

