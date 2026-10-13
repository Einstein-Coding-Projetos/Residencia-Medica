
"""Serviço de cálculo e atualização do progresso das EPAs."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EPA, ProgressoEPA, Usuario, agora_utc


def _ano_residencia(residente: Usuario) -> int:
    """Estimativa temporária até o cadastro ter o ano real."""
    anos_passados = agora_utc().year - residente.criado_em.year + 1
    return min(max(anos_passados, 1), 3)


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

        mapa.append({
            "epa_id": epa.id,
            "codigo": epa.codigo,
            "titulo": epa.titulo,
            "nivel_esperado": esperado,
            "nivel_atual": atual,
            "dentro_do_esperado": atual >= esperado,
        })

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
        progresso = ProgressoEPA(
            residente_id=residente_id,
            epa_id=epa_id,
        )
        db.add(progresso)

    progresso.nivel_atual = nivel_atual
    progresso.atualizado_por = atualizado_por

    db.flush()

    return progresso
