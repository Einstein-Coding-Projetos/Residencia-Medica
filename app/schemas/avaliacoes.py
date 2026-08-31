from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ItemAvaliacao(BaseModel):
    """Um domínio preenchido da ficha.

    A escala NÃO é validada aqui: cada instrumento tem a sua (OSATS 1–5,
    Mini-CEX 1–9, NOTSS 1–4). A validação acontece em
    app.core.instrumentos.validar_itens, que conhece o instrumento.
    """

    dominio: str = Field(min_length=1, description="Código do domínio no instrumento")
    nota: int = Field(description="Nota atribuída, dentro da escala do instrumento")


class AvaliacaoCriar(BaseModel):
    residente_id: uuid.UUID
    instrumento: str = Field(min_length=1)
    itens: list[ItemAvaliacao] = Field(default_factory=list)
    observacoes: str = ""

    # Só usados quando instrumento == "zwisch" — ela não usa `itens`
    # (ver app.core.instrumentos.validar_zwisch).
    etapa_cirurgica: str | None = None
    nivel_autonomia: int | None = None


class ConfirmarAvaliacao(BaseModel):
    """Corpo da confirmação de envio (regra INT-04).

    O avaliador precisa declarar explicitamente que observou o residente
    pessoalmente. Sem isso o envio não é aceito.
    """

    confirmo_observacao_direta: bool = Field(
        description=(
            "Confirmo que observei este residente pessoalmente nesta "
            "atividade na data informada."
        )
    )


class AvaliacaoPublica(BaseModel):
    id: uuid.UUID
    residente_id: uuid.UUID
    avaliador_id: uuid.UUID
    instrumento: str
    instrumento_nome: str
    itens: list[dict]
    observacoes: str
    nota: float
    agregacao: str
    total_minimo: int
    total_maximo: int
    faixa_rotulo: str | None = None
    faixa_descricao: str | None = None
    etapa_cirurgica: str | None = None
    confirmado: bool
    hash_integridade: str | None = None
    declaracao_observacao: str | None = None
    confirmado_em: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SetqCriar(BaseModel):
    """SETQ Smart: o residente preenche sobre o preceptor (fluxo invertido)."""

    preceptor_id: uuid.UUID
    itens: list[ItemAvaliacao] = Field(min_length=1)
    observacoes: str = ""


class SetqResumoPublico(BaseModel):
    """Resumo agregado e anônimo — nunca carrega dado por residente."""

    preceptor_id: uuid.UUID
    total_respostas: int
    disponivel: bool
    media_por_dominio: dict[str, float] | None = None


class DominioPublico(BaseModel):
    codigo: str
    titulo: str
    descricao: str


class FaixaPublica(BaseModel):
    minimo: float
    maximo: float
    rotulo: str
    descricao: str


class InstrumentoPublico(BaseModel):
    """Metadados da ficha — o frontend monta o formulário a partir daqui."""

    codigo: str
    nome: str
    escala_min: int
    escala_max: int
    ancora_escala: dict[int, str]
    agregacao: str
    total_minimo: int
    total_maximo: int
    dominios_fixos: bool
    anonimo: bool
    dominios: list[DominioPublico]
    faixas: list[FaixaPublica]
    observacao_interna: str
