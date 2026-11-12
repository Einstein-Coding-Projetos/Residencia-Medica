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

    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8080"]

    # Login institucional (SSO) via OpenID Connect — Microsoft Entra,
    # Google Workspace ou outro provedor OIDC. Desligado até a TI da
    # instituição registrar o app e fornecer os dados abaixo (ver README).
    SSO_HABILITADO: bool = False
    SSO_NOME_PROVEDOR: str = "conta institucional"
    # Base do provedor; o sistema lê {SSO_ISSUER}/.well-known/openid-configuration.
    # Ex.: https://login.microsoftonline.com/<tenant-id>/v2.0
    SSO_ISSUER: str = ""
    SSO_CLIENT_ID: str = ""
    SSO_CLIENT_SECRET: str = ""
    # Callback desta API, cadastrado igual no provedor.
    SSO_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/sso/callback"
    # Tela de login do frontend, para onde o callback devolve o usuário.
    SSO_URL_FRONTEND: str = "http://localhost:8080/login.html"
    SSO_ESCOPOS: str = "openid email profile"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()