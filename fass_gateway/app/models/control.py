from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ProviderType = Literal["openai_compat", "ollama"]
AuthType = Literal["none", "bearer", "header"]


class ProviderAuth(BaseModel):
    type: AuthType = "bearer"
    token: str | None = None
    header_name: str | None = None


class Provider(BaseModel):
    id: str
    name: str
    type: ProviderType = "openai_compat"
    base_url: str
    enabled: bool = True
    auth: ProviderAuth = Field(default_factory=ProviderAuth)
    extra_headers: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 60.0


HealthStatus = Literal["unknown", "up", "down", "degraded"]
CircuitStatus = Literal["closed", "open", "half_open"]


class ProviderHealth(BaseModel):
    status: HealthStatus = "unknown"
    latency_ms: int | None = None
    checked_at_unix_ms: int | None = None
    last_error: str | None = None


class CircuitBreakerState(BaseModel):
    state: CircuitStatus = "closed"
    failures: int = 0
    opened_at_unix_ms: int | None = None
    last_failure_at_unix_ms: int | None = None


class ProviderRuntime(BaseModel):
    health: ProviderHealth = Field(default_factory=ProviderHealth)
    circuit: CircuitBreakerState = Field(default_factory=CircuitBreakerState)


class ControlConfig(BaseModel):
    schema_version: int = 1
    providers: list[Provider] = Field(default_factory=list)
    default_provider_id: str | None = None


Capability = Literal["chat", "embeddings"]


class ModelCandidate(BaseModel):
    provider_id: str
    upstream_model: str


class ModelAlias(BaseModel):
    id: str
    enabled: bool = True
    capabilities: list[Capability] = Field(default_factory=list)
    priority: list[ModelCandidate] = Field(default_factory=list)


Tier = Literal["L1", "L2", "L3"]


class ModelProfile(BaseModel):
    id: str
    name: str
    tier: Tier
    model_alias_id: str
    system_prompt: str = ""
    params: dict = Field(default_factory=dict)
    tools_enabled: bool = True
    private_memory_enabled: bool = True
