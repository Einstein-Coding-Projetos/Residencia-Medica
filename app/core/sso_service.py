"""Login institucional (SSO) por OpenID Connect — fluxo authorization code.

Etapas (cada uma numa função, para os testes simularem o provedor):

1. `url_de_autorizacao`: monta o redirect para o provedor, com um `state`
   assinado (JWT com nonce e validade curta) — não precisa guardar sessão.
2. `ler_state`: no callback, confere a assinatura e a validade do state.
3. `trocar_codigo`: troca o `code` pelo token no endpoint do provedor.
4. `validar_id_token`: confere assinatura (JWKS do provedor), `iss`, `aud`,
   expiração e `nonce`.
5. `email_do_token`: extrai o e-mail (`email`, `preferred_username` ou `upn`).

O sistema NÃO cria conta automaticamente: o e-mail precisa pertencer a um
usuário já cadastrado e ativo — papéis e acesso continuam com o administrador.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from urllib.parse import urlencode

import httpx
import jwt

from app.core.config import settings

VALIDADE_STATE = timedelta(minutes=10)
# Só assinaturas assimétricas: nunca "none" nem HS* (o segredo HMAC seria o
# client secret, e um token forjado com ele passaria).
ALGORITMOS_SEGUROS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512")
FINALIDADE_STATE = "sso_state"


class ErroSSO(Exception):
    """Falha no login institucional; a mensagem vai para o usuário."""


def sso_configurado() -> bool:
    return bool(
        settings.SSO_HABILITADO
        and settings.SSO_ISSUER
        and settings.SSO_CLIENT_ID
        and settings.SSO_CLIENT_SECRET
    )


@lru_cache(maxsize=4)
def _discovery_em_cache(issuer: str) -> dict:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    resposta = httpx.get(url, timeout=10)
    resposta.raise_for_status()
    return resposta.json()


def obter_discovery() -> dict:
    try:
        return _discovery_em_cache(settings.SSO_ISSUER)
    except httpx.HTTPError as erro:
        raise ErroSSO("Não foi possível falar com o provedor de login institucional.") from erro


def _criar_state() -> tuple[str, str]:
    nonce = secrets.token_urlsafe(24)
    agora = datetime.now(timezone.utc)
    state = jwt.encode(
        {"fin": FINALIDADE_STATE, "nonce": nonce, "iat": agora, "exp": agora + VALIDADE_STATE},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return state, nonce


def ler_state(state: str) -> str:
    """Valida o state e devolve o nonce que deve vir no id_token."""
    try:
        dados = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ErroSSO("O login demorou demais. Tente entrar de novo.") from None
    except jwt.InvalidTokenError:
        raise ErroSSO("Retorno do login institucional inválido.") from None
    if dados.get("fin") != FINALIDADE_STATE or not dados.get("nonce"):
        raise ErroSSO("Retorno do login institucional inválido.")
    return dados["nonce"]


def url_de_autorizacao() -> str:
    discovery = obter_discovery()
    state, nonce = _criar_state()
    parametros = {
        "client_id": settings.SSO_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.SSO_REDIRECT_URI,
        "scope": settings.SSO_ESCOPOS,
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    return discovery["authorization_endpoint"] + "?" + urlencode(parametros)


def trocar_codigo(code: str) -> dict:
    discovery = obter_discovery()
    try:
        resposta = httpx.post(
            discovery["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.SSO_REDIRECT_URI,
                "client_id": settings.SSO_CLIENT_ID,
                "client_secret": settings.SSO_CLIENT_SECRET,
            },
            timeout=10,
        )
        resposta.raise_for_status()
    except httpx.HTTPError as erro:
        raise ErroSSO("O provedor recusou o login institucional.") from erro
    tokens = resposta.json()
    if "id_token" not in tokens:
        raise ErroSSO("O provedor não devolveu a identificação do usuário.")
    return tokens


def _chave_de_assinatura(id_token: str, jwks_uri: str):
    return jwt.PyJWKClient(jwks_uri).get_signing_key_from_jwt(id_token).key


def validar_id_token(id_token: str, nonce_esperado: str) -> dict:
    discovery = obter_discovery()
    try:
        chave = _chave_de_assinatura(id_token, discovery["jwks_uri"])
        dados = jwt.decode(
            id_token,
            chave,
            algorithms=[
                alg for alg in (discovery.get("id_token_signing_alg_values_supported") or ["RS256"])
                if alg in ALGORITMOS_SEGUROS
            ] or ["RS256"],
            audience=settings.SSO_CLIENT_ID,
            issuer=discovery["issuer"],
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except (jwt.InvalidTokenError, jwt.PyJWKClientError) as erro:
        raise ErroSSO("Não foi possível confirmar sua identidade no login institucional.") from erro
    if dados.get("nonce") != nonce_esperado:
        raise ErroSSO("Não foi possível confirmar sua identidade no login institucional.")
    return dados


def email_do_token(dados: dict) -> str:
    for campo in ("email", "preferred_username", "upn"):
        valor = dados.get(campo)
        if isinstance(valor, str) and "@" in valor:
            return valor
    raise ErroSSO("Sua conta institucional não informou um e-mail.")
