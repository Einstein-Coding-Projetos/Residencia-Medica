"""Modelos do Sprint 1: papéis, usuários, programas e trilha de auditoria."""
from __future__ import annotations

import enum
import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def agora_utc() -> datetime:
    return datetime.now(timezone.utc)


class Papel(str, enum.Enum):
    """Os 4 papéis do cronograma. A ordem aqui não implica hierarquia.

    ATENÇÃO — decisão de negócio já fechada no Sprint 1:
    ADMINISTRADOR é papel de gestão de usuários e sistema. Ele NÃO acumula
    função clínica. Administrador não avalia residente, não preenche ficha,
    não entra na matriz de "quem avalia quem". Qualquer verificação de
    permissão que trate admin como super-usuário quebra essa separação.
    """

    RESIDENTE = "residente"
    PRECEPTOR = "preceptor"
    AVALIADOR_INTERMEDIARIO = "avaliador_intermediario"  # R4/R5
    ADMINISTRADOR = "administrador"


# Quem pode aplicar ficha de avaliação. Usado pelas rotas do Sprint 2.
PAPEIS_AVALIADORES = frozenset({Papel.PRECEPTOR, Papel.AVALIADOR_INTERMEDIARIO})


class Programa(Base):
    __tablename__ = "programas"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(180), nullable=False)
    especialidade: Mapped[str] = mapped_column(String(120), nullable=False)
    instituicao: Mapped[str] = mapped_column(String(180), nullable=False)
    duracao_anos: Mapped[int] = mapped_column(nullable=False, default=5)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="programa")


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(180), nullable=False)
    # Guardado sempre em minúsculas — ver `normalizar_email` no serviço de auth.
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    papel: Mapped[Papel] = mapped_column(Enum(Papel, native_enum=False), nullable=False)

    programa_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("programas.id"), nullable=True
    )
    programa: Mapped[Programa | None] = relationship(back_populates="usuarios")

    # Desligamento não apaga o registro (dado é imutável). Só desativa,
    # e o token deixa de valer na próxima requisição.
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)
    ultimo_login_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Usuario {self.email} ({self.papel.value})>"


class LogAuditoria(Base):
    """Trilha de auditoria append-only.

    Cada linha carrega o SHA-256 do próprio conteúdo. Se alguém editar a
    linha no banco, o hash para de bater e a adulteração fica evidente.
    O encadeamento com o hash anterior (blockchain-like) fica pro Sprint 4,
    junto com os pilares de governança — aqui basta o hash por registro.
    """

    __tablename__ = "log_auditoria"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    ocorrido_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)
    acao: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    entidade: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entidade_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    detalhe: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    ip_origem: Mapped[str | None] = mapped_column(String(45), nullable=True)
    hash_registro: Mapped[str] = mapped_column(String(64), nullable=False)

    @staticmethod
    def calcular_hash(payload: dict) -> str:
        canonico = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonico.encode("utf-8")).hexdigest()
