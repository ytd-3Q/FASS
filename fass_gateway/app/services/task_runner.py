from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any

from ..db import open_db
from ..settings import settings
from .provider_health import monitor as provider_health_monitor
from .memory import store as memory_store
from .control_store import get_json
from .research import tick_research_jobs
from .dreaming import run_dreaming
from .timeline import TimelineBuildConfig, build_timeline
from .self_heal import daily_tick as self_heal_daily_tick


def _now_ms() -> int:
    return int(time() * 1000)


def _db():
    base = Path(__file__).resolve().parents[2]
    return open_db(str(base / "data" / "fass_gateway.sqlite"))


@dataclass
class TaskRunner:
    poll_seconds: float = 5.0
    _task: asyncio.Task | None = None
    _stop: asyncio.Event | None = None

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._stop:
            self._stop.set()
        if self._task:
            try:
                await self._task
            except Exception:
                pass

    async def _loop(self) -> None:
        assert self._stop is not None
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                pass
            await asyncio.sleep(self.poll_seconds)

    async def _tick(self) -> None:
        conn = _db()
        rows = conn.execute("SELECT * FROM tasks WHERE enabled=1 ORDER BY id ASC").fetchall()
        tasks = [dict(r) for r in rows]
        conn.close()

        for t in tasks:
            payload = {}
            try:
                payload = json.loads(t.get("payload_json") or "{}")
            except Exception:
                payload = {}

            if not isinstance(payload, dict):
                continue
            if payload.get("type") != "timeline_build":
                pass
            else:
                interval_seconds = payload.get("interval_seconds")
                if not isinstance(interval_seconds, int) or interval_seconds <= 0:
                    continue

                last_run = payload.get("last_run_unix_ms")
                last_run = int(last_run) if isinstance(last_run, int) else 0
                now = _now_ms()
                if last_run and now - last_run < interval_seconds * 1000:
                    continue

                diary_root = payload.get("diary_root")
                project_base_path = payload.get("project_base_path")
                timeline_dir = payload.get("timeline_dir")
                summary_model = payload.get("summary_model") or settings.llm_model or "default"
                min_content_length = payload.get("min_content_length", 100)
                max_files = payload.get("max_files")

                if not isinstance(diary_root, str) or not isinstance(project_base_path, str):
                    continue
                if timeline_dir is not None and not isinstance(timeline_dir, str):
                    continue
                if not isinstance(min_content_length, int):
                    min_content_length = 100
                if max_files is not None and not isinstance(max_files, int):
                    max_files = None

                cfg = TimelineBuildConfig(
                    diary_root=Path(diary_root),
                    project_base_path=Path(project_base_path),
                    timeline_dir=Path(timeline_dir) if timeline_dir else Path(project_base_path) / "timeline",
                    summary_model=str(summary_model),
                    min_content_length=min_content_length,
                    max_files=max_files,
                )

                result = await build_timeline(cfg, wait_ms_if_busy=0)
                if not isinstance(result, dict) or result.get("status") == "busy":
                    continue

                payload["last_run_unix_ms"] = now
                self._update_task_payload(int(t["id"]), payload)
                continue
            if payload.get("type") != "dreaming":
                continue

            interval_seconds = payload.get("interval_seconds")
            if not isinstance(interval_seconds, int) or interval_seconds <= 0:
                continue
            last_run = payload.get("last_run_unix_ms")
            last_run = int(last_run) if isinstance(last_run, int) else 0
            now = _now_ms()
            if last_run and now - last_run < interval_seconds * 1000:
                continue

            max_items = payload.get("max_items", 10)
            collection = payload.get("collection", "shared")
            if not isinstance(max_items, int):
                max_items = 10
            if not isinstance(collection, str):
                collection = "shared"
            await run_dreaming(max_items=max_items, collection=collection)

            payload["last_run_unix_ms"] = now
            self._update_task_payload(int(t["id"]), payload)

        await provider_health_monitor.tick()
        memory_store.sync_indexes(limit=200)
        base = get_json("web.searxng_base_url")
        await tick_research_jobs(base if isinstance(base, str) else None)
        try:
            self_heal_daily_tick(actor="task_runner")
        except Exception:
            pass

    def _update_task_payload(self, task_id: int, payload: dict[str, Any]) -> None:
        conn = _db()
        conn.execute(
            "UPDATE tasks SET payload_json=?, updated_at_unix_ms=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), _now_ms(), task_id),
        )
        conn.commit()
        conn.close()


runner = TaskRunner()
