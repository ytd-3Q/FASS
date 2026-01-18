from __future__ import annotations

import hashlib
import json
import random
import sqlite3
from pathlib import Path
from time import sleep, time
from typing import Any

from ..db import open_db
from ..models.control import Provider
from .audit_log import write as write_audit
from .provider_registry import registry
from .provider_router import proxy_models_for_provider


def _now_ms() -> int:
    return int(time() * 1000)


def _db():
    base = Path(__file__).resolve().parents[2]
    return open_db(str(base / "data" / "fass_gateway.sqlite"))


def _hash_models(models: dict[str, Any]) -> str:
    s = json.dumps(models, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _normalize_models(models: dict[str, Any]) -> list[dict[str, Any]]:
    data = models.get("data")
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for m in data:
        if isinstance(m, dict) and isinstance(m.get("id"), str):
            out.append(m)
    return out


def _model_capabilities(model_obj: dict[str, Any]) -> dict[str, Any]:
    return {"raw": model_obj}


def _begin(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE;")


def _retryable(fn):
    def wrapped(*args, **kwargs):
        last: Exception | None = None
        for attempt in range(3):
            try:
                return fn(*args, **kwargs)
            except sqlite3.OperationalError as e:
                last = e
                if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                    raise
                sleep((0.08 + random.random() * 0.08) * (attempt + 1))
        if last:
            raise last

    return wrapped


@_retryable
def mark_provider_offline(provider_id: str, *, actor: str) -> int:
    now = _now_ms()
    expire = now + 90 * 24 * 3600 * 1000
    conn = _db()
    _begin(conn)
    cur = conn.execute(
        """
UPDATE model_catalog
SET status='offline',
    offline_since_unix_ms=COALESCE(offline_since_unix_ms, ?),
    expire_at_unix_ms=COALESCE(expire_at_unix_ms, ?),
    updated_at_unix_ms=?
WHERE provider_id=? AND status!='offline'
""",
        (now, expire, now, provider_id),
    )
    conn.commit()
    conn.close()
    write_audit(actor, "PROVIDER_CATALOG_OFFLINE", {"provider_id": provider_id, "affected": int(cur.rowcount or 0)})
    return int(cur.rowcount or 0)


@_retryable
def cleanup_offline(*, actor: str) -> int:
    now = _now_ms()
    conn = _db()
    _begin(conn)
    cur = conn.execute(
        """
DELETE FROM model_catalog
WHERE status='offline'
  AND expire_at_unix_ms IS NOT NULL
  AND expire_at_unix_ms < ?
  AND NOT EXISTS (
    SELECT 1 FROM trace_events te
    WHERE te.provider_id=model_catalog.provider_id AND te.model_id=model_catalog.model_id
  )
""",
        (now,),
    )
    conn.commit()
    n = int(cur.rowcount or 0)
    conn.close()
    if n:
        write_audit(actor, "MODEL_CATALOG_PRUNE", {"deleted": n})
    return n


async def fetch_and_cache(provider: Provider, *, actor: str) -> dict[str, Any]:
    models = await proxy_models_for_provider(provider)
    etag = _hash_models(models)
    return _upsert_models(provider.id, models, etag_or_hash=etag, actor=actor)


@_retryable
def _upsert_models(provider_id: str, models: dict[str, Any], *, etag_or_hash: str, actor: str) -> dict[str, Any]:
    now = _now_ms()
    rows = _normalize_models(models)
    conn = _db()
    _begin(conn)

    cached = conn.execute(
        "SELECT etag_or_hash FROM model_catalog WHERE provider_id=? ORDER BY fetched_at_unix_ms DESC LIMIT 1",
        (provider_id,),
    ).fetchone()
    if cached and cached["etag_or_hash"] == etag_or_hash:
        conn.commit()
        conn.close()
        return {"ok": True, "provider_id": provider_id, "changed": 0, "etag_or_hash": etag_or_hash, "cached": True}

    changed = 0
    conflicts = 0
    for m in rows:
        model_id = str(m["id"])
        raw_json = json.dumps(m, ensure_ascii=False)
        caps_json = json.dumps(_model_capabilities(m), ensure_ascii=False)

        existing = conn.execute(
            "SELECT raw_json, capabilities_json, status FROM model_catalog WHERE provider_id=? AND model_id=?",
            (provider_id, model_id),
        ).fetchone()

        if existing and (existing["raw_json"] != raw_json or existing["capabilities_json"] != caps_json):
            conflicts += 1
            write_audit(
                actor,
                "MODEL_CATALOG_CONFLICT",
                {"provider_id": provider_id, "model_id": model_id, "action": "upsert_update"},
            )

        conn.execute(
            """
INSERT INTO model_catalog(
  provider_id, model_id, raw_json, capabilities_json, status,
  fetched_at_unix_ms, etag_or_hash, created_at_unix_ms, updated_at_unix_ms
) VALUES(?,?,?,?,?,?,?,?,?)
ON CONFLICT(provider_id, model_id) DO UPDATE SET
  raw_json=excluded.raw_json,
  capabilities_json=excluded.capabilities_json,
  status='online',
  fetched_at_unix_ms=excluded.fetched_at_unix_ms,
  etag_or_hash=excluded.etag_or_hash,
  updated_at_unix_ms=excluded.updated_at_unix_ms
""",
            (provider_id, model_id, raw_json, caps_json, "online", now, etag_or_hash, now, now),
        )
        changed += 1

    conn.commit()
    conn.close()
    write_audit(
        actor,
        "MODEL_CATALOG_SYNC",
        {"provider_id": provider_id, "models": len(rows), "changed": changed, "conflicts": conflicts, "etag_or_hash": etag_or_hash},
    )
    return {"ok": True, "provider_id": provider_id, "changed": changed, "models": len(rows), "conflicts": conflicts, "etag_or_hash": etag_or_hash}


def list_cached(provider_id: str, *, status: str = "online", limit: int = 500) -> list[dict[str, Any]]:
    conn = _db()
    rows = conn.execute(
        "SELECT provider_id, model_id, raw_json, capabilities_json, status, fetched_at_unix_ms FROM model_catalog WHERE provider_id=? AND status=? ORDER BY model_id ASC LIMIT ?",
        (provider_id, status, int(limit)),
    ).fetchall()
    conn.close()
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        try:
            d["raw"] = json.loads(d.pop("raw_json"))
        except Exception:
            d["raw"] = None
        try:
            d["capabilities"] = json.loads(d.pop("capabilities_json"))
        except Exception:
            d["capabilities"] = None
        out.append(d)
    return out


async def on_default_provider_changed(old_provider_id: str | None, new_provider_id: str | None, *, actor: str) -> dict[str, Any]:
    if old_provider_id and old_provider_id != new_provider_id:
        mark_provider_offline(old_provider_id, actor=actor)
    if not new_provider_id:
        return {"ok": True, "provider_id": None}
    p = registry.get_provider(new_provider_id)
    if not p:
        return {"ok": False, "error": "provider not found"}
    return await fetch_and_cache(p, actor=actor)
