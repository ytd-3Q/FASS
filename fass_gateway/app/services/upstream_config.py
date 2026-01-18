from __future__ import annotations

from dataclasses import dataclass

from .control_store import get_json, set_json


@dataclass(frozen=True)
class NewApiConfig:
    base_url: str | None
    api_key: str | None


@dataclass(frozen=True)
class OllamaConfig:
    base_url: str | None
    api_key: str | None


@dataclass(frozen=True)
class UpstreamConfig:
    newapi: NewApiConfig
    ollama: OllamaConfig


def _str(v: object) -> str | None:
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def get_upstreams() -> UpstreamConfig:
    return UpstreamConfig(
        newapi=NewApiConfig(
            base_url=_str(get_json("upstream.newapi.base_url")),
            api_key=_str(get_json("upstream.newapi.api_key")),
        ),
        ollama=OllamaConfig(
            base_url=_str(get_json("upstream.ollama.base_url")) or "http://localhost:11434",
            api_key=_str(get_json("upstream.ollama.api_key")),
        ),
    )


def set_upstreams(*, newapi_base_url: str | None, newapi_api_key: str | None, ollama_base_url: str | None, ollama_api_key: str | None) -> UpstreamConfig:
    set_json("upstream.newapi.base_url", newapi_base_url.strip() if isinstance(newapi_base_url, str) and newapi_base_url.strip() else None)
    set_json("upstream.newapi.api_key", newapi_api_key.strip() if isinstance(newapi_api_key, str) and newapi_api_key.strip() else None)
    set_json("upstream.ollama.base_url", ollama_base_url.strip() if isinstance(ollama_base_url, str) and ollama_base_url.strip() else None)
    set_json("upstream.ollama.api_key", ollama_api_key.strip() if isinstance(ollama_api_key, str) and ollama_api_key.strip() else None)
    return get_upstreams()

