"""Verificação de contexto (pilar de governança do Sprint 4).

Uma avaliação só vale se avaliador e residente estavam de fato alocados no
mesmo serviço na data declarada da atividade. A fonte da verdade é a
tabela `alocacoes` (cadastrada pelo administrador).
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Alocacao


def servicos_do_usuario_em(db: Session, usuario_id: uuid.UUID, dia: date) -> set[uuid.UUID]:
    """Serviços em que o usuário estava alocado no dia (pode ser mais de um)."""
    return set(
        db.scalars(
            select(Alocacao.servico_id)
            .where(Alocacao.usuario_id == usuario_id)
            .where(Alocacao.data_inicio <= dia)
            .where(Alocacao.data_fim >= dia)
        )
    )


def servico_em_comum(
    db: Session,
    avaliador_id: uuid.UUID,
    residente_id: uuid.UUID,
    dia: date,
) -> uuid.UUID | None:
    """Retorna um serviço onde os dois estavam alocados no dia, ou None."""
    comuns = servicos_do_usuario_em(db, avaliador_id, dia) & servicos_do_usuario_em(
        db, residente_id, dia
    )
    return next(iter(sorted(comuns, key=str)), None)
