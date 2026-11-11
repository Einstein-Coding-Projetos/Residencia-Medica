from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SomenteAdministrador, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.db.models import Servico
from app.db.session import get_db
from app.schemas.cadastros import ServicoCreate, ServicoPublico

router = APIRouter(prefix="/servicos", tags=["serviços"])


@router.post(
    "",
    response_model=ServicoPublico,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar serviço (somente administrador)",
)
def cadastrar_servico(
    dados: ServicoCreate,
    admin: SomenteAdministrador,
    db: Annotated[Session, Depends(get_db)],
) -> ServicoPublico:
    servico = Servico(**dados.model_dump())
    db.add(servico)
    db.flush()
    registrar_auditoria(
        db,
        acao="servico.criado",
        usuario_id=admin.id,
        entidade="servicos",
        entidade_id=servico.id,
        detalhe={"nome": servico.nome},
    )
    db.commit()
    return ServicoPublico.model_validate(servico)


@router.get("", response_model=list[ServicoPublico], summary="Listar serviços")
def listar_servicos(
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
) -> list[ServicoPublico]:
    servicos = db.scalars(select(Servico).where(Servico.ativo.is_(True))).all()
    return [ServicoPublico.model_validate(s) for s in servicos]