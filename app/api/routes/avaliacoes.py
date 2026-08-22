from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


Instrumento = Literal["zwisch", "setq_smart"]


class ItemAvaliacao(BaseModel):
    item: str = Field(min_length=1)
    nota: int = Field(ge=1, le=5)


class AvaliacaoCriar(BaseModel):
    residente_id: uuid.UUID
    instrumento: Instrumento
    itens: list[ItemAvaliacao] = Field(min_length=1)
    observacoes: str = ""


class AvaliacaoPublica(BaseModel):
    id: uuid.UUID
    residente_id: uuid.UUID
    avaliador_id: uuid.UUID
    instrumento: str
    itens: list[dict]
    observacoes: str
    nota: float
    confirmado: bool
    hash_integridade: str | None

    class Config:
        from_attributes = True

