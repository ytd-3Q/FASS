from __future__ import annotations

import time
from dataclasses import dataclass

from pydantic import BaseModel, Field

from ..models.control import ControlConfig, Provider, ProviderRuntime
from ..settings import settings
from .control_store import get_model, set_model


def _now_ms() -> int:
    return int(time.time() * 1000)


class _PersistedProviders(BaseModel):
    schema_version: int = 1
    providers: list[Provider] = Field(default_factory=list)
    default_provider_id: str | None = None


@dataclass
class ProviderRegistry:
    _config: ControlConfig | None = None
    _runtime: dict[str, ProviderRuntime] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._runtime = {}

    def load(self) -> ControlConfig:
        persisted = get_model("control.providers", _PersistedProviders, default=_PersistedProviders())
        providers = list(persisted.providers)
        default_provider_id = persisted.default_provider_id

        if not providers:
            legacy = Provider(
                id="default",
                name="Default",
                type="openai_compat",
                base_url=settings.llm_base_url,
                enabled=True,
                auth={"type": "bearer", "token": settings.llm_api_key},
            )
            providers = [legacy]
            default_provider_id = "default"
            self.save(ControlConfig(schema_version=1, providers=providers, default_provider_id=default_provider_id))
        else:
            if default_provider_id and default_provider_id not in {p.id for p in providers}:
                default_provider_id = providers[0].id if providers else None

        cfg = ControlConfig(schema_version=1, providers=providers, default_provider_id=default_provider_id)
        self._config = cfg
        for p in cfg.providers:
            self._runtime.setdefault(p.id, ProviderRuntime())
        return cfg

    def save(self, cfg: ControlConfig) -> None:
        out = _PersistedProviders(schema_version=cfg.schema_version, providers=cfg.providers, default_provider_id=cfg.default_provider_id)
        set_model("control.providers", out)
        self._config = cfg
        for p in cfg.providers:
            self._runtime.setdefault(p.id, ProviderRuntime())

    def get(self) -> ControlConfig:
        if self._config is None:
            return self.load()
        return self._config

    def get_provider(self, provider_id: str) -> Provider | None:
        cfg = self.get()
        for p in cfg.providers:
            if p.id == provider_id:
                return p
        return None

    def list_enabled(self) -> list[Provider]:
        cfg = self.get()
        return [p for p in cfg.providers if p.enabled]

    def runtime(self, provider_id: str) -> ProviderRuntime:
        self.get()
        return self._runtime.setdefault(provider_id, ProviderRuntime())

    def set_health(self, provider_id: str, *, status: str, latency_ms: int | None, error: str | None) -> None:
        rt = self.runtime(provider_id)
        rt.health.status = status  # type: ignore[assignment]
        rt.health.latency_ms = latency_ms
        rt.health.checked_at_unix_ms = _now_ms()
        rt.health.last_error = error[:1000] if isinstance(error, str) else None


registry = ProviderRegistry()

