"""Alertas estatísticos de padrão anômalo de avaliação (Sprint 4).

Roda na confirmação de cada avaliação. Os alertas não bloqueiam nada —
só ficam registrados para o administrador revisar. As heurísticas
comparativas precisam de amostra mínima: com pouco uso real elas
simplesmente não disparam (o cronograma já prevê isso).

Heurísticas:
- velocidade_suspeita: ficha preenchida rápido demais.
- volume_atipico: muitas avaliações confirmadas pelo mesmo avaliador no mesmo dia.
- notas_uniformes: as últimas N avaliações do avaliador têm todas a mesma nota.
- leniencia: média normalizada do avaliador muito acima da dos demais avaliadores.
"""

from __future__ import annotations

import statistics
import uuid
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.instrumentos import obter_instrumento
from app.db.models import AlertaAnomalia, Avaliacao, agora_utc

LIMIAR_SEGUNDOS = 15
LIMIAR_VOLUME_DIA = 10
JANELA_UNIFORMIDADE = 10
AMOSTRA_MIN_AVALIADOR = 10
AMOSTRA_MIN_DEMAIS = 30
DESVIOS_LENIENCIA = 2.0
INTERVALO_REPETICAO = timedelta(days=7)

INSTRUMENTO_EXCLUIDO = "setq_smart"  # anônimo e de fluxo invertido


def _normalizar(avaliacao: Avaliacao) -> float | None:
    instrumento = obter_instrumento(avaliacao.instrumento)
    if instrumento.codigo == "zwisch":
        minimo, maximo = instrumento.escala_min, instrumento.escala_max
    else:
        minimo, maximo = instrumento.total_minimo, instrumento.total_maximo
    if maximo == minimo:
        return None
    return (avaliacao.nota - minimo) / (maximo - minimo)


def _ja_alertado_recentemente(db: Session, avaliador_id: uuid.UUID, tipo: str) -> bool:
    return (
        db.scalar(
            select(func.count(AlertaAnomalia.id))
            .where(AlertaAnomalia.avaliador_id == avaliador_id)
            .where(AlertaAnomalia.tipo_alerta == tipo)
            .where(AlertaAnomalia.criado_em >= agora_utc() - INTERVALO_REPETICAO)
        )
        or 0
    ) > 0


def _alertar(db: Session, avaliacao: Avaliacao, tipo: str, detalhes: dict) -> AlertaAnomalia:
    alerta = AlertaAnomalia(
        avaliacao_id=avaliacao.id,
        avaliador_id=avaliacao.avaliador_id,
        tipo_alerta=tipo,
        detalhes=detalhes,
    )
    db.add(alerta)
    return alerta


def _confirmadas_do_avaliador(db: Session, avaliador_id: uuid.UUID) -> list[Avaliacao]:
    return list(
        db.scalars(
            select(Avaliacao)
            .where(Avaliacao.avaliador_id == avaliador_id)
            .where(Avaliacao.confirmado.is_(True))
            .where(Avaliacao.instrumento != INSTRUMENTO_EXCLUIDO)
            .order_by(Avaliacao.confirmado_em.desc())
        )
    )


def analisar_avaliacao(
    db: Session,
    avaliacao: Avaliacao,
    tempo_preenchimento_segundos: int | None = None,
) -> list[AlertaAnomalia]:
    """Aplica as heurísticas a uma avaliação recém-confirmada.

    Deve ser chamada depois do flush da confirmação e antes do commit,
    na mesma sessão da requisição. Retorna os alertas criados.
    """
    if avaliacao.instrumento == INSTRUMENTO_EXCLUIDO:
        return []

    criados: list[AlertaAnomalia] = []
    avaliador_id = avaliacao.avaliador_id

    if tempo_preenchimento_segundos is not None and tempo_preenchimento_segundos < LIMIAR_SEGUNDOS:
        criados.append(
            _alertar(
                db,
                avaliacao,
                "velocidade_suspeita",
                {"tempo_segundos": tempo_preenchimento_segundos, "limiar": LIMIAR_SEGUNDOS},
            )
        )

    historico = _confirmadas_do_avaliador(db, avaliador_id)

    hoje = (avaliacao.confirmado_em or agora_utc()).date()
    no_dia = [a for a in historico if a.confirmado_em and a.confirmado_em.date() == hoje]
    if len(no_dia) >= LIMIAR_VOLUME_DIA and not _ja_alertado_recentemente(
        db, avaliador_id, "volume_atipico"
    ):
        criados.append(
            _alertar(
                db,
                avaliacao,
                "volume_atipico",
                {"avaliacoes_no_dia": len(no_dia), "limiar": LIMIAR_VOLUME_DIA},
            )
        )

    ultimas = historico[:JANELA_UNIFORMIDADE]
    if (
        len(ultimas) >= JANELA_UNIFORMIDADE
        and len({(a.instrumento, a.nota) for a in ultimas}) == 1
        and not _ja_alertado_recentemente(db, avaliador_id, "notas_uniformes")
    ):
        criados.append(
            _alertar(
                db,
                avaliacao,
                "notas_uniformes",
                {"janela": JANELA_UNIFORMIDADE, "nota": ultimas[0].nota},
            )
        )

    if len(historico) >= AMOSTRA_MIN_AVALIADOR and not _ja_alertado_recentemente(
        db, avaliador_id, "leniencia"
    ):
        demais = db.scalars(
            select(Avaliacao)
            .where(Avaliacao.avaliador_id != avaliador_id)
            .where(Avaliacao.confirmado.is_(True))
            .where(Avaliacao.instrumento != INSTRUMENTO_EXCLUIDO)
        )
        notas_demais = [n for n in (_normalizar(a) for a in demais) if n is not None]
        notas_avaliador = [n for n in (_normalizar(a) for a in historico) if n is not None]
        if len(notas_demais) >= AMOSTRA_MIN_DEMAIS and notas_avaliador:
            media_demais = statistics.fmean(notas_demais)
            desvio = statistics.pstdev(notas_demais)
            media_avaliador = statistics.fmean(notas_avaliador)
            if desvio > 0 and media_avaliador > media_demais + DESVIOS_LENIENCIA * desvio:
                criados.append(
                    _alertar(
                        db,
                        avaliacao,
                        "leniencia",
                        {
                            "media_avaliador": round(media_avaliador, 3),
                            "media_demais": round(media_demais, 3),
                            "desvio_demais": round(desvio, 3),
                            "amostra_avaliador": len(notas_avaliador),
                            "amostra_demais": len(notas_demais),
                        },
                    )
                )

    if criados:
        db.flush()
    return criados
