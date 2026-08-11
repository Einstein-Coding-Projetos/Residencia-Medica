"""Contratos de entrada e saída das rotas de autenticação."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models import Papel


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=200)


class UsuarioPublico(BaseModel):
    """O que o front pode ver sobre o usuário. Sem hash, nunca."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    email: EmailStr
    papel: Papel
    programa_id: uuid.UUID | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: int  # segundos
    usuario: UsuarioPublico


class ProgramaCreate(BaseModel):
    nome: str = Field(min_length=3, max_length=180)
    especialidade: str = Field(min_length=3, max_length=120)
    instituicao: str = Field(min_length=3, max_length=180)
    duracao_anos: int = Field(ge=1, le=10, default=5)


class ProgramaPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    especialidade: str
    instituicao: str
    duracao_anos: int
    ativo: bool
