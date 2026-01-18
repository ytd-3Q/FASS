from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..settings import settings
from .llm_proxy import proxy_chat_completions
from .memory import store


_DATE_RE = re.compile(r"^(?:\[(\d{4}[\.\-]\d{1,2}[\.\-]\d{1,2})\]\s*-\s*(.+)|(\d{4}[\.\-]\d{1,2}[\.\-]\d{1,2})-(.+))$")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def _safe_name(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[\\\\/:*?\"<>|]", "_", s)
    return s or "unknown"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass(frozen=True)
class TimelineBuildConfig:
    diary_root: Path
    project_base_path: Path
    timeline_dir: Path
    summary_model: str
    min_content_length: int = 100
    max_files: int | None = None
    include_extensions: tuple[str, ...] = (".txt", ".md")
    ignored_path_regexes: tuple[re.Pattern[str], ...] = (
        re.compile(r".*已整理.*"),
        re.compile(r".*MusicDiary.*"),
    )


class _Lock:
    def __init__(self, lock_path: Path, *, stale_ms: int = 6 * 3600 * 1000) -> None:
        self.lock_path = lock_path
        self.stale_ms = stale_ms

    def acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        now = _now_ms()
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(json.dumps({"pid": os.getpid(), "created_at_unix_ms": now}, ensure_ascii=False))
            return True
        except FileExistsError:
            try:
                info = _read_json(self.lock_path, {})
                created = int(info.get("created_at_unix_ms") or 0)
            except Exception:
                created = 0
            if created and now - created > self.stale_ms:
                try:
                    self.lock_path.unlink(missing_ok=True)
                except Exception:
                    return False
                return self.acquire()
            return False

    def release(self) -> None:
        try:
            self.lock_path.unlink(missing_ok=True)
        except Exception:
            pass


_GLOBAL_ASYNC_LOCK = asyncio.Lock()


def _summary_system_prompt() -> str:
    return (
        "You are a highly efficient text summarizer. Your only task is to read the provided diary entry "
        "and distill its core event into a single, concise, headline-style sentence.\n\n"
        "You MUST wrap your final summary sentence within the following tags: <<<summary>>> and <<</summary>>>.\n"
        "Output ONLY the tagged summary and nothing else.\n\n"
        "NOW, PROCESS THE FOLLOWING DIARY ENTRY:"
    )


async def _summarize(text: str, *, model: str) -> tuple[str | None, str]:
    try:
        resp = await proxy_chat_completions(
            {
                "model": model or settings.llm_model or "default",
                "messages": [
                    {"role": "system", "content": _summary_system_prompt()},
                    {"role": "user", "content": text},
                ],
                "stream": False,
            }
        )
    except Exception as e:
        msg = str(e)
        if "no candidates returned" in msg.lower():
            return None, "skipped_sensitive"
        return None, "error"

    content = ((resp.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    m = re.search(r"<<<summary>>>(.*?)<<<\s*\/?\s*summary\s*>>>", content, re.IGNORECASE | re.DOTALL)
    if m and m.group(1).strip():
        return m.group(1).strip(), "summarized"
    one_line = content.strip().splitlines()[0].strip() if content.strip() else ""
    return (one_line or None), "fallback"


async def build_timeline(cfg: TimelineBuildConfig, *, wait_ms_if_busy: int = 0) -> dict[str, Any]:
    lock = _Lock(cfg.timeline_dir / ".timeline_build.lock")
    start = _now_ms()

    waited = 0
    while not lock.acquire():
        if waited >= wait_ms_if_busy:
            return {"ok": False, "status": "busy"}
        await asyncio.sleep(0.2)
        waited += 200

    async with _GLOBAL_ASYNC_LOCK:
        try:
            processed_db_path = cfg.timeline_dir / "processed_files_db.json"
            processed_db = _read_json(processed_db_path, {})
            if not isinstance(processed_db, dict):
                processed_db = {}

            files: list[Path] = []
            for p in cfg.diary_root.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in cfg.include_extensions:
                    continue
                if any(r.match(str(p)) for r in cfg.ignored_path_regexes):
                    continue
                if p.parent.name.endswith("簇"):
                    continue
                files.append(p)

            files.sort(key=lambda x: str(x))
            if cfg.max_files is not None:
                files = files[: cfg.max_files]

            changed = 0
            skipped = 0
            timeline_paths: set[str] = set()
            entries_written = 0

            for fp in files:
                try:
                    content = fp.read_text(encoding="utf-8")
                except Exception:
                    content = fp.read_text(encoding="utf-8", errors="ignore")
                if len(content) < cfg.min_content_length:
                    skipped += 1
                    continue

                first_line = content.splitlines()[0].strip() if content else ""
                m = _DATE_RE.match(first_line)
                if not m:
                    skipped += 1
                    continue
                date_str = (m.group(1) or m.group(3) or "").replace(".", "-")
                character = (m.group(2) or m.group(4) or "").strip()
                character = character.strip()
                if not date_str or not character:
                    skipped += 1
                    continue

                normalized_path = fp.resolve().as_posix()
                h = _sha256_text(content)
                record = processed_db.get(normalized_path) if isinstance(processed_db, dict) else None
                if isinstance(record, dict) and record.get("hash") == h and record.get("status") == "summarized":
                    skipped += 1
                    continue

                summary, status = await _summarize(content, model=cfg.summary_model)
                if status == "skipped_sensitive":
                    processed_db[normalized_path] = {
                        **(record if isinstance(record, dict) else {}),
                        "hash": h,
                        "status": "skipped_sensitive",
                        "lastUpdated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "firstProcessed": (record or {}).get("firstProcessed") if isinstance(record, dict) else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                    skipped += 1
                    continue

                summary_text = summary or content.strip().splitlines()[-1][:200]

                timeline_file = cfg.timeline_dir / f"{_safe_name(character)}_timeline.json"
                timeline_data = _read_json(
                    timeline_file,
                    {"character": character, "lastUpdated": "", "version": "1.0.0", "entries": {}},
                )
                if not isinstance(timeline_data, dict):
                    timeline_data = {"character": character, "lastUpdated": "", "version": "1.0.0", "entries": {}}
                entries = timeline_data.get("entries")
                if not isinstance(entries, dict):
                    entries = {}
                    timeline_data["entries"] = entries
                day_list = entries.get(date_str)
                if not isinstance(day_list, list):
                    day_list = []
                    entries[date_str] = day_list
                if not any(isinstance(e, dict) and e.get("sourceHash") == h for e in day_list):
                    day_list.append(
                        {
                            "summary": summary_text,
                            "sourceHash": h,
                            "sourcePath": normalized_path,
                            "addedOn": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                    )
                    timeline_data["lastUpdated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    _write_json(timeline_file, timeline_data)
                    timeline_paths.add(str(timeline_file))
                    entries_written += 1

                    await store.upsert_texts(
                        "timeline",
                        [
                            {
                                "path": f"{_safe_name(character)}/{date_str}/{h}.txt",
                                "content": f"{date_str} {character}: {summary_text}\nsource: {normalized_path}",
                            }
                        ],
                    )

                processed_db[normalized_path] = {
                    **(record if isinstance(record, dict) else {}),
                    "hash": h,
                    "status": status,
                    "lastUpdated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "firstProcessed": (record or {}).get("firstProcessed") if isinstance(record, dict) else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                changed += 1

            _write_json(processed_db_path, processed_db)
            return {
                "ok": True,
                "status": "done",
                "changed": changed,
                "skipped": skipped,
                "entries_written": entries_written,
                "timeline_files": sorted(timeline_paths),
                "elapsed_ms": _now_ms() - start,
            }
        finally:
            lock.release()

