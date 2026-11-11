"""Cadastro de usuários pela própria API (além do seed.py, que é só
para dados fictícios de desenvolvimento)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import SomenteAdministrador
from app.core.auth_service import criar_usuario
from app.core.security import SenhaInvalida
from app.db.session import get_db
from app.schemas.auth import UsuarioCreate, UsuarioPublico

router = APIRouter(prefix="/usuarios", tags=["usuários"])


@router.post(
    "",
    response_model=UsuarioPublico,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar usuário (somente administrador)",
)
def cadastrar_usuario(
    dados: UsuarioCreate,
    admin: SomenteAdministrador,
    db: Annotated[Session, Depends(get_db)],
) -> UsuarioPublico:
    try:
        usuario = criar_usuario(
            db,
            nome=dados.nome,
            email=dados.email,
            senha=dados.senha,
            papel=dados.papel,
            programa_id=dados.programa_id,
        )
        db.commit()
    except SenhaInvalida as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe um usuário com este email.",
        ) from None

    return UsuarioPublico.model_validate(usuario)