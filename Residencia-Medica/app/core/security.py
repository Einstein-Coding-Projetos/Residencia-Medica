from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SENHA_MAX_BYTES = 72
SENHA_MIN_CHARS = 8

_HASH_DUMMY = pwd_context.hash("hash-descartavel-para-equalizar-tempo")


class SenhaInvalida(ValueError):
    pass


def validar_formato_senha(senha: str) -> None:
    if len(senha) < SENHA_MIN_CHARS:
        raise SenhaInvalida(f"A senha precisa ter ao menos {SENHA_MIN_CHARS} caracteres.")
    if len(senha.encode("utf-8")) > SENHA_MAX_BYTES:
        raise SenhaInvalida("A senha é longa demais. Use no máximo 72 caracteres.")


def gerar_hash_senha(senha: str) -> str:
    validar_formato_senha(senha)
    return pwd_context.hash(senha)


def verificar_senha(senha_plana: str, hash_armazenado: str) -> bool:
    try:
        return pwd_context.verify(senha_plana, hash_armazenado)
    except (ValueError, TypeError):
        return False


def queimar_tempo_de_verificacao() -> None:
    pwd_context.verify("qualquer-coisa", _HASH_DUMMY)


class TokenInvalido(Exception):
    pass


@dataclass(frozen=True)
class DadosToken:
    usuario_id: uuid.UUID
    papel: str
    programa_id: uuid.UUID | None
    jti: str
    expira_em: datetime


def criar_access_token(
    *,
    usuario_id: uuid.UUID,
    papel: str,
    programa_id: uuid.UUID | None = None,
    duracao: timedelta | None = None,
) -> tuple[str, int]:
    agora = datetime.now(timezone.utc)
    expira = agora + (duracao or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    payload = {
        "sub": str(usuario_id),
        "papel": papel,
        "programa_id": str(programa_id) if programa_id else None,
        "iat": int(agora.timestamp()),
        "exp": int(expira.timestamp()),
        "jti": uuid.uuid4().hex,
        "typ": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, int((expira - agora).total_seconds())


def ler_access_token(token: str) -> DadosToken:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except InvalidTokenError as exc:
        raise TokenInvalido(str(exc)) from exc

    if payload.get("typ") != "access":
        raise TokenInvalido("Tipo de token inesperado.")

    try:
        usuario_id = uuid.UUID(payload["sub"])
        papel = payload["papel"]
        programa_bruto = payload.get("programa_id")
        programa_id = uuid.UUID(programa_bruto) if programa_bruto else None
    except (KeyError, ValueError, TypeError) as exc:
        raise TokenInvalido("Payload do token incompleto.") from exc

    return DadosToken(
        usuario_id=usuario_id,
        papel=papel,
        programa_id=programa_id,
        jti=payload.get("jti", ""),
        expira_em=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
    )