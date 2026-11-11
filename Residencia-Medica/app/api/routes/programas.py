from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SomenteAdministrador, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.db.models import Programa
from app.db.session import get_db
from app.schemas.cadastros import ProgramaCreate, ProgramaPublico

router = APIRouter(prefix="/programas", tags=["programas"])


@router.post(
    "",
    response_model=ProgramaPublico,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar programa (somente administrador)",
)
def cadastrar_programa(
    dados: ProgramaCreate,
    admin: SomenteAdministrador,
    db: Annotated[Session, Depends(get_db)],
) -> ProgramaPublico:
    programa = Programa(**dados.model_dump())
    db.add(programa)
    db.flush()
    registrar_auditoria(
        db,
        acao="programa.criado",
        usuario_id=admin.id,
        entidade="programas",
        entidade_id=programa.id,
        detalhe={"nome": programa.nome},
    )
    db.commit()
    return ProgramaPublico.model_validate(programa)


@router.get("", response_model=list[ProgramaPublico], summary="Listar programas")
def listar_programas(
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
) -> list[ProgramaPublico]:
    programas = db.scalars(select(Programa).where(Programa.ativo.is_(True))).all()
    return [ProgramaPublico.model_validate(p) for p in programas]