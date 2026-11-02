
"""Serviço de cálculo e atualização do progresso das EPAs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.catalogo_epas import obter_epa
from app.core.instrumentos import SETQ_SMART
from app.db.models import EPA, Avaliacao, ProgressoEPA, Usuario, agora_utc

class SaltoInvalidoError(ValueError):
    """Erro levantado quando o salto de nível viola a regra de 30 dias."""
    pass

class ObservacoesInsuficientesError(ValueError):
    """Erro levantado quando falta observação no trimestre para avançar de nível."""
    pass

def _ano_residencia(residente: Usuario) -> int:
    """Ano de residência (R1=1, R2=2, R3=3), calculado a partir de
    `data_inicio_programa`. Quando ausente (cadastros antigos, antes deste
    campo existir), cai no fallback por `criado_em` — aproximação, não um
    fato clínico real."""
    inicio = residente.data_inicio_programa
    if inicio is None:
        anos_passados = agora_utc().year - residente.criado_em.year + 1
    else:
        anos_passados = (agora_utc().date() - inicio).days // 365 + 1
    return min(max(anos_passados, 1), 3)


def _inicio_trimestre(referencia: datetime) -> datetime:
    mes_trimestre = ((referencia.month - 1) // 3) * 3 + 1
    return referencia.replace(
        month=mes_trimestre, day=1, hour=0, minute=0, second=0, microsecond=0
    )


def contar_observacoes_trimestre(
    db: Session,
    *,
    residente_id: uuid.UUID,
    epa_id: uuid.UUID,
    referencia: datetime | None = None,
) -> int:
    """Conta quantas avaliações confirmadas, vinculadas a esta EPA, o
    residente recebeu no trimestre (calendário: jan-mar/abr-jun/jul-set/
    out-dez) que contém `referencia` (padrão: agora).

    SETQ Smart nunca conta — é o residente avaliando o preceptor, não uma
    observação clínica dele (e `SetqCriar` nem tem campo `epa_id`; o filtro
    aqui é só defensivo).
    """
    referencia = referencia or agora_utc()
    inicio = _inicio_trimestre(referencia)

    total = db.scalar(
        select(func.count())
        .select_from(Avaliacao)
        .where(Avaliacao.residente_id == residente_id)
        .where(Avaliacao.epa_id == epa_id)
        .where(Avaliacao.confirmado.is_(True))
        .where(Avaliacao.instrumento != SETQ_SMART.codigo)
        .where(Avaliacao.confirmado_em >= inicio)
    )
    return total or 0


def _nivel_esperado(epa: EPA, ano: int) -> int:
    return {
        1: epa.nivel_r1,
        2: epa.nivel_r2,
        3: epa.nivel_r3,
    }[ano]


def calcular_mapa_epas(
    db: Session,
    residente: Usuario,
) -> list[dict]:

    if residente.programa_id is None:
        return []

    epas = db.scalars(
        select(EPA)
        .where(EPA.programa_id == residente.programa_id)
        .where(EPA.ativo.is_(True))
        .order_by(EPA.codigo)
    ).all()

    progressos = {
        p.epa_id: p.nivel_atual
        for p in db.scalars(
            select(ProgressoEPA).where(
                ProgressoEPA.residente_id == residente.id
            )
        ).all()
    }

    ano = _ano_residencia(residente)
    mapa = []

    for epa in epas:
        esperado = _nivel_esperado(epa, ano)
        atual = progressos.get(epa.id, 0)

        catalogo = obter_epa(epa.codigo)
        minimo = catalogo.minimo_trimestre if catalogo else None

        mapa.append({
            "epa_id": epa.id,
            "codigo": epa.codigo,
            "titulo": epa.titulo,
            "nivel_esperado": esperado,
            "nivel_atual": atual,
            "dentro_do_esperado": atual >= esperado,
            "observacoes_trimestre": (
                contar_observacoes_trimestre(
                    db, residente_id=residente.id, epa_id=epa.id
                )
                if minimo is not None
                else None
            ),
            "minimo_trimestre": minimo,
        })

    return mapa

def atualizar_progresso(
    db: Session,
    *,
    residente_id: uuid.UUID,
    epa: EPA,
    nivel_atual: int,
    atualizado_por: uuid.UUID,
) -> ProgressoEPA:

    progresso = db.scalar(
        select(ProgressoEPA)
        .where(ProgressoEPA.residente_id == residente_id)
        .where(ProgressoEPA.epa_id == epa.id)
    )

    if progresso is None:
        # Primeira atribuição de nível nesta EPA para este residente — não
        # é "avanço" (não há nível anterior), então o gate de observações
        # mínimas e o bloqueio de salto não se aplicam aqui.
        progresso = ProgressoEPA(
            residente_id=residente_id,
            epa_id=epa.id,
        )
        db.add(progresso)
    else:
        if nivel_atual > progresso.nivel_atual:
            # REGRA SPRINT 3: mínimo de observações no trimestre antes de
            # avançar de nível. EPAs sem minimo_trimestre no catálogo (EPA
            # 11, EPA 16 — regra própria, documentada) ou não catalogadas
            # (ex.: uma EPA de CCP ainda sem o catálogo delas) pulam o
            # gate, não é bug.
            catalogo = obter_epa(epa.codigo)
            minimo = catalogo.minimo_trimestre if catalogo else None

            if minimo is not None:
                observadas = contar_observacoes_trimestre(
                    db, residente_id=residente_id, epa_id=epa.id
                )
                if observadas < minimo:
                    raise ObservacoesInsuficientesError(
                        f"Avanço bloqueado: {epa.codigo} exige {minimo} observações "
                        f"no trimestre para avançar de nível, mas o residente tem "
                        f"{observadas}."
                    )

        # REGRA SPRINT 3: Bloqueio de salto > 1 nível em < 30 dias
        diferenca_niveis = nivel_atual - progresso.nivel_atual

        if diferenca_niveis >= 2:
            # SQLite não preserva tzinfo em DateTime(timezone=True) — depois
            # de um round-trip real pelo banco (uma nova sessão por request,
            # o caso normal em produção), atualizado_em volta "naive".
            # Postgres não tem esse problema, mas o fallback é inofensivo lá.
            atualizado_em = progresso.atualizado_em
            if atualizado_em.tzinfo is None:
                atualizado_em = atualizado_em.replace(tzinfo=timezone.utc)

            dias_desde_atualizacao = (agora_utc() - atualizado_em).days

            if dias_desde_atualizacao < 30:
                raise SaltoInvalidoError(
                    f"Avanço bloqueado: não é permitido saltar {diferenca_niveis} níveis "
                    f"em apenas {dias_desde_atualizacao} dias (mínimo de 30 dias exigido)."
                )

    progresso.nivel_atual = nivel_atual
    progresso.atualizado_por = atualizado_por

    db.flush()

    return progresso
