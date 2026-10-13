"""Formato de resposta de GET /portfolio — espelha app.core.portfolio."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel


class ResidentePortfolio(BaseModel):
    id: uuid.UUID
    nome: str
    email: str
    programa: str | None = None
    especialidade: str | None = None
    instituicao: str | None = None
    ano_residencia: str | None = None


class ResumoPortfolio(BaseModel):
    total_avaliacoes: int
    instrumentos_utilizados: int
    procedimentos_validados: int
    procedimentos_pendentes: int
    epas_total: int
    epas_atingidas: int
    epas_comparavel: bool
    primeira_avaliacao: datetime | None = None
    ultima_avaliacao: datetime | None = None


class ProgressoEPAPublico(BaseModel):
    codigo: str
    nome: str
    especialidade: str | None = None
    niveis_esperados: dict[str, int]
    ano_residente: str | None = None
    nivel_esperado: int | None = None
    nivel_atual: int | None = None
    observacoes_trimestre: int | None = None
    minimo_trimestre: int | None = None
    regra_minimo: str | None = None
    atualizado_em: datetime | None = None
    situacao: str
    nivel_esperado_rotulo: str | None = None
    nivel_atual_rotulo: str | None = None


class EPAsPortfolio(BaseModel):
    niveis_do_sistema: bool
    ano_residente: str | None = None
    mensagem: str | None = None
    fonte: str
    niveis: dict[int, str]
    anos: list[str]
    total: int
    com_nivel: int
    atingidas: int
    abaixo: int
    comparavel: bool
    itens: list[ProgressoEPAPublico]


class PontoEvolucao(BaseModel):
    data: datetime
    nota: float


class FaixaContagem(BaseModel):
    rotulo: str
    texto: str | None = None
    minimo: float
    maximo: float
    quantidade: int


class MediaDominio(BaseModel):
    codigo: str
    titulo: str
    media: float | None = None


class InstrumentoPortfolio(BaseModel):
    codigo: str
    nome: str
    nome_completo: str
    agregacao: str
    escala_min: int
    escala_max: int
    total_minimo: int
    total_maximo: int
    quantidade: int
    media: float | None = None
    melhor: float
    ultima_nota: float
    ultima_faixa: str | None = None
    evolucao: list[PontoEvolucao]
    faixas: list[FaixaContagem]
    media_por_dominio: list[MediaDominio]


class EtapaZwisch(BaseModel):
    etapa: str
    nivel_atual: int
    nivel_texto: str | None = None
    melhor_nivel: int
    quantidade: int
    ultima_data: datetime
    historico: list[int]


class ContagemParticipacao(BaseModel):
    participacao: str
    texto: str
    quantidade: int


class ProcedimentoPorNome(BaseModel):
    nome: str
    total: int
    cirurgiao_principal: int
    primeiro_auxiliar: int
    segundo_auxiliar: int


class ProcedimentoValidado(BaseModel):
    id: uuid.UUID
    nome: str
    data_realizacao: date
    participacao: str
    participacao_texto: str
    observacoes: str


class ProcedimentosPortfolio(BaseModel):
    total_validados: int
    pendentes: int
    recusados: int
    por_participacao: list[ContagemParticipacao]
    por_nome: list[ProcedimentoPorNome]
    lista: list[ProcedimentoValidado]


class ItemAvaliado(BaseModel):
    dominio: str
    titulo: str
    nota: float


class AvaliacaoPortfolio(BaseModel):
    id: uuid.UUID
    instrumento: str
    instrumento_nome: str
    data: datetime
    avaliador_nome: str
    nota: float
    total_minimo: int
    total_maximo: int
    faixa_rotulo: str | None = None
    faixa_texto: str | None = None
    etapa_cirurgica: str | None = None
    observacoes: str
    itens: list[ItemAvaliado]
    hash_integridade: str | None = None


class PortfolioPublico(BaseModel):
    gerado_em: datetime
    residente: ResidentePortfolio
    resumo: ResumoPortfolio
    epas: EPAsPortfolio
    instrumentos: list[InstrumentoPortfolio]
    zwisch: list[EtapaZwisch]
    procedimentos: ProcedimentosPortfolio
    avaliacoes: list[AvaliacaoPortfolio]
