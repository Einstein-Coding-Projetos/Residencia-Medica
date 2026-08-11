"""Configuração da aplicação.

Nada de segredo hardcoded no código. Tudo vem de variável de ambiente
(.env em dev, secret manager em produção). Ver .env.example.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Aplicação ---
    APP_NAME: str = "Residência Médica API"
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # --- Banco ---
    DATABASE_URL: str = "sqlite:///./dev.db"

    # --- Token (JWT) ---
    # Gere com: python -c "import secrets; print(secrets.token_urlsafe(64))"
    SECRET_KEY: str = "TROQUE-ISSO-ANTES-DE-SUBIR-QUALQUER-COISA"
    ALGORITHM: str = "HS256"
    # 8h cobre um plantão inteiro sem obrigar o preceptor a logar de novo
    # no meio de uma avaliação. Se a cliente pedir mais curto, muda aqui.
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 8 * 60

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
