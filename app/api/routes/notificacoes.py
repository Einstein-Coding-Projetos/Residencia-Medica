from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import UsuarioAtual
from app.db.models import Notificacao, agora_utc
from app.db.session import get_db
from app.schemas.governanca import NotificacaoPublica

router = APIRouter(prefix="/notificacoes", tags=["notificações"])


@router.get("", response_model=list[NotificacaoPublica], summary="Minhas notificações")
def listar_notificacoes(
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
    nao_lidas: bool = False,
):
    query = (
        select(Notificacao)
        .where(Notificacao.usuario_id == usuario.id)
        .order_by(Notificacao.criado_em.desc())
    )
    if nao_lidas:
        query = query.where(Notificacao.lida_em.is_(None))
    return list(db.scalars(query))


@router.post(
    "/{notificacao_id}/lida",
    response_model=NotificacaoPublica,
    summary="Marcar notificação como lida",
)
def marcar_lida(
    notificacao_id: uuid.UUID,
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
):
    notificacao = db.get(Notificacao, notificacao_id)
    if notificacao is None or notificacao.usuario_id != usuario.id:
        raise HTTPException(status_code=404, detail="Notificação não encontrada.")
    if notificacao.lida_em is None:
        notificacao.lida_em = agora_utc()
        db.commit()
        db.refresh(notificacao)
    return notificacao
