from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SomenteAdministrador, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.db.models import Alocacao, Papel, Servico, Usuario
from app.db.session import get_db
from app.schemas.alocacoes import AlocacaoCreate, AlocacaoResponse

router = APIRouter(prefix="/alocacoes", tags=["alocações"])


@router.post(
    "",
    response_model=AlocacaoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar alocação de um usuário num serviço (somente administrador)",
)
def criar_alocacao(
    dados: AlocacaoCreate,
    request: Request,
    admin: SomenteAdministrador,
    db: Annotated[Session, Depends(get_db)],
):
    usuario = db.get(Usuario, dados.usuario_id)
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if usuario.papel == Papel.ADMINISTRADOR:
        raise HTTPException(
            status_code=400,
            detail="Administrador não tem função clínica e não é alocado em serviço.",
        )

    servico = db.get(Servico, dados.servico_id)
    if servico is None or not servico.ativo:
        raise HTTPException(status_code=404, detail="Serviço não encontrado.")

    alocacao = Alocacao(**dados.model_dump())
    db.add(alocacao)
    db.flush()

    registrar_auditoria(
        db,
        acao="alocacao.criada",
        usuario_id=admin.id,
        entidade="alocacoes",
        entidade_id=alocacao.id,
        detalhe={
            "usuario_id": str(usuario.id),
            "servico_id": str(servico.id),
            "data_inicio": dados.data_inicio.isoformat(),
            "data_fim": dados.data_fim.isoformat(),
        },
        ip_origem=request.client.host if request.client else None,
    )

    db.commit()
    db.refresh(alocacao)
    return alocacao


@router.get(
    "",
    response_model=list[AlocacaoResponse],
    summary="Listar alocações (administrador vê todas; demais, só as próprias)",
)
def listar_alocacoes(
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
    usuario_id: uuid.UUID | None = None,
):
    if usuario.papel != Papel.ADMINISTRADOR:
        if usuario_id is not None and usuario_id != usuario.id:
            raise HTTPException(
                status_code=403,
                detail="Você só pode consultar as suas próprias alocações.",
            )
        usuario_id = usuario.id

    query = select(Alocacao).order_by(Alocacao.data_inicio)
    if usuario_id is not None:
        query = query.where(Alocacao.usuario_id == usuario_id)

    return list(db.scalars(query))
