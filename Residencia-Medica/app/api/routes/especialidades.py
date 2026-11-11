from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SomenteAdministrador, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.db.models import Especialidade
from app.db.session import get_db
from app.schemas.cadastros import EspecialidadeCreate, EspecialidadePublico

router = APIRouter(prefix="/especialidades", tags=["especialidades"])


@router.post(
    "",
    response_model=EspecialidadePublico,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar especialidade (somente administrador)",
)
def cadastrar_especialidade(
    dados: EspecialidadeCreate,
    admin: SomenteAdministrador,
    db: Annotated[Session, Depends(get_db)],
) -> EspecialidadePublico:
    especialidade = Especialidade(**dados.model_dump())
    db.add(especialidade)
    db.flush()
    registrar_auditoria(
        db,
        acao="especialidade.criada",
        usuario_id=admin.id,
        entidade="especialidades",
        entidade_id=especialidade.id,
        detalhe={"nome": especialidade.nome},
    )
    db.commit()
    return EspecialidadePublico.model_validate(especialidade)


@router.get("", response_model=list[EspecialidadePublico], summary="Listar especialidades")
def listar_especialidades(
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
) -> list[EspecialidadePublico]:
    especialidades = db.scalars(
        select(Especialidade).where(Especialidade.ativo.is_(True))
    ).all()
    return [EspecialidadePublico.model_validate(e) for e in especialidades]