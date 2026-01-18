from __future__ import annotations

import json
import math
from pathlib import Path
from time import time

from ..db import open_db
from .embedding import embed_texts
from .mcp_executor import execute_tool
from .memory import store


def _now_ms() -> int:
    return int(time() * 1000)


def _db():
    base = Path(__file__).resolve().parents[2]
    return open_db(str(base / "data" / "fass_gateway.sqlite"))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += float(x) * float(y)
        na += float(x) * float(x)
        nb += float(y) * float(y)
    denom = math.sqrt(na) * math.sqrt(nb)
    return float(dot / denom) if denom else 0.0


async def enqueue_research(query: str, *, collection: str) -> dict:
    q = (query or "").strip()
    if not q:
        return {"queued": False, "reason": "empty"}
    now = _now_ms()
    vec = None
    try:
        vec = (await embed_texts([q]))[0]
    except Exception:
        vec = None

    conn = _db()
    rows = conn.execute(
        "SELECT query_embedding_json, result_json, created_at_unix_ms FROM research_history WHERE created_at_unix_ms>? ORDER BY id DESC LIMIT 50",
        (now - 3_600_000,),
    ).fetchall()
    for r in rows:
        try:
            prev = json.loads(r["query_embedding_json"]) if r["query_embedding_json"] else None
        except Exception:
            prev = None
        if vec and isinstance(prev, list):
            if _cosine(vec, prev) >= 0.92:
                conn.close()
                return {"queued": False, "reused": True, "result_json": json.loads(r["result_json"] or "null")}
    conn.close()

    conn = _db()
    conn.execute(
        "INSERT INTO research_jobs(query, collection, status, scheduled_at_unix_ms, query_embedding_json, created_at_unix_ms, updated_at_unix_ms) VALUES (?, ?, 'queued', ?, ?, ?, ?)",
        (q, collection, now, json.dumps(vec, ensure_ascii=False) if vec else None, now, now),
    )
    conn.commit()
    conn.close()
    return {"queued": True}


async def tick_research_jobs(searxng_base_url: str | None) -> None:
    base = (searxng_base_url or "").strip()
    if not base:
        return
    now = _now_ms()
    conn = _db()
    row = conn.execute(
        "SELECT * FROM research_jobs WHERE status='queued' AND scheduled_at_unix_ms<=? ORDER BY id ASC LIMIT 1",
        (now,),
    ).fetchone()
    if not row:
        conn.close()
        return
    job_id = int(row["id"])
    query = str(row["query"])
    collection = str(row["collection"])
    vec_json = row["query_embedding_json"]
    conn.execute("UPDATE research_jobs SET status='running', updated_at_unix_ms=? WHERE id=?", (now, job_id))
    conn.commit()
    conn.close()

    try:
        sr = await execute_tool(
            "web.search",
            {"searxng_base_url": base, "query": query, "max_results": 5},
        )
        urls = []
        if sr.get("ok") and isinstance(sr.get("result"), dict):
            for it in (sr["result"].get("results") or [])[:5]:
                if isinstance(it, dict) and isinstance(it.get("url"), str):
                    urls.append(it["url"])
        pages = []
        for u in urls[:3]:
            fr = await execute_tool("web.fetch", {"url": u, "max_chars": 6000})
            if fr.get("ok") and isinstance(fr.get("result"), dict):
                pages.append(fr["result"])
        items = []
        for p in pages:
            u = str(p.get("url") or "")
            c = str(p.get("content") or "")
            if u and c:
                items.append({"path": u, "content": c})
        if items:
            await store.upsert_texts(collection, items)
        result = {"query": query, "urls": urls[:3], "ingested": len(items)}

        conn = _db()
        conn.execute(
            "UPDATE research_jobs SET status='done', result_json=?, error=NULL, updated_at_unix_ms=? WHERE id=?",
            (json.dumps(result, ensure_ascii=False), _now_ms(), job_id),
        )
        conn.execute(
            "INSERT INTO research_history(query, query_embedding_json, result_json, created_at_unix_ms) VALUES (?, ?, ?, ?)",
            (query, vec_json, json.dumps(result, ensure_ascii=False), _now_ms()),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        conn = _db()
        conn.execute(
            "UPDATE research_jobs SET status='failed', error=?, updated_at_unix_ms=? WHERE id=?",
            (type(e).__name__, _now_ms(), job_id),
        )
        conn.commit()
        conn.close()

