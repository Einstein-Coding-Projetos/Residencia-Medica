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
    RESIDENTE = "residente"
    PRECEPTOR = "preceptor"
    AVALIADOR_INTERMEDIARIO = "avaliador_intermediario"
    ADMINISTRADOR = "administrador"


PAPEIS_AVALIADORES = frozenset({Papel.PRECEPTOR, Papel.AVALIADOR_INTERMEDIARIO})


class Especialidade(Base):
    """A área médica em si (ex.: Cirurgia Geral, Cirurgia de Cabeça e Pescoço).

    Separada de Programa porque a mesma especialidade pode existir em
    mais de um programa/instituição.
    """

    __tablename__ = "especialidades"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)

    programas: Mapped[list["Programa"]] = relationship(back_populates="especialidade")


class Programa(Base):
    """O 'onde': ex. Residência em Cirurgia Geral no Hospital X."""

    __tablename__ = "programas"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(180), nullable=False)
    especialidade_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("especialidades.id"), nullable=False
    )
    instituicao: Mapped[str] = mapped_column(String(180), nullable=False)
    duracao_anos: Mapped[int] = mapped_column(nullable=False, default=5)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)

    especialidade: Mapped["Especialidade"] = relationship(back_populates="programas")
    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="programa")
    servicos: Mapped[list["Servico"]] = relationship(back_populates="programa")


class Servico(Base):
    """O setor dentro do hospital (ex.: Enfermaria, Ambulatório, Centro
    Cirúrgico) onde o residente atua no dia a dia. Vinculado a um Programa."""

    __tablename__ = "servicos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    programa_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("programas.id"), nullable=False
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)

    programa: Mapped["Programa"] = relationship(back_populates="servicos")


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    papel: Mapped[Papel] = mapped_column(Enum(Papel, native_enum=False), nullable=False)

    programa_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("programas.id"), nullable=True
    )
    programa: Mapped[Programa | None] = relationship(back_populates="usuarios")

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)
    ultimo_login_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return f"<Usuario {self.email} ({self.papel.value})>"


class LogAuditoria(Base):
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