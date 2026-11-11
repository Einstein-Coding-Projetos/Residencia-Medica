"""Contratos dos cadastros da estrutura da residência: especialidade,
programa e serviço."""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class EspecialidadeCreate(BaseModel):
    nome: str = Field(min_length=3, max_length=120)


class EspecialidadePublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    ativo: bool


class ProgramaCreate(BaseModel):
    nome: str = Field(min_length=3, max_length=180)
    especialidade_id: uuid.UUID
    instituicao: str = Field(min_length=3, max_length=180)
    duracao_anos: int = Field(ge=1, le=10, default=5)


class ProgramaPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    especialidade_id: uuid.UUID
    instituicao: str
    duracao_anos: int
    ativo: bool


class ServicoCreate(BaseModel):
    nome: str = Field(min_length=3, max_length=120)
    programa_id: uuid.UUID


class ServicoPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    programa_id: uuid.UUID
    ativo: bool