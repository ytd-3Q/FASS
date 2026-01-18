from __future__ import annotations

import time
from typing import Any

import httpx

from ..models.control import Provider
from .provider_registry import registry
from .model_registry import model_registry


def _now_ms() -> int:
    return int(time.time() * 1000)


def _normalize_base(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def _resolve_url(base_url: str, path: str) -> str:
    base = _normalize_base(base_url)
    if not path.startswith("/"):
        path = "/" + path
    if base.endswith("/v1") and path.startswith("/v1/"):
        return base + path[len("/v1") :]
    return base + path


def _headers_for_provider(p: Provider) -> dict[str, str]:
    headers: dict[str, str] = {}
    auth = p.auth
    if auth.type == "bearer" and auth.token:
        headers["Authorization"] = f"Bearer {auth.token}"
    elif auth.type == "header" and auth.header_name and auth.token:
        headers[str(auth.header_name)] = str(auth.token)
    for k, v in (p.extra_headers or {}).items():
        if isinstance(k, str) and isinstance(v, str) and k and v:
            headers[k] = v
    return headers


def _should_fallback(status_code: int) -> bool:
    return status_code in (408, 409, 425, 429, 500, 502, 503, 504)


def _candidate_order(primary: Provider | None) -> list[Provider]:
    enabled = registry.list_enabled()
    if primary is None:
        return enabled
    out = [primary]
    for p in enabled:
        if p.id != primary.id:
            out.append(p)
    return out


def _candidates_for_model(model: Any) -> list[tuple[Provider, str | None]]:
    provider_id, upstream_model = _parse_model_selector(model)
    if provider_id:
        p = registry.get_provider(provider_id)
        primary = p if p and p.enabled else None
        return [(x, upstream_model) for x in _candidate_order(primary)]

    if isinstance(upstream_model, str) and upstream_model:
        alias = model_registry.get_alias(upstream_model)
        if alias and alias.enabled and alias.priority:
            out: list[tuple[Provider, str | None]] = []
            for c in alias.priority:
                p = registry.get_provider(c.provider_id)
                if p and p.enabled:
                    out.append((p, c.upstream_model))
            if out:
                return out

    primary = _default_primary_provider()
    return [(x, upstream_model) for x in _candidate_order(primary)]


def _parse_model_selector(model: Any) -> tuple[str | None, str | None]:
    if not isinstance(model, str) or not model.strip():
        return None, None
    s = model.strip()
    if "::" in s:
        left, right = s.split("::", 1)
        left = left.strip()
        right = right.strip()
        if left and right:
            return left, right
    return None, s


def _default_primary_provider() -> Provider | None:
    cfg = registry.get()
    if cfg.default_provider_id:
        p = registry.get_provider(cfg.default_provider_id)
        if p and p.enabled:
            return p
    enabled = registry.list_enabled()
    return enabled[0] if enabled else None


async def proxy_models() -> dict:
    primary = _default_primary_provider()
    if not primary:
        return {"object": "list", "data": []}
    return await proxy_models_for_provider(primary)


async def proxy_models_for_provider(provider: Provider) -> dict:
    async with httpx.AsyncClient(timeout=provider.timeout_seconds) as client:
        headers = _headers_for_provider(provider)
        resp = await client.get(_resolve_url(provider.base_url, "/v1/models"), headers=headers)
        if resp.status_code == 404:
            tags = await client.get(_resolve_url(provider.base_url, "/api/tags"), headers=headers)
            tags.raise_for_status()
            data = tags.json() or {}
            models = [{"id": m.get("name"), "object": "model"} for m in (data.get("models") or []) if m.get("name")]
            return {"object": "list", "data": models}
        resp.raise_for_status()
        return resp.json()


async def proxy_chat_completions(payload: dict) -> dict:
    now = _now_ms()
    last_err: str | None = None

    for p, upstream_model in _candidates_for_model(payload.get("model")):
        if not p.enabled:
            continue
        rt = registry.runtime(p.id)
        if rt.circuit.state == "open":
            opened_at = int(rt.circuit.opened_at_unix_ms or 0)
            if opened_at and now - opened_at < 30_000:
                continue
            rt.circuit.state = "half_open"

        req_payload = dict(payload)
        if upstream_model:
            req_payload["model"] = upstream_model
        headers = _headers_for_provider(p)
        try:
            async with httpx.AsyncClient(timeout=p.timeout_seconds) as client:
                resp = await client.post(_resolve_url(p.base_url, "/v1/chat/completions"), headers=headers, json=req_payload)
                if resp.status_code == 404:
                    ollama_payload = {
                        "model": req_payload.get("model") or "default",
                        "messages": req_payload.get("messages") or [],
                        "stream": False,
                    }
                    r2 = await client.post(_resolve_url(p.base_url, "/api/chat"), headers=headers, json=ollama_payload)
                    if r2.status_code >= 400 and _should_fallback(r2.status_code):
                        last_err = f"{p.id} /api/chat {r2.status_code}: {(r2.text or '')[:500]}"
                        _mark_failure(p.id)
                        continue
                    r2.raise_for_status()
                    _mark_success(p.id)
                    out = r2.json() or {}
                    msg = (out.get("message") or {}).get("content") or ""
                    return {
                        "id": out.get("id") or "ollama",
                        "object": "chat.completion",
                        "created": int(out.get("created_at", "0").split("T")[0].replace("-", "") or 0),
                        "model": out.get("model") or ollama_payload["model"],
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": msg}, "finish_reason": "stop"}],
                    }

                if resp.status_code >= 400 and _should_fallback(resp.status_code):
                    last_err = f"{p.id} /v1/chat/completions {resp.status_code}: {(resp.text or '')[:500]}"
                    _mark_failure(p.id)
                    continue
                resp.raise_for_status()
                _mark_success(p.id)
                return resp.json()
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_err = f"{p.id} network: {type(e).__name__}"
            _mark_failure(p.id)
            continue
        except Exception as e:
            last_err = f"{p.id} error: {type(e).__name__}"
            _mark_failure(p.id)
            continue

    raise RuntimeError(last_err or "no providers available")


def _mark_failure(provider_id: str) -> None:
    rt = registry.runtime(provider_id)
    rt.circuit.failures += 1
    rt.circuit.last_failure_at_unix_ms = _now_ms()
    if rt.circuit.failures >= 3:
        rt.circuit.state = "open"
        rt.circuit.opened_at_unix_ms = _now_ms()


def _mark_success(provider_id: str) -> None:
    rt = registry.runtime(provider_id)
    rt.circuit.failures = 0
    rt.circuit.state = "closed"
    rt.circuit.opened_at_unix_ms = None
