from __future__ import annotations

import enum
import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
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
    __tablename__ = "especialidades"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nome: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)

    programas: Mapped[list["Programa"]] = relationship(back_populates="especialidade")
    epas: Mapped[list["EPA"]] = relationship(back_populates="especialidade")


class Programa(Base):
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


class EPA(Base):
    """Atividade Profissional Confiável (Entrustable Professional Activity).

    O nível esperado varia por ano de residência (R1/R2/R3) — a mesma EPA
    se repete nos três anos, só muda o quanto de autonomia se espera do
    residente. Ver Ten Cate / Quadro 1 do currículo de referência.
    """

    __tablename__ = "epas"
    __table_args__ = (UniqueConstraint("especialidade_id", "numero", name="uq_epa_numero_especialidade"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    especialidade_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("especialidades.id"), nullable=False
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    nome: Mapped[str] = mapped_column(String(220), nullable=False)

    nivel_esperado_r1: Mapped[int] = mapped_column(Integer, nullable=False)
    nivel_esperado_r2: Mapped[int] = mapped_column(Integer, nullable=False)
    nivel_esperado_r3: Mapped[int] = mapped_column(Integer, nullable=False)

    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)

    especialidade: Mapped["Especialidade"] = relationship(back_populates="epas")


class ProgressoEPA(Base):
    """Nível atual de um residente numa EPA específica.

    Atualizado por um avaliador (preceptor/R4-R5) conforme observa o
    residente. Uma linha por par (residente, EPA) — o histórico de como
    se chegou ali fica na trilha de auditoria, não aqui.
    """

    __tablename__ = "progresso_epa"
    __table_args__ = (UniqueConstraint("residente_id", "epa_id", name="uq_progresso_residente_epa"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    residente_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("usuarios.id"), nullable=False)
    epa_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("epas.id"), nullable=False)

    nivel_atual: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc, onupdate=agora_utc)
    atualizado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("usuarios.id"), nullable=True)


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


class Avaliacao(Base):
    __tablename__ = "avaliacoes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    residente_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("usuarios.id"), nullable=False)
    avaliador_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("usuarios.id"), nullable=False)
    instrumento: Mapped[str] = mapped_column(String(50), nullable=False)
    itens: Mapped[str] = mapped_column(Text, nullable=False)
    observacoes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    etapa_cirurgica: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nota: Mapped[float] = mapped_column(nullable=False)
    confirmado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    faixa_rotulo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    declaracao_observacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash_integridade: Mapped[str | None] = mapped_column(String(64), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)