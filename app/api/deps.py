from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenInvalido, ler_access_token
from app.db.models import Papel, Usuario
from app.db.session import get_db

esquema_bearer = HTTPBearer(auto_error=False, description="Cole o access_token do login")

CABECALHO_WWW = {"WWW-Authenticate": "Bearer"}


def _nao_autenticado(detalhe: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detalhe,
        headers=CABECALHO_WWW,
    )


def usuario_atual(
    credencial: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> Usuario:
    if credencial is None or not credencial.credentials:
        raise _nao_autenticado("Faça login para continuar.")

    try:
        dados = ler_access_token(credencial.credentials)
    except TokenInvalido:
        raise _nao_autenticado("Sessão inválida ou expirada. Entre novamente.") from None

    usuario = db.get(Usuario, dados.usuario_id)
    if usuario is None or not usuario.ativo:
        raise _nao_autenticado("Sessão inválida ou expirada. Entre novamente.")

    if usuario.papel.value != dados.papel:
        raise _nao_autenticado("Seu perfil foi alterado. Entre novamente.")

    return usuario


UsuarioAtual = Annotated[Usuario, Depends(usuario_atual)]


def exigir_papeis(*papeis_permitidos: Papel):
    if not papeis_permitidos:
        raise ValueError("exigir_papeis precisa de ao menos um papel.")

    permitidos = frozenset(papeis_permitidos)

    def verificar(usuario: UsuarioAtual) -> Usuario:
        if usuario.papel not in permitidos:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Seu perfil não tem permissão para esta ação.",
            )
        return usuario

    return verificar


SomenteAdministrador = Annotated[Usuario, Depends(exigir_papeis(Papel.ADMINISTRADOR))]
SomenteResidente = Annotated[Usuario, Depends(exigir_papeis(Papel.RESIDENTE))]
SomenteAvaliador = Annotated[
    Usuario,
    Depends(exigir_papeis(Papel.PRECEPTOR, Papel.AVALIADOR_INTERMEDIARIO)),
]