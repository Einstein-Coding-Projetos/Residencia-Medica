from __future__ import annotations

import enum
import hashlib
import json
import uuid
from datetime import date, datetime, timezone


from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)

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
    epas: Mapped[list["EPA"]] = relationship(back_populates="programa")
    
class EPA(Base):
    """Atividade Profissional Confiável vinculada a um programa de residência."""

    __tablename__ = "epas"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    codigo: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    titulo: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    programa_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("programas.id"),
        nullable=False,
    )

    nivel_r1: Mapped[int] = mapped_column(
        nullable=False,
    )

    nivel_r2: Mapped[int] = mapped_column(
        nullable=False,
    )

    nivel_r3: Mapped[int] = mapped_column(
        nullable=False,
    )

    ativo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=agora_utc,
    )

    programa: Mapped["Programa"] = relationship(
        back_populates="epas"
    )


class ProgressoEPA(Base):
    """Nível atual de um residente em cada EPA."""

    __tablename__ = "progresso_epa"

    __table_args__ = (
        UniqueConstraint(
            "residente_id",
            "epa_id",
            name="uq_progresso_residente_epa",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )

    residente_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False
    )

    epa_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("epas.id"), nullable=False
    )

    nivel_atual: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=agora_utc,
        onupdate=agora_utc,
    )

    atualizado_por: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=True
    )

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

    # Data real de início no programa (residentes). Usada para calcular o
    # ano de residência (R1/R2/R3) em app.core.epa_service._ano_residencia;
    # quando ausente (cadastros antigos), cai no fallback por criado_em.
    data_inicio_programa: Mapped[date | None] = mapped_column(Date, nullable=True)

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


class Avaliacao(Base):
    __tablename__ = "avaliacoes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    # Em todo instrumento, exceto SETQ Smart: residente_id é quem é avaliado,
    # avaliador_id é quem preenche. No SETQ o sentido inverte (residente
    # preenche sobre o preceptor) para reaproveitar a mesma tabela e o mesmo
    # mecanismo de hash/imutabilidade — ver app.api.routes.setq.
    residente_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("usuarios.id"),
        nullable=False,
    )

    avaliador_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("usuarios.id"),
        nullable=False,
    )

    instrumento: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    itens: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    observacoes: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    # Só usada quando instrumento == "zwisch": a Zwisch não soma domínios,
    # é um nível de autonomia por etapa cirúrgica (ver app.core.instrumentos).
    etapa_cirurgica: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    # EPA que esta avaliação documenta (opcional). Uma avaliação confirmada
    # com epa_id conta como uma "observação" para o mínimo trimestral da
    # EPA (ver app.core.epa_service.contar_observacoes_trimestre). SETQ
    # Smart nunca preenche isto — SetqCriar não tem o campo.
    epa_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("epas.id"),
        nullable=True,
    )

    # Data em que a atividade avaliada aconteceu (declarada pelo avaliador).
    # Usada na verificação de contexto (Sprint 4): avaliador e residente
    # precisam estar alocados no mesmo serviço nesta data. Nula só em
    # registros anteriores a esta coluna.
    data_atividade: Mapped[date | None] = mapped_column(Date, nullable=True)

    nota: Mapped[float] = mapped_column(
        nullable=False,
    )

    confirmado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    faixa_rotulo: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    declaracao_observacao: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    hash_integridade: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=agora_utc,
    )

    confirmado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class Procedimento(Base):
    """Procedimento realizado pelo residente (portfólio).

    Regra do documento do projeto: "trabalhos adicionados pelo residente
    precisam de validação de um profissional antes de contar na
    estatística". Fluxo:

        residente registra  ->  status "pendente"
        preceptor/R4-R5 do mesmo programa decide  ->  "validado" ou "recusado"

    A decisão é final: gera hash de integridade e trava o registro
    (mesmo mecanismo das avaliações). Só "validado" entra nas estatísticas
    do portfólio.
    """

    __tablename__ = "procedimentos"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)

    residente_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False, index=True
    )

    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    data_realizacao: Mapped[date] = mapped_column(Date, nullable=False)

    # "cirurgiao_principal" | "primeiro_auxiliar" | "segundo_auxiliar" —
    # valores validados em app.schemas.procedimentos.
    participacao: Mapped[str] = mapped_column(String(30), nullable=False)

    servico_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("servicos.id"), nullable=True
    )

    observacoes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # "pendente" | "validado" | "recusado"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pendente")

    validador_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=True
    )
    validado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    motivo_recusa: Mapped[str | None] = mapped_column(Text, nullable=True)

    # `confirmado` + `hash_integridade`: mesmos nomes da Avaliacao, para
    # reaproveitar confirmar_registro() e bloquear_se_confirmado().
    confirmado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hash_integridade: Mapped[str | None] = mapped_column(String(64), nullable=True)

    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)


class Alocacao(Base):
    """Período em que um usuário (residente ou avaliador) atua num serviço.

    Base da verificação de contexto: uma avaliação só é aceita se avaliador
    e residente estavam alocados no mesmo serviço na data da atividade
    (ver app.core.contexto_service).
    """

    __tablename__ = "alocacoes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    servico_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("servicos.id"), nullable=False
    )
    data_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    data_fim: Mapped[date] = mapped_column(Date, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=agora_utc)


class AlertaAnomalia(Base):
    """Alerta estatístico sobre o padrão de avaliação de um avaliador.

    Gerado em app.core.anomalias_service; só o administrador consulta.
    """

    __tablename__ = "alertas_anomalia"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    avaliacao_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("avaliacoes.id"), nullable=True
    )
    avaliador_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    tipo_alerta: Mapped[str] = mapped_column(String(100), nullable=False)
    detalhes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora_utc, nullable=False
    )


class Notificacao(Base):
    """Aviso dentro do sistema para um usuário (Sprint 4).

    Gerada por app.core.notificacoes_service: prazos de engajamento,
    escaladas, avaliações recebidas e discordâncias.
    """

    __tablename__ = "notificacoes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False, default="")
    referencia: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora_utc, nullable=False
    )


class AlertaEngajamento(Base):
    """Marco D15/D20/D25 já disparado para um par preceptor-residente no mês.

    Serve de trava para o job não repetir o mesmo alerta (ver
    app.core.engajamento_service). `competencia` é o 1º dia do mês.
    """

    __tablename__ = "alertas_engajamento"
    __table_args__ = (
        UniqueConstraint(
            "preceptor_id", "residente_id", "competencia", "marco",
            name="uq_alerta_engajamento",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    preceptor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    residente_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False
    )
    competencia: Mapped[date] = mapped_column(Date, nullable=False)
    marco: Mapped[str] = mapped_column(String(5), nullable=False)  # D15 | D20 | D25
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora_utc, nullable=False
    )


class OmissaoAvaliacao(Base):
    """Mês fechado sem avaliação do preceptor sobre um residente alocado com ele.

    É registro histórico (não se apaga). Enquanto não houver avaliação
    confirmada daquele mês, bloqueia a certificação do residente — ver
    app.core.engajamento_service.bloqueios_certificacao.
    """

    __tablename__ = "omissoes_avaliacao"
    __table_args__ = (
        UniqueConstraint(
            "preceptor_id", "residente_id", "competencia",
            name="uq_omissao_avaliacao",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    preceptor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    residente_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    competencia: Mapped[date] = mapped_column(Date, nullable=False)
    registrada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora_utc, nullable=False
    )


class Discordancia(Base):
    """Discordância formal do residente sobre uma avaliação recebida.

    Prazo de 7 dias a partir da confirmação. A avaliação original nunca é
    alterada: a discordância fica anexada a ela, com hash próprio. O
    avaliador responde uma única vez; a resposta também recebe hash.
    """

    __tablename__ = "discordancias"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    avaliacao_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("avaliacoes.id"), nullable=False, unique=True
    )
    residente_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    avaliador_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("usuarios.id"), nullable=False, index=True
    )
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    hash_integridade: Mapped[str] = mapped_column(String(64), nullable=False)
    criada_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=agora_utc, nullable=False
    )

    resposta: Mapped[str | None] = mapped_column(Text, nullable=True)
    hash_resposta: Mapped[str | None] = mapped_column(String(64), nullable=True)
    respondida_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
