"""Montagem do portfólio do residente.

Junta, num único objeto, tudo o que já existe no sistema sobre um
residente: notas das avaliações, resultado por instrumento, progresso por
EPA e procedimentos validados. A tela (frontend/portfolio.html) e o PDF
(app/core/portfolio_pdf.py) leem deste mesmo objeto — assim os dois nunca
mostram números diferentes.

Regras de conteúdo:
- Só entram avaliações CONFIRMADAS (rascunho não é feedback — mesma regra
  de GET /avaliacoes/{id}).
- SETQ Smart NÃO entra: nele o residente avalia o preceptor, e mostrar
  essas respostas no portfólio (que o preceptor pode abrir) quebraria o
  anonimato da regra COI-03.
- Só procedimentos VALIDADOS contam na estatística; pendentes e recusados
  aparecem apenas como contagem.
"""
from __future__ import annotations

import json
import uuid
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.instrumentos import INSTRUMENTOS, obter_instrumento
from app.core.portfolio_epas import NIVEIS_ENTRUSTAMENTO, progresso_epas
from app.db.models import Avaliacao, Procedimento, Programa, Usuario, agora_utc
from app.schemas.procedimentos import ROTULOS_PARTICIPACAO

INSTRUMENTOS_FORA_DO_PORTFOLIO = frozenset({"setq_smart"})

ROTULOS_FAIXA: dict[str, str] = {
    "supervisao_direta": "Supervisão direta",
    "assistencia_ocasional": "Assistência ocasional",
    "autonomia_supervisionada": "Autonomia supervisionada",
    "insatisfatorio": "Insatisfatório",
    "em_desenvolvimento": "Em desenvolvimento",
    "satisfatorio": "Satisfatório",
}

# Nome curto para gráficos, tabelas e cabeçalhos.
NOME_CURTO: dict[str, str] = {
    "osats": "OSATS",
    "mini_cex": "Mini-CEX",
    "notss": "NOTSS",
    "zwisch": "Zwisch",
    "setq_smart": "SETQ Smart",
}


def rotulo_faixa(rotulo: str | None) -> str | None:
    if rotulo is None:
        return None
    return ROTULOS_FAIXA.get(rotulo, rotulo)


def _media(valores: list[float]) -> float | None:
    return round(sum(valores) / len(valores), 2) if valores else None


def _data(avaliacao: Avaliacao) -> datetime:
    return avaliacao.confirmado_em or avaliacao.criado_em


# ---------------------------------------------------------------------------
# Blocos
# ---------------------------------------------------------------------------
def _bloco_residente(db: Session, residente: Usuario) -> dict:
    programa = db.get(Programa, residente.programa_id) if residente.programa_id else None
    return {
        "id": residente.id,
        "nome": residente.nome,
        "email": residente.email,
        "programa": programa.nome if programa else None,
        "especialidade": programa.especialidade.nome if programa else None,
        "instituicao": programa.instituicao if programa else None,
    }


def _bloco_avaliacoes(db: Session, residente_id: uuid.UUID) -> list[dict]:
    avaliacoes = db.scalars(
        select(Avaliacao).where(
            Avaliacao.residente_id == residente_id,
            Avaliacao.confirmado.is_(True),
            Avaliacao.instrumento.not_in(INSTRUMENTOS_FORA_DO_PORTFOLIO),
        )
    ).all()

    ids_avaliadores = {a.avaliador_id for a in avaliacoes}
    nomes = {
        u.id: u.nome
        for u in db.scalars(select(Usuario).where(Usuario.id.in_(ids_avaliadores))).all()
    } if ids_avaliadores else {}

    lista = []
    for a in sorted(avaliacoes, key=_data, reverse=True):
        instrumento = obter_instrumento(a.instrumento)
        titulos = {d.codigo: d.titulo for d in instrumento.dominios}

        if instrumento.codigo == "zwisch":
            total_min, total_max = instrumento.escala_min, instrumento.escala_max
            faixa_texto = instrumento.ancora_escala.get(int(a.nota))
        else:
            total_min, total_max = instrumento.total_minimo, instrumento.total_maximo
            faixa_texto = rotulo_faixa(a.faixa_rotulo)

        lista.append(
            {
                "id": a.id,
                "instrumento": a.instrumento,
                "instrumento_nome": NOME_CURTO.get(a.instrumento, instrumento.nome),
                "data": _data(a),
                "avaliador_nome": nomes.get(a.avaliador_id, "—"),
                "nota": a.nota,
                "total_minimo": total_min,
                "total_maximo": total_max,
                "faixa_rotulo": a.faixa_rotulo,
                "faixa_texto": faixa_texto,
                "etapa_cirurgica": a.etapa_cirurgica,
                "observacoes": a.observacoes or "",
                "itens": [
                    {
                        "dominio": item["dominio"],
                        "titulo": titulos.get(item["dominio"], item["dominio"]),
                        "nota": item["nota"],
                    }
                    for item in json.loads(a.itens or "[]")
                ],
                "hash_integridade": a.hash_integridade,
            }
        )
    return lista


def _bloco_instrumentos(avaliacoes: list[dict]) -> list[dict]:
    """Resumo por instrumento de escore (OSATS, Mini-CEX, NOTSS).

    Zwisch fica de fora daqui porque não é escore somado — ver
    `_bloco_zwisch`.
    """
    por_instrumento: dict[str, list[dict]] = defaultdict(list)
    for a in avaliacoes:
        if a["instrumento"] != "zwisch":
            por_instrumento[a["instrumento"]].append(a)

    blocos = []
    for codigo in INSTRUMENTOS:  # ordem estável do registro
        lista = por_instrumento.get(codigo)
        if not lista:
            continue
        instrumento = obter_instrumento(codigo)
        cronologica = sorted(lista, key=lambda a: a["data"])
        notas = [a["nota"] for a in cronologica]

        notas_dominio: dict[str, list[float]] = defaultdict(list)
        for a in cronologica:
            for item in a["itens"]:
                notas_dominio[item["dominio"]].append(item["nota"])

        faixas = Counter(a["faixa_rotulo"] for a in cronologica if a["faixa_rotulo"])
        ultima = cronologica[-1]

        blocos.append(
            {
                "codigo": codigo,
                "nome": NOME_CURTO.get(codigo, instrumento.nome),
                "nome_completo": instrumento.nome,
                "agregacao": instrumento.agregacao,
                "escala_min": instrumento.escala_min,
                "escala_max": instrumento.escala_max,
                "total_minimo": instrumento.total_minimo,
                "total_maximo": instrumento.total_maximo,
                "quantidade": len(cronologica),
                "media": _media(notas),
                "melhor": max(notas),
                "ultima_nota": ultima["nota"],
                "ultima_faixa": rotulo_faixa(ultima["faixa_rotulo"]),
                "evolucao": [{"data": a["data"], "nota": a["nota"]} for a in cronologica],
                "faixas": [
                    {
                        "rotulo": f.rotulo,
                        "texto": rotulo_faixa(f.rotulo),
                        "minimo": f.minimo,
                        "maximo": f.maximo,
                        "quantidade": faixas.get(f.rotulo, 0),
                    }
                    for f in instrumento.faixas
                ],
                "media_por_dominio": [
                    {
                        "codigo": d.codigo,
                        "titulo": d.titulo,
                        "media": _media(notas_dominio.get(d.codigo, [])),
                    }
                    for d in instrumento.dominios
                ],
            }
        )
    return blocos


def _bloco_zwisch(avaliacoes: list[dict]) -> list[dict]:
    """Zwisch: nível de autonomia mais recente por etapa cirúrgica."""
    instrumento = obter_instrumento("zwisch")
    por_etapa: dict[str, list[dict]] = defaultdict(list)
    for a in avaliacoes:
        if a["instrumento"] == "zwisch" and a["etapa_cirurgica"]:
            por_etapa[a["etapa_cirurgica"].strip()].append(a)

    etapas = []
    for etapa, lista in por_etapa.items():
        cronologica = sorted(lista, key=lambda a: a["data"])
        ultimo = int(cronologica[-1]["nota"])
        etapas.append(
            {
                "etapa": etapa,
                "nivel_atual": ultimo,
                "nivel_texto": instrumento.ancora_escala.get(ultimo),
                "melhor_nivel": int(max(a["nota"] for a in cronologica)),
                "quantidade": len(cronologica),
                "ultima_data": cronologica[-1]["data"],
                "historico": [int(a["nota"]) for a in cronologica],
            }
        )
    return sorted(etapas, key=lambda e: e["etapa"].lower())


def _bloco_procedimentos(db: Session, residente_id: uuid.UUID) -> dict:
    todos = db.scalars(
        select(Procedimento).where(Procedimento.residente_id == residente_id)
    ).all()
    validados = sorted(
        (p for p in todos if p.status == "validado"),
        key=lambda p: p.data_realizacao,
        reverse=True,
    )

    por_nome: dict[str, Counter] = defaultdict(Counter)
    for p in validados:
        por_nome[p.nome][p.participacao] += 1

    return {
        "total_validados": len(validados),
        "pendentes": sum(1 for p in todos if p.status == "pendente"),
        "recusados": sum(1 for p in todos if p.status == "recusado"),
        "por_participacao": [
            {
                "participacao": chave,
                "texto": texto,
                "quantidade": sum(1 for p in validados if p.participacao == chave),
            }
            for chave, texto in ROTULOS_PARTICIPACAO.items()
        ],
        "por_nome": sorted(
            (
                {
                    "nome": nome,
                    "total": sum(contagem.values()),
                    **{chave: contagem.get(chave, 0) for chave in ROTULOS_PARTICIPACAO},
                }
                for nome, contagem in por_nome.items()
            ),
            key=lambda linha: (-linha["total"], linha["nome"].lower()),
        ),
        "lista": [
            {
                "id": p.id,
                "nome": p.nome,
                "data_realizacao": p.data_realizacao,
                "participacao": p.participacao,
                "participacao_texto": ROTULOS_PARTICIPACAO.get(p.participacao, p.participacao),
                "observacoes": p.observacoes or "",
            }
            for p in validados
        ],
    }


def _bloco_epas(db: Session, residente_id: uuid.UUID) -> dict:
    resultado = progresso_epas(db, residente_id)
    itens = resultado.itens

    if not resultado.niveis_do_sistema:
        mensagem = (
            "Os níveis atuais de cada EPA ainda não estão no sistema. Abaixo, a "
            "trajetória esperada pelo documento das EPAs para cada ano."
        )
    elif not itens:
        mensagem = "Nenhuma EPA cadastrada para o programa deste residente."
    elif resultado.ano_residente is None:
        mensagem = (
            "O ano de residência (R1, R2…) não foi informado — não dá para "
            "comparar o nível atual com o esperado."
        )
    else:
        mensagem = None

    anos = sorted({ano for e in itens for ano in e.niveis_esperados}, key=lambda a: (len(a), a))

    return {
        "niveis_do_sistema": resultado.niveis_do_sistema,
        "ano_residente": resultado.ano_residente,
        "mensagem": mensagem,
        "fonte": resultado.fonte,
        "niveis": NIVEIS_ENTRUSTAMENTO,
        "anos": anos,
        "total": len(itens),
        "com_nivel": sum(1 for e in itens if e.nivel_atual is not None),
        "atingidas": sum(1 for e in itens if e.situacao == "atingido"),
        "abaixo": sum(1 for e in itens if e.situacao == "abaixo"),
        "comparavel": resultado.niveis_do_sistema and resultado.ano_residente is not None,
        "itens": [e.como_dict() for e in itens],
    }


# ---------------------------------------------------------------------------
# API do módulo
# ---------------------------------------------------------------------------
def montar_portfolio(db: Session, residente: Usuario) -> dict:
    avaliacoes = _bloco_avaliacoes(db, residente.id)
    instrumentos = _bloco_instrumentos(avaliacoes)
    zwisch = _bloco_zwisch(avaliacoes)
    procedimentos = _bloco_procedimentos(db, residente.id)
    epas = _bloco_epas(db, residente.id)

    datas = [a["data"] for a in avaliacoes]

    return {
        "gerado_em": agora_utc(),
        "residente": {**_bloco_residente(db, residente), "ano_residencia": epas["ano_residente"]},
        "resumo": {
            "total_avaliacoes": len(avaliacoes),
            "instrumentos_utilizados": len(instrumentos) + (1 if zwisch else 0),
            "procedimentos_validados": procedimentos["total_validados"],
            "procedimentos_pendentes": procedimentos["pendentes"],
            "epas_total": epas["total"],
            "epas_atingidas": epas["atingidas"],
            "epas_comparavel": epas["comparavel"],
            "primeira_avaliacao": min(datas) if datas else None,
            "ultima_avaliacao": max(datas) if datas else None,
        },
        "epas": epas,
        "instrumentos": instrumentos,
        "zwisch": zwisch,
        "procedimentos": procedimentos,
        "avaliacoes": avaliacoes,
    }
