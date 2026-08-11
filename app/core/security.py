"""Criptografia de senha e emissão/leitura do access token.

Duas responsabilidades, isoladas de propósito do resto do sistema:

1. Senha  -> passlib/bcrypt. A senha em texto puro nunca é gravada,
   nunca é logada e nunca é comparada com `==`.
2. Token  -> JWT. É o "crachá digital": prova quem é a pessoa e qual o
   papel dela nas telas seguintes, sem pedir a senha de novo.

Nenhuma função aqui conhece FastAPI ou banco de dados. Isso deixa o
módulo testável isoladamente e reaproveitável nos próximos sprints.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext

from app.core.config import settings

# ---------------------------------------------------------------- senha ---

# bcrypt com custo padrão (12 rounds). `deprecated="auto"` permite trocar
# de algoritmo no futuro sem invalidar as senhas já cadastradas.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt ignora silenciosamente tudo depois do byte 72. Se aceitássemos
# senhas maiores, "senha_de_80_chars_A" e "senha_de_80_chars_B" logariam
# a mesma conta. Por isso rejeitamos na entrada em vez de truncar.
SENHA_MAX_BYTES = 72
SENHA_MIN_CHARS = 8

# Hash descartável usado para igualar o tempo de resposta quando o email
# não existe. Sem isso dá pra descobrir quais emails estão cadastrados só
# cronometrando a resposta do /login (enumeração de usuários — LGPD).
_HASH_DUMMY = pwd_context.hash("hash-descartavel-para-equalizar-tempo")


class SenhaInvalida(ValueError):
    """Senha fora das regras de formato (não é erro de autenticação)."""


def validar_formato_senha(senha: str) -> None:
    if len(senha) < SENHA_MIN_CHARS:
        raise SenhaInvalida(f"A senha precisa ter ao menos {SENHA_MIN_CHARS} caracteres.")
    if len(senha.encode("utf-8")) > SENHA_MAX_BYTES:
        raise SenhaInvalida("A senha é longa demais. Use no máximo 72 caracteres.")


def gerar_hash_senha(senha: str) -> str:
    """Transforma a senha em hash. Único ponto do sistema que faz isso."""
    validar_formato_senha(senha)
    return pwd_context.hash(senha)


def verificar_senha(senha_plana: str, hash_armazenado: str) -> bool:
    """Compara senha digitada com o hash guardado. Nunca levanta exceção."""
    try:
        return pwd_context.verify(senha_plana, hash_armazenado)
    except (ValueError, TypeError):
        # Hash corrompido ou em formato desconhecido: trata como senha errada.
        return False


def queimar_tempo_de_verificacao() -> None:
    """Roda um bcrypt de mentira quando o email não existe."""
    pwd_context.verify("qualquer-coisa", _HASH_DUMMY)


# ---------------------------------------------------------------- token ---


class TokenInvalido(Exception):
    """Token ausente, expirado, adulterado ou com payload incompleto."""


@dataclass(frozen=True)
class DadosToken:
    """Conteúdo já validado do crachá."""

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
    """Emite o crachá. Devolve (token, segundos_ate_expirar).

    O papel vai dentro do token só para o front decidir o que desenhar.
    A autorização de verdade sempre reconfere o papel no banco — ver
    `app/api/deps.py`.
    """
    agora = datetime.now(timezone.utc)
    expira = agora + (duracao or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))

    payload = {
        "sub": str(usuario_id),
        "papel": papel,
        "programa_id": str(programa_id) if programa_id else None,
        "iat": int(agora.timestamp()),
        "exp": int(expira.timestamp()),
        "jti": uuid.uuid4().hex,  # identificador único — base da revogação futura
        "typ": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return token, int((expira - agora).total_seconds())


def ler_access_token(token: str) -> DadosToken:
    """Valida assinatura e prazo do crachá e devolve o conteúdo."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            # Lista fixa e explícita. Se aceitássemos o algoritmo que vem
            # escrito no próprio token, dava pra mandar "alg": "none" e
            # entrar sem assinatura nenhuma.
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
