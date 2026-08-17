from __future__ import annotations

import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    gerar_hash_senha,
    queimar_tempo_de_verificacao,
    verificar_senha,
)
from app.db.models import LogAuditoria, Papel, Usuario, agora_utc


def normalizar_email(email: str) -> str:
    return unicodedata.normalize("NFKC", email).strip().lower()


def registrar_auditoria(
    db: Session,
    *,
    acao: str,
    usuario_id: uuid.UUID | None = None,
    entidade: str | None = None,
    entidade_id: uuid.UUID | None = None,
    detalhe: dict | None = None,
    ip_origem: str | None = None,
) -> LogAuditoria:
    payload = {
        "acao": acao,
        "usuario_id": usuario_id,
        "entidade": entidade,
        "entidade_id": entidade_id,
        "detalhe": detalhe or {},
        "ocorrido_em": agora_utc().isoformat(),
    }
    log = LogAuditoria(
        acao=acao,
        usuario_id=usuario_id,
        entidade=entidade,
        entidade_id=entidade_id,
        detalhe=str(detalhe or {}),
        ip_origem=ip_origem,
        hash_registro=LogAuditoria.calcular_hash(payload),
    )
    db.add(log)
    return log


def autenticar(db: Session, *, email: str, senha: str) -> Usuario | None:
    email_normalizado = normalizar_email(email)
    usuario = db.scalar(select(Usuario).where(Usuario.email == email_normalizado))

    if usuario is None:
        queimar_tempo_de_verificacao()
        return None

    if not verificar_senha(senha, usuario.senha_hash):
        return None

    if not usuario.ativo:
        return None

    return usuario


def criar_usuario(
    db: Session,
    *,
    nome: str,
    email: str,
    senha: str,
    papel: Papel,
    programa_id: uuid.UUID | None = None,
) -> Usuario:
    usuario = Usuario(
        nome=nome.strip(),
        email=normalizar_email(email),
        senha_hash=gerar_hash_senha(senha),
        papel=papel,
        programa_id=programa_id,
    )
    db.add(usuario)
    db.flush()
    registrar_auditoria(
        db,
        acao="usuario.criado",
        usuario_id=usuario.id,
        entidade="usuarios",
        entidade_id=usuario.id,
        detalhe={"papel": papel.value},
    )
    return usuario