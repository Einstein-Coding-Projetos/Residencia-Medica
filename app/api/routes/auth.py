from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import UsuarioAtual
from app.core.auth_service import autenticar, normalizar_email, registrar_auditoria
from app.core.config import settings
from app.core.security import criar_access_token
from app.core.sso_service import (
    ErroSSO,
    email_do_token,
    ler_state,
    sso_configurado,
    trocar_codigo,
    url_de_autorizacao,
    validar_id_token,
)
from app.db.models import Usuario, agora_utc
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
    return UsuarioPublico.model_validate(usuario)


# ---------------------------------------------------------------------------
# Login institucional (SSO / OpenID Connect)
# ---------------------------------------------------------------------------


def _voltar_ao_login(fragmento: str) -> RedirectResponse:
    # Token e erro vão no fragmento (#...): o navegador não envia o
    # fragmento a servidor nenhum, então ele não fica em logs de acesso.
    return RedirectResponse(f"{settings.SSO_URL_FRONTEND}#{fragmento}", status_code=302)


@router.get("/sso/config", summary="O login institucional está disponível?")
def sso_config() -> dict:
    return {"habilitado": sso_configurado(), "nome_provedor": settings.SSO_NOME_PROVEDOR}


@router.get("/sso/iniciar", summary="Começar o login institucional (redireciona ao provedor)")
def sso_iniciar():
    if not sso_configurado():
        raise HTTPException(status_code=404, detail="Login institucional não configurado.")
    try:
        return RedirectResponse(url_de_autorizacao(), status_code=302)
    except ErroSSO as erro:
        return _voltar_ao_login("sso_erro=" + quote(str(erro)))


@router.get("/sso/callback", summary="Retorno do provedor de login institucional")
def sso_callback(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if not sso_configurado():
        raise HTTPException(status_code=404, detail="Login institucional não configurado.")

    ip = request.client.host if request.client else None
    email = None
    try:
        if error:
            raise ErroSSO("O login institucional foi cancelado ou recusado.")
        if not code or not state:
            raise ErroSSO("Retorno do login institucional incompleto.")
        nonce = ler_state(state)
        tokens = trocar_codigo(code)
        dados = validar_id_token(tokens["id_token"], nonce)
        email = normalizar_email(email_do_token(dados))

        usuario = db.scalar(select(Usuario).where(Usuario.email == email))
        if usuario is None or not usuario.ativo:
            raise ErroSSO(
                "Sua conta institucional não está cadastrada no sistema. "
                "Procure a administração da residência."
            )
    except ErroSSO as erro:
        registrar_auditoria(
            db,
            acao="login.sso_negado",
            detalhe={"email_tentado": email, "motivo": str(erro)},
            ip_origem=ip,
        )
        db.commit()
        return _voltar_ao_login("sso_erro=" + quote(str(erro)))

    token, _ = criar_access_token(
        usuario_id=usuario.id,
        papel=usuario.papel.value,
        programa_id=usuario.programa_id,
    )
    usuario.ultimo_login_em = agora_utc()
    registrar_auditoria(
        db,
        acao="login.sso_aceito",
        usuario_id=usuario.id,
        entidade="usuarios",
        entidade_id=usuario.id,
        detalhe={"papel": usuario.papel.value, "provedor": settings.SSO_NOME_PROVEDOR},
        ip_origem=ip,
    )
    db.commit()
    return _voltar_ao_login("sso=" + quote(token))
