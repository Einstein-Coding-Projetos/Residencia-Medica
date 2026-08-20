from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Residência Médica API"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    DATABASE_URL: str = "sqlite:///./dev.db"

    SECRET_KEY: str = "TROQUE-ISSO-ANTES-DE-SUBIR-QUALQUER-COISA"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 8 * 60

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()