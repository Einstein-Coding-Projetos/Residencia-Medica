"""Painel por perfil (Sprint 4, versão funcional).

Um único endpoint devolve o resumo do papel de quem está logado. Ainda
sem os gráficos comparativos de turma (ficam para depois da entrega).
"""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import UsuarioAtual
from app.api.routes.discordancias import prazo_discordancia
from app.api.routes.engajamento import montar_pendencias
from app.core.contexto_service import servicos_do_usuario_em
from app.core.engajamento_service import (
    bloqueios_certificacao,
    competencia_de,
    fim_da_competencia,
    status_certificacao,
)
from app.core.epa_service import calcular_mapa_epas
from app.core.instrumentos import obter_instrumento
from app.db.models import (
    PAPEIS_AVALIADORES,
    AlertaAnomalia,
    AlertaEngajamento,
    Alocacao,
    Avaliacao,
    Discordancia,
    Notificacao,
    OmissaoAvaliacao,
    Papel,
    Servico,
    Usuario,
    agora_utc,
)
from app.db.session import get_db

router = APIRouter(prefix="/dashboard", tags=["painel"])

SETQ = "setq_smart"


def _nao_lidas(db: Session, usuario: Usuario) -> int:
    return db.scalar(
        select(func.count(Notificacao.id))
        .where(Notificacao.usuario_id == usuario.id)
        .where(Notificacao.lida_em.is_(None))
    ) or 0


def _no_mes(avaliacao: Avaliacao, inicio: date, fim: date) -> bool:
    dia = avaliacao.data_atividade or (avaliacao.confirmado_em.date() if avaliacao.confirmado_em else None)
    return dia is not None and inicio <= dia <= fim


def _painel_residente(db: Session, residente: Usuario, hoje: date) -> dict:
    inicio, fim = competencia_de(hoje), fim_da_competencia(competencia_de(hoje))
    recebidas = list(
        db.scalars(
            select(Avaliacao)
            .where(Avaliacao.residente_id == residente.id)
            .where(Avaliacao.confirmado.is_(True))
            .where(Avaliacao.instrumento != SETQ)
            .order_by(Avaliacao.confirmado_em.desc())
        )
    )
    com_discordancia = set(
        db.scalars(select(Discordancia.avaliacao_id).where(Discordancia.residente_id == residente.id))
    )
    nomes = dict(db.execute(select(Usuario.id, Usuario.nome)).all())
    agora = agora_utc()

    ultimas = []
    for a in recebidas[:5]:
        prazo = prazo_discordancia(a)
        ultimas.append(
            {
                "id": a.id,
                "instrumento": a.instrumento,
                "instrumento_nome": obter_instrumento(a.instrumento).nome,
                "nota": a.nota,
                "faixa_rotulo": a.faixa_rotulo,
                "data_atividade": a.data_atividade,
                "avaliador_nome": nomes.get(a.avaliador_id, ""),
                "discordancia_registrada": a.id in com_discordancia,
                "pode_discordar_ate": prazo if prazo and prazo > agora and a.id not in com_discordancia else None,
            }
        )

    mapa = calcular_mapa_epas(db, residente)
    discordancias = list(db.scalars(select(Discordancia).where(Discordancia.residente_id == residente.id)))

    return {
        "avaliacoes_recebidas": len(recebidas),
        "avaliacoes_no_mes": sum(1 for a in recebidas if _no_mes(a, inicio, fim)),
        "ultimas_avaliacoes": ultimas,
        "epas": {
            "total": len(mapa),
            "dentro_do_esperado": sum(1 for e in mapa if e["dentro_do_esperado"]),
            "abaixo_do_esperado": [
                {"codigo": e["codigo"], "titulo": e["titulo"], "nivel_atual": e["nivel_atual"], "nivel_esperado": e["nivel_esperado"]}
                for e in mapa
                if not e["dentro_do_esperado"]
            ],
        },
        "discordancias": {
            "abertas": sum(1 for d in discordancias if d.resposta is None),
            "respondidas": sum(1 for d in discordancias if d.resposta is not None),
        },
        "certificacao": status_certificacao(db, residente.id),
    }


def _painel_avaliador(db: Session, avaliador: Usuario, hoje: date) -> dict:
    inicio, fim = competencia_de(hoje), fim_da_competencia(competencia_de(hoje))

    meus_servicos = servicos_do_usuario_em(db, avaliador.id, hoje)
    residentes_hoje = []
    if meus_servicos:
        linhas = db.execute(
            select(Usuario.id, Usuario.nome, Servico.nome)
            .join(Alocacao, Alocacao.usuario_id == Usuario.id)
            .join(Servico, Servico.id == Alocacao.servico_id)
            .where(Usuario.papel == Papel.RESIDENTE)
            .where(Usuario.ativo.is_(True))
            .where(Alocacao.servico_id.in_(meus_servicos))
            .where(Alocacao.data_inicio <= hoje)
            .where(Alocacao.data_fim >= hoje)
            .order_by(Usuario.nome)
        ).all()
        residentes_hoje = [{"id": i, "nome": n, "servico": s} for i, n, s in linhas]

    minhas = list(
        db.scalars(
            select(Avaliacao)
            .where(Avaliacao.avaliador_id == avaliador.id)
            .where(Avaliacao.instrumento != SETQ)
        )
    )
    aguardando = list(
        db.scalars(
            select(Discordancia)
            .where(Discordancia.avaliador_id == avaliador.id)
            .where(Discordancia.resposta.is_(None))
            .order_by(Discordancia.criada_em)
        )
    )
    nomes = dict(db.execute(select(Usuario.id, Usuario.nome)).all())

    painel = {
        "residentes_alocados_hoje": residentes_hoje,
        "avaliacoes_confirmadas_no_mes": sum(1 for a in minhas if a.confirmado and _no_mes(a, inicio, fim)),
        "rascunhos_nao_enviados": sum(1 for a in minhas if not a.confirmado),
        "discordancias_aguardando_resposta": [
            {
                "id": d.id,
                "avaliacao_id": d.avaliacao_id,
                "residente_nome": nomes.get(d.residente_id, ""),
                "criada_em": d.criada_em,
            }
            for d in aguardando
        ],
    }
    # Engajamento obrigatório é do preceptor (R4/R5 não recebe D15/D20/D25).
    if avaliador.papel == Papel.PRECEPTOR:
        painel["pendencias_do_mes"] = montar_pendencias(db, hoje, avaliador.id)
    return painel


def _painel_admin(db: Session, hoje: date) -> dict:
    competencia = competencia_de(hoje)
    inicio, fim = competencia, fim_da_competencia(competencia)

    por_papel = Counter(
        p.value for p in db.scalars(select(Usuario.papel).where(Usuario.ativo.is_(True)))
    )
    confirmadas = db.scalars(
        select(Avaliacao).where(Avaliacao.confirmado.is_(True)).where(Avaliacao.instrumento != SETQ)
    )
    alertas_30d = Counter(
        db.scalars(
            select(AlertaAnomalia.tipo_alerta).where(
                AlertaAnomalia.criado_em >= agora_utc() - timedelta(days=30)
            )
        )
    )
    escaladas = db.scalar(
        select(func.count(AlertaEngajamento.id))
        .where(AlertaEngajamento.competencia == competencia)
        .where(AlertaEngajamento.marco == "D25")
    ) or 0

    residentes_com_omissao = set(db.scalars(select(OmissaoAvaliacao.residente_id)))
    bloqueados = [r for r in residentes_com_omissao if bloqueios_certificacao(db, r)]

    return {
        "usuarios_por_papel": {p.value: por_papel.get(p.value, 0) for p in Papel},
        "avaliacoes_confirmadas_no_mes": sum(1 for a in confirmadas if _no_mes(a, inicio, fim)),
        "pendencias_do_mes": len(montar_pendencias(db, hoje)),
        "escaladas_d25_no_mes": escaladas,
        "residentes_com_certificacao_bloqueada": len(bloqueados),
        "alertas_anomalia_30_dias": dict(alertas_30d),
        "discordancias_abertas": db.scalar(
            select(func.count(Discordancia.id)).where(Discordancia.resposta.is_(None))
        ) or 0,
    }


@router.get("", summary="Resumo do painel para o perfil de quem está logado")
def meu_painel(usuario: UsuarioAtual, db: Annotated[Session, Depends(get_db)]) -> dict:
    hoje = date.today()
    if usuario.papel == Papel.RESIDENTE:
        dados = _painel_residente(db, usuario, hoje)
    elif usuario.papel in PAPEIS_AVALIADORES:
        dados = _painel_avaliador(db, usuario, hoje)
    else:
        dados = _painel_admin(db, hoje)
    return {
        "papel": usuario.papel.value,
        "data": hoje,
        "notificacoes_nao_lidas": _nao_lidas(db, usuario),
        **dados,
    }
