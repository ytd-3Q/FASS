from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from ..settings import settings
from ..services.timeline import TimelineBuildConfig, build_timeline


router = APIRouter(prefix="/api/timeline")


def _check_api_key(authorization: str | None) -> None:
    if not settings.api_key:
        return
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")


@router.post("/build")
async def build(request: Request, authorization: str | None = Header(default=None)) -> dict:
    _check_api_key(authorization)
    payload = await request.json()

    diary_root = payload.get("diary_root")
    project_base_path = payload.get("project_base_path")
    timeline_dir = payload.get("timeline_dir")
    summary_model = payload.get("summary_model")
    min_content_length = payload.get("min_content_length", 100)
    max_files = payload.get("max_files")
    wait_ms_if_busy = payload.get("wait_ms_if_busy", 0)

    if not isinstance(diary_root, str) or not diary_root:
        raise HTTPException(status_code=400, detail="diary_root is required")
    if not isinstance(project_base_path, str) or not project_base_path:
        raise HTTPException(status_code=400, detail="project_base_path is required")
    if timeline_dir is not None and not isinstance(timeline_dir, str):
        raise HTTPException(status_code=400, detail="timeline_dir must be a string or null")
    if summary_model is not None and not isinstance(summary_model, str):
        raise HTTPException(status_code=400, detail="summary_model must be a string or null")
    if not isinstance(min_content_length, int):
        raise HTTPException(status_code=400, detail="min_content_length must be an integer")
    if max_files is not None and not isinstance(max_files, int):
        raise HTTPException(status_code=400, detail="max_files must be an integer or null")
    if not isinstance(wait_ms_if_busy, int):
        raise HTTPException(status_code=400, detail="wait_ms_if_busy must be an integer")

    base = Path(project_base_path)
    out_dir = Path(timeline_dir) if timeline_dir else base / "timeline"
    cfg = TimelineBuildConfig(
        diary_root=Path(diary_root),
        project_base_path=base,
        timeline_dir=out_dir,
        summary_model=summary_model or settings.llm_model or "default",
        min_content_length=min_content_length,
        max_files=max_files,
    )
    return await build_timeline(cfg, wait_ms_if_busy=wait_ms_if_busy)

