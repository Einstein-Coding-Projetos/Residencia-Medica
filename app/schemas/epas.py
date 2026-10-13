
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class ProgressoEPAUpdate(BaseModel):
    residente_id: uuid.UUID
    epa_id: uuid.UUID
    nivel_atual: int = Field(ge=1, le=5)


class ItemMapaEPA(BaseModel):
    epa_id: uuid.UUID
    codigo: str
    titulo: str
    nivel_esperado: int
    nivel_atual: int
    dentro_do_esperado: bool
