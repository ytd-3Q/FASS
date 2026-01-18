from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from time import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from ..db import open_db
from ..settings import settings


def _now_ms() -> int:
    return int(time() * 1000)


def _db():
    base = Path(__file__).resolve().parents[2]
    return open_db(str(base / "data" / "fass_gateway.sqlite"))


def _fernet() -> Fernet:
    key = getattr(settings, "audit_log_key", None)
    if isinstance(key, str) and key.strip():
        return Fernet(key.strip().encode("utf-8"))
    seed = settings.api_key or "fass-audit-default"
    derived = base64.urlsafe_b64encode(hashlib.sha256(seed.encode("utf-8")).digest())
    return Fernet(derived)


def write(actor: str, action: str, payload: dict[str, Any], *, retention_days: int = 180) -> None:
    now = _now_ms()
    expire = now + retention_days * 24 * 3600 * 1000
    blob = _fernet().encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    conn = _db()
    conn.execute(
        "INSERT INTO audit_logs(actor, action, encrypted_payload, created_at_unix_ms, expire_at_unix_ms) VALUES(?,?,?,?,?)",
        (actor, action, blob, now, expire),
    )
    conn.commit()
    conn.close()


def list_logs(
    *,
    since_unix_ms: int | None = None,
    until_unix_ms: int | None = None,
    action: str | None = None,
    limit: int = 200,
    decrypt: bool = False,
) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if since_unix_ms is not None:
        where.append("created_at_unix_ms>=?")
        params.append(int(since_unix_ms))
    if until_unix_ms is not None:
        where.append("created_at_unix_ms<=?")
        params.append(int(until_unix_ms))
    if action is not None:
        where.append("action=?")
        params.append(str(action))
    sql = "SELECT id, actor, action, encrypted_payload, created_at_unix_ms, expire_at_unix_ms FROM audit_logs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created_at_unix_ms DESC LIMIT ?"
    params.append(int(limit))
    conn = _db()
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    out: list[dict[str, Any]] = []
    f = _fernet()
    for r in rows:
        item = dict(r)
        if decrypt:
            try:
                plain = f.decrypt(item["encrypted_payload"])
                item["payload"] = json.loads(plain.decode("utf-8"))
            except (InvalidToken, json.JSONDecodeError):
                item["payload"] = None
        item.pop("encrypted_payload", None)
        out.append(item)
    return out


def prune_expired() -> int:
    now = _now_ms()
    conn = _db()
    cur = conn.execute("DELETE FROM audit_logs WHERE expire_at_unix_ms < ?", (now,))
    conn.commit()
    n = int(cur.rowcount or 0)
    conn.close()
    return n

