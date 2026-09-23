"""Cálculo do mapa de progresso de EPAs: nível esperado (conforme o ano
de residência) versus nível em que o residente realmente está.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EPA, ProgressoEPA, Usuario


def _ano_residencia(residente: Usuario) -> int:
    """Deriva o ano (1, 2 ou 3) a partir de quando o residente entrou no
    programa. Simplificação inicial: usa o ano corrente menos o ano de
    criação da conta. Isso deve ser revisto quando existir uma data de
    início de residência de verdade no cadastro."""
    anos_passados = (_hoje().year - residente.criado_em.year) + 1
    return min(max(anos_passados, 1), 3)


def _hoje():
    from app.db.models import agora_utc
    return agora_utc()


def _nivel_esperado(epa: EPA, ano: int) -> int:
    return {1: epa.nivel_esperado_r1, 2: epa.nivel_esperado_r2, 3: epa.nivel_esperado_r3}[ano]


def calcular_mapa_epas(db: Session, residente: Usuario) -> list[dict]:
    if residente.programa is None or residente.programa.especialidade_id is None:
        return []

    epas = db.scalars(
        select(EPA)
        .where(EPA.especialidade_id == residente.programa.especialidade_id)
        .where(EPA.ativo.is_(True))
        .order_by(EPA.numero)
    ).all()

    progressos = {
        p.epa_id: p.nivel_atual
        for p in db.scalars(
            select(ProgressoEPA).where(ProgressoEPA.residente_id == residente.id)
        ).all()
    }

    ano = _ano_residencia(residente)
    mapa = []
    for epa in epas:
        esperado = _nivel_esperado(epa, ano)
        atual = progressos.get(epa.id, 0)
        mapa.append(
            {
                "epa_id": epa.id,
                "numero": epa.numero,
                "nome": epa.nome,
                "nivel_esperado": esperado,
                "nivel_atual": atual,
                "dentro_do_esperado": atual >= esperado,
            }
        )
    return mapa


def atualizar_progresso(
    db: Session,
    *,
    residente_id: uuid.UUID,
    epa_id: uuid.UUID,
    nivel_atual: int,
    atualizado_por: uuid.UUID,
) -> ProgressoEPA:
    progresso = db.scalar(
        select(ProgressoEPA)
        .where(ProgressoEPA.residente_id == residente_id)
        .where(ProgressoEPA.epa_id == epa_id)
    )
    if progresso is None:
        progresso = ProgressoEPA(residente_id=residente_id, epa_id=epa_id)
        db.add(progresso)

    progresso.nivel_atual = nivel_atual
    progresso.atualizado_por = atualizado_por
    db.flush()
    return progresso