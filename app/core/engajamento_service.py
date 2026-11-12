"""Engajamento obrigatório do preceptor (Sprint 4).

Ciclo mensal. Um par preceptor-residente está "obrigado" no mês quando os
dois estiveram alocados no mesmo serviço, em períodos que se cruzam, em
algum dia do mês. O par fica "pendente" enquanto não houver avaliação
confirmada desse preceptor sobre esse residente com atividade no mês
(SETQ não conta).

Marcos, verificados pelo job diário `verificar_engajamento`:
- D15 e D20: alerta ao preceptor;
- D25: alerta ao preceptor e escalada aos administradores;
- mês fechado sem avaliação: registra OmissaoAvaliacao, que bloqueia a
  certificação do residente até existir uma avaliação daquele mês
  (lançamento tardio, com a data real da atividade).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.auth_service import registrar_auditoria
from app.core.notificacoes_service import notificar, notificar_administradores
from app.db.models import (
    AlertaEngajamento,
    Alocacao,
    Avaliacao,
    OmissaoAvaliacao,
    Papel,
    Usuario,
)

MARCOS = ((15, "D15"), (20, "D20"), (25, "D25"))
INSTRUMENTO_EXCLUIDO = "setq_smart"

Par = tuple[uuid.UUID, uuid.UUID]  # (preceptor_id, residente_id)


def competencia_de(dia: date) -> date:
    return dia.replace(day=1)


def fim_da_competencia(competencia: date) -> date:
    proximo = (competencia.replace(day=28) + timedelta(days=4)).replace(day=1)
    return proximo - timedelta(days=1)


def _rotulo_mes(competencia: date) -> str:
    return competencia.strftime("%m/%Y")


def pares_obrigados(db: Session, inicio: date, fim: date) -> set[Par]:
    """Pares preceptor-residente que dividiram serviço entre inicio e fim."""
    linhas = db.execute(
        select(Alocacao.servico_id, Alocacao.data_inicio, Alocacao.data_fim, Usuario.id, Usuario.papel)
        .join(Usuario, Usuario.id == Alocacao.usuario_id)
        .where(Usuario.ativo.is_(True))
        .where(Usuario.papel.in_([Papel.PRECEPTOR, Papel.RESIDENTE]))
        .where(Alocacao.data_inicio <= fim)
        .where(Alocacao.data_fim >= inicio)
    ).all()

    por_servico: dict[uuid.UUID, dict[Papel, list]] = {}
    for servico_id, ini, fi, usuario_id, papel in linhas:
        janela = (max(ini, inicio), min(fi, fim))
        por_servico.setdefault(servico_id, {}).setdefault(papel, []).append((usuario_id, janela))

    pares: set[Par] = set()
    for grupos in por_servico.values():
        for preceptor_id, (p_ini, p_fim) in grupos.get(Papel.PRECEPTOR, []):
            for residente_id, (r_ini, r_fim) in grupos.get(Papel.RESIDENTE, []):
                if p_ini <= r_fim and r_ini <= p_fim:
                    pares.add((preceptor_id, residente_id))
    return pares


def pares_avaliados(db: Session, inicio: date, fim: date) -> set[Par]:
    """Pares com avaliação confirmada cuja atividade caiu entre inicio e fim."""
    linhas = db.execute(
        select(Avaliacao.avaliador_id, Avaliacao.residente_id, Avaliacao.data_atividade, Avaliacao.confirmado_em)
        .where(Avaliacao.confirmado.is_(True))
        .where(Avaliacao.instrumento != INSTRUMENTO_EXCLUIDO)
        .where(
            or_(
                and_(Avaliacao.data_atividade >= inicio, Avaliacao.data_atividade <= fim),
                Avaliacao.data_atividade.is_(None),
            )
        )
    ).all()
    pares: set[Par] = set()
    for avaliador_id, residente_id, data_atividade, confirmado_em in linhas:
        dia = data_atividade or (confirmado_em.date() if confirmado_em else None)
        if dia is not None and inicio <= dia <= fim:
            pares.add((avaliador_id, residente_id))
    return pares


def pendencias_do_mes(db: Session, hoje: date, preceptor_id: uuid.UUID | None = None) -> list[Par]:
    competencia = competencia_de(hoje)
    pendentes = pares_obrigados(db, competencia, hoje) - pares_avaliados(
        db, competencia, fim_da_competencia(competencia)
    )
    if preceptor_id is not None:
        pendentes = {p for p in pendentes if p[0] == preceptor_id}
    return sorted(pendentes, key=lambda p: (str(p[0]), str(p[1])))


@dataclass
class ResultadoVerificacao:
    data: date
    alertas_criados: list[dict] = field(default_factory=list)
    escaladas: int = 0
    omissoes_registradas: list[dict] = field(default_factory=list)

    def como_dict(self) -> dict:
        return {
            "data": self.data.isoformat(),
            "alertas_criados": self.alertas_criados,
            "escaladas": self.escaladas,
            "omissoes_registradas": self.omissoes_registradas,
        }


def _nomes(db: Session, *ids: uuid.UUID) -> dict[uuid.UUID, str]:
    return dict(db.execute(select(Usuario.id, Usuario.nome).where(Usuario.id.in_(ids))).all())


def _processar_marcos(db: Session, hoje: date, resultado: ResultadoVerificacao) -> None:
    alcancados = [rotulo for dia, rotulo in MARCOS if hoje.day >= dia]
    if not alcancados:
        return

    competencia = competencia_de(hoje)
    for preceptor_id, residente_id in pendencias_do_mes(db, hoje):
        ja_disparados = set(
            db.scalars(
                select(AlertaEngajamento.marco)
                .where(AlertaEngajamento.preceptor_id == preceptor_id)
                .where(AlertaEngajamento.residente_id == residente_id)
                .where(AlertaEngajamento.competencia == competencia)
            )
        )
        novos = [m for m in alcancados if m not in ja_disparados]
        if not novos:
            continue

        for marco in novos:
            db.add(
                AlertaEngajamento(
                    preceptor_id=preceptor_id,
                    residente_id=residente_id,
                    competencia=competencia,
                    marco=marco,
                )
            )

        # Notifica só o marco mais avançado (se o job ficou dias sem rodar,
        # não despeja D15 e D20 de uma vez no preceptor).
        marco = novos[-1]
        nomes = _nomes(db, preceptor_id, residente_id)
        referencia = {
            "preceptor_id": str(preceptor_id),
            "residente_id": str(residente_id),
            "competencia": competencia.isoformat(),
            "marco": marco,
        }
        notificar(
            db,
            preceptor_id,
            tipo=f"engajamento_{marco.lower()}",
            titulo=f"{marco}: avaliação pendente de {nomes.get(residente_id, 'residente')}",
            mensagem=(
                f"Você ainda não registrou avaliação de {nomes.get(residente_id, 'residente')} "
                f"em {_rotulo_mes(competencia)}. Se o mês fechar sem avaliação, a "
                "certificação do residente fica bloqueada."
            ),
            referencia=referencia,
        )
        resultado.alertas_criados.append(referencia)

        if "D25" in novos:
            notificar_administradores(
                db,
                tipo="engajamento_escalada",
                titulo=(
                    f"Escalada D25: {nomes.get(preceptor_id, 'preceptor')} sem avaliar "
                    f"{nomes.get(residente_id, 'residente')}"
                ),
                mensagem=(
                    f"Chegou o dia 25 de {_rotulo_mes(competencia)} sem avaliação. "
                    "O preceptor já foi alertado nos dias 15 e 20."
                ),
                referencia=referencia,
            )
            resultado.escaladas += 1
            registrar_auditoria(
                db,
                acao="engajamento.escalada_d25",
                usuario_id=None,
                entidade="usuarios",
                entidade_id=preceptor_id,
                detalhe=referencia,
            )


def _fechar_mes_anterior(db: Session, hoje: date, resultado: ResultadoVerificacao) -> None:
    fim = competencia_de(hoje) - timedelta(days=1)
    competencia = competencia_de(fim)
    pendentes = pares_obrigados(db, competencia, fim) - pares_avaliados(db, competencia, fim)

    for preceptor_id, residente_id in sorted(pendentes, key=lambda p: (str(p[0]), str(p[1]))):
        existe = db.scalar(
            select(OmissaoAvaliacao.id)
            .where(OmissaoAvaliacao.preceptor_id == preceptor_id)
            .where(OmissaoAvaliacao.residente_id == residente_id)
            .where(OmissaoAvaliacao.competencia == competencia)
        )
        if existe:
            continue

        omissao = OmissaoAvaliacao(
            preceptor_id=preceptor_id, residente_id=residente_id, competencia=competencia
        )
        db.add(omissao)
        db.flush()

        nomes = _nomes(db, preceptor_id, residente_id)
        referencia = {
            "omissao_id": str(omissao.id),
            "preceptor_id": str(preceptor_id),
            "residente_id": str(residente_id),
            "competencia": competencia.isoformat(),
        }
        texto = (
            f"{nomes.get(preceptor_id, 'Preceptor')} não avaliou "
            f"{nomes.get(residente_id, 'residente')} em {_rotulo_mes(competencia)}. "
            "A certificação do residente fica bloqueada até o lançamento da "
            "avaliação daquele mês."
        )
        notificar(db, preceptor_id, tipo="engajamento_omissao", titulo="Mês fechado sem avaliação", mensagem=texto, referencia=referencia)
        notificar_administradores(db, tipo="engajamento_omissao", titulo="Omissão de avaliação registrada", mensagem=texto, referencia=referencia)
        registrar_auditoria(
            db,
            acao="engajamento.omissao_registrada",
            usuario_id=None,
            entidade="omissoes_avaliacao",
            entidade_id=omissao.id,
            detalhe=referencia,
        )
        resultado.omissoes_registradas.append(referencia)


def verificar_engajamento(db: Session, hoje: date | None = None) -> ResultadoVerificacao:
    """Job diário. Idempotente: rodar duas vezes no mesmo dia não duplica nada."""
    hoje = hoje or date.today()
    resultado = ResultadoVerificacao(data=hoje)
    _fechar_mes_anterior(db, hoje, resultado)
    _processar_marcos(db, hoje, resultado)
    db.flush()
    return resultado


def bloqueios_certificacao(db: Session, residente_id: uuid.UUID) -> list[OmissaoAvaliacao]:
    """Omissões do residente que ainda não foram supridas por avaliação tardia."""
    ativas = []
    for omissao in db.scalars(
        select(OmissaoAvaliacao)
        .where(OmissaoAvaliacao.residente_id == residente_id)
        .order_by(OmissaoAvaliacao.competencia)
    ):
        fim = fim_da_competencia(omissao.competencia)
        if (omissao.preceptor_id, residente_id) not in pares_avaliados(db, omissao.competencia, fim):
            ativas.append(omissao)
    return ativas


def status_certificacao(db: Session, residente_id: uuid.UUID) -> dict:
    """Resumo usado pela rota de certificação, pelo painel e pelo portfólio."""
    ativas = bloqueios_certificacao(db, residente_id)
    meses = ", ".join(o.competencia.strftime("%m/%Y") for o in ativas)
    return {
        "residente_id": residente_id,
        "bloqueada": bool(ativas),
        "motivo": f"Meses sem avaliação obrigatória: {meses}." if ativas else None,
        "omissoes": [
            {
                "id": o.id,
                "preceptor_id": o.preceptor_id,
                "residente_id": o.residente_id,
                "competencia": o.competencia,
                "registrada_em": o.registrada_em,
                "ativa": True,
            }
            for o in ativas
        ],
    }
