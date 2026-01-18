from __future__ import annotations

import json
from pathlib import Path
from time import time

from ..db import open_db
import asyncio
from .memory import store
from .model_registry import model_registry
from .llm_proxy import proxy_chat_completions


def _now_ms() -> int:
    return int(time() * 1000)


def _db():
    base = Path(__file__).resolve().parents[2]
    return open_db(str(base / "data" / "fass_gateway.sqlite"))


async def run_dreaming(*, max_items: int = 10, collection: str = "shared") -> dict:
    max_items = min(max(1, int(max_items)), 50)
    conn = _db()
    rows = conn.execute("SELECT query, result_json, created_at_unix_ms FROM research_history ORDER BY id DESC LIMIT ?", (max_items,)).fetchall()
    conn.close()
    items = []
    for r in rows:
        try:
            result = json.loads(r["result_json"] or "null")
        except Exception:
            result = None
        items.append({"query": r["query"], "result": result})

    if not items:
        return {"status": "noop"}

    profile_id = model_registry.default_profile_id()
    profile = model_registry.get_profile(profile_id) if profile_id else None
    model = profile.model_alias_id if profile else "default"

    source_text = "\n\n".join(
        [f"Q: {it['query']}\nR: {json.dumps(it['result'], ensure_ascii=False)[:1500]}" for it in items]
    )
    prompt = (
        "你处于“梦境模式”。请把以下检索/爬取结果做自主消化：\n"
        "1) 合并重复信息；2) 归纳出长期有效的要点；3) 标注潜在冲突或不确定；\n"
        "输出结构化 Markdown：\n"
        "- 摘要\n- 关键要点(条目)\n- 待验证/冲突\n- 可行动任务\n"
    )

    content = None
    try:
        resp = await asyncio.wait_for(
            proxy_chat_completions({"model": model, "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": source_text}]}),
            timeout=10.0,
        )
        content = resp.get("choices", [{}])[0].get("message", {}).get("content")
    except Exception:
        content = None

    if not isinstance(content, str) or not content.strip():
        content = "## 摘要\n\n" + source_text[:8000]

    path = f"dream://{_now_ms()}"
    await store.upsert_texts(collection, [{"path": path, "content": content}])
    return {"status": "ok", "path": path, "items": len(items)}
