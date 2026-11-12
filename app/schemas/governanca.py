from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class NotificacaoPublica(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    titulo: str
    mensagem: str
    referencia: dict | None = None
    lida_em: datetime | None = None
    criado_em: datetime


class PendenciaEngajamento(BaseModel):
    preceptor_id: uuid.UUID
    preceptor_nome: str
    residente_id: uuid.UUID
    residente_nome: str
    competencia: date
    marcos_disparados: list[str]


class OmissaoPublica(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    preceptor_id: uuid.UUID
    residente_id: uuid.UUID
    competencia: date
    registrada_em: datetime
    ativa: bool = True


class StatusCertificacao(BaseModel):
    residente_id: uuid.UUID
    bloqueada: bool
    motivo: str | None = None
    omissoes: list[OmissaoPublica]


class DiscordanciaCriar(BaseModel):
    motivo: str = Field(min_length=20, max_length=5000)


class DiscordanciaResponder(BaseModel):
    resposta: str = Field(min_length=10, max_length=5000)


class DiscordanciaPublica(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    avaliacao_id: uuid.UUID
    residente_id: uuid.UUID
    avaliador_id: uuid.UUID
    motivo: str
    hash_integridade: str
    criada_em: datetime
    resposta: str | None = None
    hash_resposta: str | None = None
    respondida_em: datetime | None = None
    status: str
