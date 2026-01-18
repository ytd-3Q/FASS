from __future__ import annotations

import json
from pathlib import Path

from ..db import open_db


def get_context_pack() -> str | None:
    base = Path(__file__).resolve().parents[2]
    conn = open_db(str(base / "data" / "fass_gateway.sqlite"))
    row = conn.execute("SELECT value FROM settings WHERE key='context_pack'").fetchone()
    conn.close()
    if not row:
        return None
    try:
        val = json.loads(row["value"])
    except Exception:
        return None
    if isinstance(val, str) and val.strip():
        return val
    return None

