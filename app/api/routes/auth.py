"""Rotas de autenticação."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import UsuarioAtual
from app.core.auth_service import autenticar, normalizar_email, registrar_auditoria
from app.core.security import criar_access_token
from app.db.models import agora_utc
from app.db.session import get_db
from app.schemas.auth import LoginRequest, TokenResponse, UsuarioPublico

router = APIRouter(prefix="/auth", tags=["autenticação"])


@router.post("/login", response_model=TokenResponse, summary="Entrar no sistema")
def login(
    dados: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    ip = request.client.host if request.client else None
    usuario = autenticar(db, email=dados.email, senha=dados.senha)

    if usuario is None:
        registrar_auditoria(
            db,
            acao="login.negado",
            detalhe={"email_tentado": normalizar_email(dados.email)},
            ip_origem=ip,
        )
        db.commit()
        # Uma mensagem só para os dois casos. Se dissesse "email não
        # cadastrado", qualquer pessoa poderia descobrir quem trabalha aqui.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token, expira_em = criar_access_token(
        usuario_id=usuario.id,
        papel=usuario.papel.value,
        programa_id=usuario.programa_id,
    )

    usuario.ultimo_login_em = agora_utc()
    registrar_auditoria(
        db,
        acao="login.aceito",
        usuario_id=usuario.id,
        entidade="usuarios",
        entidade_id=usuario.id,
        detalhe={"papel": usuario.papel.value},
        ip_origem=ip,
    )
    db.commit()

    return TokenResponse(
        access_token=token,
        expira_em=expira_em,
        usuario=UsuarioPublico.model_validate(usuario),
    )


@router.get("/eu", response_model=UsuarioPublico, summary="Dados de quem está logado")
def eu(usuario: UsuarioAtual) -> UsuarioPublico:
    """O front chama isso ao abrir o app para saber se o crachá ainda vale."""
    return UsuarioPublico.model_validate(usuario)
