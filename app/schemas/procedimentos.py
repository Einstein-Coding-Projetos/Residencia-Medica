from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Participacao = Literal["cirurgiao_principal", "primeiro_auxiliar", "segundo_auxiliar"]

ROTULOS_PARTICIPACAO: dict[str, str] = {
    "cirurgiao_principal": "Cirurgião principal",
    "primeiro_auxiliar": "1º auxiliar",
    "segundo_auxiliar": "2º auxiliar",
}


class ProcedimentoCriar(BaseModel):
    nome: str = Field(min_length=2, max_length=200, description="Ex.: Colecistectomia videolaparoscópica")
    data_realizacao: date
    participacao: Participacao
    servico_id: uuid.UUID | None = None
    observacoes: str = Field(default="", max_length=2000)


class ProcedimentoDecidir(BaseModel):
    """Decisão do preceptor sobre um procedimento registrado pelo residente."""

    aprovado: bool
    motivo_recusa: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _motivo_obrigatorio_na_recusa(self):
        if not self.aprovado and not (self.motivo_recusa or "").strip():
            raise ValueError("Informe o motivo da recusa — o residente verá essa mensagem.")
        return self


class ProcedimentoPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    residente_id: uuid.UUID
    nome: str
    data_realizacao: date
    participacao: str
    servico_id: uuid.UUID | None = None
    observacoes: str
    status: str
    validador_id: uuid.UUID | None = None
    validado_em: datetime | None = None
    motivo_recusa: str | None = None
    hash_integridade: str | None = None
    criado_em: datetime | None = None
