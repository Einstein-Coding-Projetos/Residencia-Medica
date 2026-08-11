"""Porteiro do sistema.

`usuario_atual` responde "quem é você?" — lê o crachá e confere se é válido.
`exigir_papeis` responde "você pode isso?" — confere se o papel permite a ação.

Toda rota protegida do sistema passa por aqui. Se você precisar de uma
regra nova de permissão, escreva ela neste arquivo em vez de espalhar
`if usuario.papel == ...` pelas rotas.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenInvalido, ler_access_token
from app.db.models import Papel, Usuario
from app.db.session import get_db

# auto_error=False para a gente controlar a mensagem de erro em português.
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
    """Lê o token do cabeçalho `Authorization: Bearer <token>` e devolve o usuário."""
    if credencial is None or not credencial.credentials:
        raise _nao_autenticado("Faça login para continuar.")

    try:
        dados = ler_access_token(credencial.credentials)
    except TokenInvalido:
        # Mensagem genérica de propósito: não contamos ao cliente se o token
        # expirou, foi adulterado ou está malformado.
        raise _nao_autenticado("Sessão inválida ou expirada. Entre novamente.") from None

    usuario = db.get(Usuario, dados.usuario_id)
    if usuario is None or not usuario.ativo:
        raise _nao_autenticado("Sessão inválida ou expirada. Entre novamente.")

    # O papel dentro do token é só uma cópia para o front desenhar a tela.
    # A fonte da verdade é o banco. Se o admin mudou o papel de alguém no
    # meio do dia, o crachá antigo para de valer na hora.
    if usuario.papel.value != dados.papel:
        raise _nao_autenticado("Seu perfil foi alterado. Entre novamente.")

    return usuario


UsuarioAtual = Annotated[Usuario, Depends(usuario_atual)]


def exigir_papeis(*papeis_permitidos: Papel):
    """Fábrica de dependência: libera a rota só para os papéis listados.

    Uso:
        @router.post("/programas", dependencies=[Depends(exigir_papeis(Papel.ADMINISTRADOR))])

    Não existe atalho de super-usuário aqui. `exigir_papeis(Papel.PRECEPTOR)`
    barra o administrador, e isso é intencional: administrador é gestão, não
    função clínica. Se um dia precisar liberar os dois, liste os dois
    explicitamente — assim a decisão fica escrita e revisável no código.
    """
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


# Atalhos prontos para as rotas dos próximos sprints.
SomenteAdministrador = Annotated[Usuario, Depends(exigir_papeis(Papel.ADMINISTRADOR))]
SomenteResidente = Annotated[Usuario, Depends(exigir_papeis(Papel.RESIDENTE))]
SomenteAvaliador = Annotated[
    Usuario,
    Depends(exigir_papeis(Papel.PRECEPTOR, Papel.AVALIADOR_INTERMEDIARIO)),
]
