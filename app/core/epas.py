
"""Integra o progresso das EPAs ao portfólio do residente."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.epa_service import _ano_residencia
from app.db.models import EPA, ProgressoEPA, Usuario


def progresso_do_residente(
    db: Session,
    residente_id: uuid.UUID,
) -> dict:

    residente = db.get(Usuario, residente_id)

    if residente is None or residente.programa_id is None:
        return {"ano_residente": None, "epas": []}

    ano = _ano_residencia(residente)

    epas = db.scalars(
        select(EPA)
        .where(EPA.programa_id == residente.programa_id)
        .where(EPA.ativo.is_(True))
        .order_by(EPA.codigo)
    ).all()

    progressos = {
        progresso.epa_id: progresso
        for progresso in db.scalars(
            select(ProgressoEPA).where(
                ProgressoEPA.residente_id == residente.id
            )
        ).all()
    }

    itens = []

    for epa in epas:
        progresso = progressos.get(epa.id)

        itens.append({
            "codigo": epa.codigo,
            "nome": epa.titulo,
            "niveis_esperados": {
                "R1": epa.nivel_r1,
                "R2": epa.nivel_r2,
                "R3": epa.nivel_r3,
            },
            "nivel_atual": (
                progresso.nivel_atual if progresso else None
            ),
            "atualizado_em": (
                progresso.atualizado_em if progresso else None
            ),
            "observacoes_trimestre": None,
        })

    return {
        "ano_residente": f"R{ano}",
        "epas": itens,
    }
