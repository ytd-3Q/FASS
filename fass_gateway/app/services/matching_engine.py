from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from time import time
from typing import Any

from ..db import open_db
from .audit_log import write as write_audit


def _now_ms() -> int:
    return int(time() * 1000)


def _db():
    base = Path(__file__).resolve().parents[2]
    return open_db(str(base / "data" / "fass_gateway.sqlite"))


_SENSITIVE_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"bearer\\s+[A-Za-z0-9_\\-\\.]+", re.IGNORECASE),
]


def _filter_sensitive(text: str) -> str:
    out = text
    for p in _SENSITIVE_PATTERNS:
        out = p.sub("[REDACTED]", out)
    return out


def _normalize_reason(reason: dict[str, Any]) -> str:
    for k in ("matching_logic", "decision_factors", "confidence_score"):
        if k not in reason:
            raise ValueError("missing reason field")
    cs = float(reason.get("confidence_score", 0.0))
    if cs < 0.0:
        cs = 0.0
    if cs > 1.0:
        cs = 1.0
    reason["confidence_score"] = cs
    reason["matching_logic"] = _filter_sensitive(str(reason["matching_logic"] or "")).strip()
    if not reason["matching_logic"]:
        reason["matching_logic"] = "n/a"
    if not isinstance(reason["decision_factors"], list):
        reason["decision_factors"] = [str(reason["decision_factors"])]
    reason["decision_factors"] = [str(x)[:80] for x in reason["decision_factors"] if str(x).strip()][:12]
    s = json.dumps(reason, ensure_ascii=False)
    if len(s) <= 1024:
        return s
    reason["matching_logic"] = reason["matching_logic"][:300] + "…"
    s2 = json.dumps(reason, ensure_ascii=False)
    if len(s2) <= 1024:
        return s2
    reason["decision_factors"] = reason["decision_factors"][:6]
    s3 = json.dumps(reason, ensure_ascii=False)
    return s3[:1024]


def _select(models: list[str], layer: str) -> tuple[str | None, dict[str, Any]]:
    lower = [m.lower() for m in models]
    if layer == "L1":
        candidates = [m for m in models if re.search(r"(flash|mini)", m, re.IGNORECASE)]
        picked = candidates[0] if candidates else (models[0] if models else None)
        return picked, {
            "matching_logic": "L1 优先选择名称包含 Flash/mini 的轻量模型；若无则回退到首个模型。",
            "decision_factors": ["name_contains_flash_or_mini", "fallback_first_model"],
            "confidence_score": 0.72 if candidates else 0.48,
        }
    if layer == "L2":
        candidates = [m for m in models if not re.search(r"(flash|mini)", m, re.IGNORECASE)]
        picked = candidates[0] if candidates else (models[0] if models else None)
        return picked, {
            "matching_logic": "L2 优先选择非 Flash/mini 的中等规模候选；若无则回退到首个模型。",
            "decision_factors": ["avoid_flash_mini", "fallback_first_model"],
            "confidence_score": 0.66 if candidates else 0.46,
        }
    picked = models[0] if models else None
    return picked, {
        "matching_logic": "L3 默认选择 provider 返回的首个模型（可被 routing_strategy 覆盖）。",
        "decision_factors": ["provider_first_model"],
        "confidence_score": 0.6 if picked else 0.2,
    }


def upsert_layer_presets(*, provider_id: str, models: list[str], actor: str) -> dict[str, Any]:
    now = _now_ms()
    conn = _db()
    conn.execute("BEGIN IMMEDIATE;")
    out: dict[str, Any] = {"provider_id": provider_id, "layers": {}}
    for layer in ("L1", "L2", "L3"):
        picked, reason = _select(models, layer)
        reason_json = _normalize_reason(reason)
        conn.execute(
            """
INSERT INTO layer_presets(layer, selected_model_id, selection_reason_json, default_prompt_template, constraints_json, updated_at_unix_ms)
VALUES(?,?,?,?,?,?)
ON CONFLICT(layer) DO UPDATE SET
  selected_model_id=excluded.selected_model_id,
  selection_reason_json=excluded.selection_reason_json,
  updated_at_unix_ms=excluded.updated_at_unix_ms
""",
            (
                layer,
                picked,
                reason_json,
                "",
                "{}",
                now,
            ),
        )
        out["layers"][layer] = {"selected_model_id": picked, "selection_reason_json": json.loads(reason_json)}
    conn.commit()
    conn.close()
    write_audit(actor, "LAYER_PRESET_MATCH", {"provider_id": provider_id, "layers": out["layers"]})
    return out


def list_layer_presets() -> list[dict[str, Any]]:
    conn = _db()
    rows = conn.execute(
        "SELECT layer, selected_model_id, selection_reason_json, default_prompt_template, constraints_json, updated_at_unix_ms FROM layer_presets ORDER BY layer ASC"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["selection_reason"] = json.loads(d.get("selection_reason_json") or "null")
        except Exception:
            d["selection_reason"] = None
        out.append(d)
    return out

