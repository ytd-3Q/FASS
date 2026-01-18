from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from ..db import open_db

T = TypeVar("T", bound=BaseModel)


def _db():
    base = Path(__file__).resolve().parents[2]
    return open_db(str(base / "data" / "fass_gateway.sqlite"))


def get_json(key: str) -> Any | None:
    conn = _db()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    if not row:
        return None
    try:
        return json.loads(row["value"])
    except Exception:
        return None


def set_json(key: str, value: Any) -> None:
    conn = _db()
    conn.execute(
        "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, json.dumps(value, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def get_model(key: str, model: type[T], *, default: T) -> T:
    data = get_json(key)
    if data is None:
        return default
    try:
        return model.model_validate(data)
    except ValidationError:
        return default


def set_model(key: str, value: BaseModel) -> None:
    set_json(key, value.model_dump(mode="json"))

