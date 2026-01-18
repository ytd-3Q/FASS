from __future__ import annotations

from pydantic import BaseModel, Field

from ..models.control import ModelAlias, ModelProfile
from ..settings import settings
from .provider_registry import registry
from .control_store import get_model, set_model


class _PersistedAliases(BaseModel):
    schema_version: int = 1
    models: list[ModelAlias] = Field(default_factory=list)


class _PersistedProfiles(BaseModel):
    schema_version: int = 1
    profiles: list[ModelProfile] = Field(default_factory=list)
    default_profile_id: str | None = None


class ModelRegistry:
    def __init__(self) -> None:
        self._aliases: list[ModelAlias] | None = None
        self._profiles: list[ModelProfile] | None = None
        self._default_profile_id: str | None = None

    def load(self) -> None:
        a = get_model("control.models", _PersistedAliases, default=_PersistedAliases())
        p = get_model("control.profiles", _PersistedProfiles, default=_PersistedProfiles())
        aliases = list(a.models)
        profiles = list(p.profiles)
        default_profile_id = p.default_profile_id

        if not aliases:
            cfg = registry.get()
            provider_id = cfg.default_provider_id or "default"
            aliases = [
                ModelAlias(
                    id="default",
                    enabled=True,
                    capabilities=["chat", "embeddings"],
                    priority=[{"provider_id": provider_id, "upstream_model": settings.llm_model or "default"}],
                )
            ]
            self.save_aliases(aliases)

        if not profiles:
            profiles = [
                ModelProfile(
                    id="default",
                    name="默认模型",
                    tier="L2",
                    model_alias_id="default",
                    system_prompt="",
                    params={},
                    tools_enabled=True,
                    private_memory_enabled=True,
                )
            ]
            default_profile_id = "default"
            self.save_profiles(profiles, default_profile_id=default_profile_id)

        self._aliases = list(aliases)
        self._profiles = list(profiles)
        self._default_profile_id = default_profile_id

    def _ensure(self) -> None:
        if self._aliases is None or self._profiles is None:
            self.load()

    def list_aliases(self) -> list[ModelAlias]:
        self._ensure()
        return list(self._aliases or [])

    def get_alias(self, alias_id: str) -> ModelAlias | None:
        self._ensure()
        for a in self._aliases or []:
            if a.id == alias_id:
                return a
        return None

    def save_aliases(self, aliases: list[ModelAlias]) -> None:
        out = _PersistedAliases(schema_version=1, models=aliases)
        set_model("control.models", out)
        self._aliases = list(aliases)

    def list_profiles(self) -> list[ModelProfile]:
        self._ensure()
        return list(self._profiles or [])

    def get_profile(self, profile_id: str) -> ModelProfile | None:
        self._ensure()
        for p in self._profiles or []:
            if p.id == profile_id:
                return p
        return None

    def default_profile_id(self) -> str | None:
        self._ensure()
        return self._default_profile_id

    def save_profiles(self, profiles: list[ModelProfile], *, default_profile_id: str | None) -> None:
        out = _PersistedProfiles(schema_version=1, profiles=profiles, default_profile_id=default_profile_id)
        set_model("control.profiles", out)
        self._profiles = list(profiles)
        self._default_profile_id = default_profile_id


model_registry = ModelRegistry()
