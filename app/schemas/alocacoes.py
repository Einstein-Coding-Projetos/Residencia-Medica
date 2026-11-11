from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, model_validator


class AlocacaoBase(BaseModel):
    usuario_id: uuid.UUID
    servico_id: uuid.UUID
    data_inicio: date
    data_fim: date

    @model_validator(mode="after")
    def validar_datas(self) -> "AlocacaoBase":
        if self.data_inicio > self.data_fim:
            raise ValueError("A data de início não pode ser posterior à data de fim.")
        return self


class AlocacaoCreate(AlocacaoBase):
    pass


class AlocacaoResponse(AlocacaoBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class AlertaAnomaliaPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    avaliacao_id: uuid.UUID | None = None
    avaliador_id: uuid.UUID
    tipo_alerta: str
    detalhes: dict | None = None
    criado_em: datetime
