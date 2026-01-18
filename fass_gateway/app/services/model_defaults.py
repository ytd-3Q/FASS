from __future__ import annotations

from dataclasses import dataclass

from .control_store import get_json, set_json


@dataclass(frozen=True)
class ModelDefaults:
    chat_model_id: str | None
    embedding_model_id: str | None


def get_defaults() -> ModelDefaults:
    chat = get_json("model.defaults.chat_model_id")
    emb = get_json("model.defaults.embedding_model_id")
    return ModelDefaults(
        chat_model_id=chat if isinstance(chat, str) and chat else None,
        embedding_model_id=emb if isinstance(emb, str) and emb else None,
    )


def set_defaults(*, chat_model_id: str | None, embedding_model_id: str | None) -> ModelDefaults:
    set_json("model.defaults.chat_model_id", chat_model_id)
    set_json("model.defaults.embedding_model_id", embedding_model_id)
    return get_defaults()

