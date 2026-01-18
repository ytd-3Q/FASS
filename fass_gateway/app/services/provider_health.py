from __future__ import annotations

import time

import httpx

from ..models.control import Provider
from .provider_registry import registry
from .provider_router import _resolve_url as resolve_url
from .provider_router import _headers_for_provider as headers_for_provider


def _now_ms() -> int:
    return int(time.time() * 1000)


class ProviderHealthMonitor:
    def __init__(self) -> None:
        self._last_run_ms = 0
        self.interval_ms = 30_000

    async def tick(self) -> None:
        now = _now_ms()
        if self._last_run_ms and now - self._last_run_ms < self.interval_ms:
            return
        self._last_run_ms = now

        providers = registry.list_enabled()
        for p in providers:
            await self._check_one(p)

    async def _check_one(self, p: Provider) -> None:
        start = time.time()
        err: str | None = None
        status = "down"
        try:
            async with httpx.AsyncClient(timeout=min(10.0, float(p.timeout_seconds or 60.0))) as client:
                headers = headers_for_provider(p)
                resp = await client.get(resolve_url(p.base_url, "/v1/models"), headers=headers)
                if resp.status_code == 404:
                    tags = await client.get(resolve_url(p.base_url, "/api/tags"), headers=headers)
                    tags.raise_for_status()
                else:
                    resp.raise_for_status()
            status = "up"
        except Exception as e:
            err = f"{type(e).__name__}"
            status = "down"
        latency_ms = int((time.time() - start) * 1000)
        registry.set_health(p.id, status=status, latency_ms=latency_ms, error=err)


monitor = ProviderHealthMonitor()

