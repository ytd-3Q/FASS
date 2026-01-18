from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="config.env", extra="ignore")

    api_key: str | None = None
    audit_log_key: str | None = None

    fs_store_enabled: bool = True
    fs_store_dir: str = str((Path(__file__).resolve().parents[2] / "data" / "fs_store").resolve())

    embedding_provider: str = "local"
    embedding_model_path: str = str((Path(__file__).resolve().parents[2] / "assets" / "models" / "embeddinggemma-300m").resolve())
    embedding_model: str = "default"

    llm_provider: str = "openai_compat"
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "default"
    llm_api_key: str | None = None

    newapi_base_url: str | None = None
    newapi_api_key: str | None = None
    newapi_timeout_seconds: float = 60.0

    local_test_api_key: str | None = None
    allow_all_cors: bool = False
    cors_allowed_origins: str | None = None

    ollama_base_url: str = "http://localhost:11434"


settings = Settings()

