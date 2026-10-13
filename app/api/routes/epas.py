from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SomenteAdministrador, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.db.models import EPA
from app.db.session import get_db
from app.schemas.cadastros import EPACreate, EPAPublico


router = APIRouter(prefix="/epas", tags=["EPAs"])


@router.post(
    "",
    response_model=EPAPublico,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar EPA (somente administrador)",
)
def cadastrar_epa(
    dados: EPACreate,
    admin: SomenteAdministrador,
    db: Annotated[Session, Depends(get_db)],
) -> EPAPublico:

    epa = EPA(**dados.model_dump())

    db.add(epa)
    db.flush()

    registrar_auditoria(
        db,
        acao="epa.criada",
        usuario_id=admin.id,
        entidade="epas",
        entidade_id=epa.id,
        detalhe={
            "codigo": epa.codigo,
            "titulo": epa.titulo,
            "programa_id": str(epa.programa_id),
        },
    )

    db.commit()

    return EPAPublico.model_validate(epa)


@router.get(
    "",
    response_model=list[EPAPublico],
    summary="Listar EPAs",
)
def listar_epas(
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
) -> list[EPAPublico]:

    epas = db.scalars(
        select(EPA)
        .where(EPA.ativo.is_(True))
        .order_by(EPA.codigo)
    ).all()

    return [EPAPublico.model_validate(epa) for epa in epas]
