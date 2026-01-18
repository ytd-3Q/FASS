from __future__ import annotations

from typing import Any

from .model_defaults import get_defaults
from .newapi_client import UpstreamError, chat_completions, list_models
from .upstream_config import get_upstreams


async def proxy_models() -> dict:
    cfg = get_upstreams()
    try:
        return await list_models(base_url=cfg.newapi.base_url, api_key=cfg.newapi.api_key)
    except UpstreamError as e:
        raise RuntimeError(f"{e.detail} (request_id={e.request_id})")


async def proxy_chat_completions(payload: dict[str, Any]) -> dict:
    p = dict(payload or {})
    defaults = get_defaults()
    if not p.get("model") and defaults.chat_model_id:
        p["model"] = defaults.chat_model_id
    cfg = get_upstreams()
    try:
        return await chat_completions(p, base_url=cfg.newapi.base_url, api_key=cfg.newapi.api_key)
    except UpstreamError as e:
        raise RuntimeError(f"{e.detail} (request_id={e.request_id})")

