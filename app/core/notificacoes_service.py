"""Criação de notificações dentro do sistema (Sprint 4).

Só grava na sessão; quem chama faz o commit junto com o resto da operação.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Notificacao, Papel, Usuario


def notificar(
    db: Session,
    usuario_id: uuid.UUID,
    *,
    tipo: str,
    titulo: str,
    mensagem: str = "",
    referencia: dict | None = None,
) -> Notificacao:
    notificacao = Notificacao(
        usuario_id=usuario_id,
        tipo=tipo,
        titulo=titulo,
        mensagem=mensagem,
        referencia=referencia,
    )
    db.add(notificacao)
    return notificacao


def ids_administradores(db: Session) -> list[uuid.UUID]:
    return list(
        db.scalars(
            select(Usuario.id)
            .where(Usuario.papel == Papel.ADMINISTRADOR)
            .where(Usuario.ativo.is_(True))
        )
    )


def notificar_administradores(
    db: Session,
    *,
    tipo: str,
    titulo: str,
    mensagem: str = "",
    referencia: dict | None = None,
) -> list[Notificacao]:
    return [
        notificar(db, admin_id, tipo=tipo, titulo=titulo, mensagem=mensagem, referencia=referencia)
        for admin_id in ids_administradores(db)
    ]
