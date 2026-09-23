from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class EPACreate(BaseModel):
    especialidade_id: uuid.UUID
    numero: int = Field(ge=1)
    nome: str = Field(min_length=3, max_length=220)
    nivel_esperado_r1: int = Field(ge=1, le=5)
    nivel_esperado_r2: int = Field(ge=1, le=5)
    nivel_esperado_r3: int = Field(ge=1, le=5)


class EPAPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    especialidade_id: uuid.UUID
    numero: int
    nome: str
    nivel_esperado_r1: int
    nivel_esperado_r2: int
    nivel_esperado_r3: int
    ativo: bool


class ProgressoEPAUpdate(BaseModel):
    residente_id: uuid.UUID
    epa_id: uuid.UUID
    nivel_atual: int = Field(ge=1, le=5)


class ItemMapaEPA(BaseModel):
    """Uma linha do mapa: uma EPA, o nível esperado no ano atual do
    residente, e o nível em que ele realmente está."""

    epa_id: uuid.UUID
    numero: int
    nome: str
    nivel_esperado: int
    nivel_atual: int
    dentro_do_esperado: bool