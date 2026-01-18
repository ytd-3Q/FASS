from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path
from time import time
from typing import Any

from ..db import open_db
from .audit_log import write as write_audit
from .audit_log import prune_expired as prune_audit_logs
from .model_catalog import cleanup_offline


def _now_ms() -> int:
    return int(time() * 1000)


def _db_path() -> Path:
    base = Path(__file__).resolve().parents[2]
    return (base / "data" / "fass_gateway.sqlite").resolve()


def _db():
    return open_db(str(_db_path()))


def _backup_dir() -> Path:
    base = Path(__file__).resolve().parents[2]
    d = (base / "data" / "backups").resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def backup(*, actor: str, reason: str) -> str:
    src = _db_path()
    ts = _now_ms()
    dst = _backup_dir() / f"fass_gateway.{ts}.sqlite"
    if src.exists():
        shutil.copy2(src, dst)
        write_audit(actor, "DB_BACKUP", {"path": str(dst), "reason": reason, "size": dst.stat().st_size})
    return dst.name


def integrity_check() -> dict[str, Any]:
    conn = _db()
    rows = conn.execute("PRAGMA integrity_check;").fetchall()
    conn.close()
    msgs = [r[0] for r in rows] if rows else []
    ok = len(msgs) == 1 and msgs[0] == "ok"
    return {"ok": ok, "messages": msgs}


def _checksum_table(conn: sqlite3.Connection, table: str, cols: list[str]) -> str:
    rows = conn.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {cols[0]} ASC").fetchall()
    h = hashlib.sha256()
    for r in rows:
        h.update(json.dumps(list(r), ensure_ascii=False).encode("utf-8"))
        h.update(b"\\n")
    return h.hexdigest()


def compute_checksums(*, actor: str) -> dict[str, str]:
    conn = _db()
    conn.execute("BEGIN IMMEDIATE;")
    now = _now_ms()
    out = {
        "l3_categories": _checksum_table(conn, "l3_categories", ["id", "updated_at_unix_ms"]),
        "personas": _checksum_table(conn, "personas", ["id", "updated_at_unix_ms"]),
        "model_catalog": _checksum_table(conn, "model_catalog", ["id", "updated_at_unix_ms", "status"]),
        "layer_presets": _checksum_table(conn, "layer_presets", ["layer", "updated_at_unix_ms"]),
    }
    for k, v in out.items():
        conn.execute(
            "INSERT INTO checksums(key, checksum, computed_at_unix_ms) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET checksum=excluded.checksum, computed_at_unix_ms=excluded.computed_at_unix_ms",
            (k, v, now),
        )
    conn.commit()
    conn.close()
    write_audit(actor, "CHECKSUM_COMPUTE", {"checksums": out})
    return out


def daily_tick(*, actor: str) -> dict[str, Any]:
    conn = _db()
    row = conn.execute("SELECT value FROM settings WHERE key='self_heal.last_daily_check_ms'").fetchone()
    last = int(row["value"]) if row else 0
    conn.close()
    now = _now_ms()
    if last and now - last < 24 * 3600 * 1000:
        return {"ok": True, "skipped": True}

    backup(actor=actor, reason="daily_precheck")
    check = integrity_check()
    compute_checksums(actor=actor)
    pruned = cleanup_offline(actor=actor)
    pruned_logs = prune_audit_logs()
    conn = _db()
    conn.execute(
        "INSERT INTO settings(key, value) VALUES('self_heal.last_daily_check_ms', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(now),),
    )
    conn.commit()
    conn.close()
    write_audit(actor, "DAILY_CHECK", {"integrity": check, "pruned_model_catalog": pruned, "pruned_audit_logs": pruned_logs})
    return {"ok": True, "integrity": check, "pruned_model_catalog": pruned, "pruned_audit_logs": pruned_logs}


def rollback_latest(*, actor: str) -> dict[str, Any]:
    backups = sorted(_backup_dir().glob("fass_gateway.*.sqlite"), reverse=True)
    if not backups:
        return {"ok": False, "error": "no backups"}
    src = backups[0]
    dst = _db_path()
    shutil.copy2(src, dst)
    write_audit(actor, "DB_ROLLBACK", {"backup": src.name})
    return {"ok": True, "backup": src.name}


def run_full_check(*, actor: str) -> dict[str, Any]:
    backup(actor=actor, reason="manual_full_check")
    check = integrity_check()
    checksums = compute_checksums(actor=actor)
    pruned_catalog = cleanup_offline(actor=actor)
    pruned_logs = prune_audit_logs()
    write_audit(
        actor,
        "MANUAL_CHECK",
        {
            "integrity": check,
            "checksums": checksums,
            "pruned_model_catalog": pruned_catalog,
            "pruned_audit_logs": pruned_logs,
        },
    )
    return {"ok": True, "integrity": check, "checksums": checksums, "pruned_model_catalog": pruned_catalog, "pruned_audit_logs": pruned_logs}
