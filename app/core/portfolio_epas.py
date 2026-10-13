"""Ponte entre o portfólio (tarefa 3) e o Mapa das EPAs (tarefas 1 e 2).

O QUE É FIXO vem do documento das EPAs e está em app/core/catalogo_epas.py:
as 16 EPAs de Cirurgia Geral, o nível esperado em cada ano (R1/R2/R3) e o
mínimo de observações por trimestre.

O QUE É DE CADA RESIDENTE (ano atual, nível atual em cada EPA, observações
no trimestre) é das tarefas 1 e 2. O contrato é:

    O módulo `app/core/epas.py` expõe

        progresso_do_residente(db: Session, residente_id: uuid.UUID)

    e devolve:

        {
            "ano_residente": "R2",           # ano atual do residente (ou None)
            "epas": [
                {
                    "codigo": "EPA 9",               # obrigatório ("EPA 9", "EPA9", 9…)
                    "nivel_atual": 2,                # obrigatório; None = sem nível ainda
                    "observacoes_trimestre": 7,      # opcional (tarefa 2)
                    "atualizado_em": datetime(...),  # opcional (última decisão de nível)
                },
                ...
            ],
        }

    (Também aceita só a lista de EPAs, sem o ano.)

    Nome, especialidade, níveis esperados por ano e mínimo por trimestre
    são completados pelo catálogo a partir do código. Para uma EPA que NÃO
    está no catálogo (ex.: as 8 de Cabeça e Pescoço, enquanto o documento
    delas não chega), a entrada precisa trazer também `nome` e
    `niveis_esperados` ({"R4": 2, "R5": 3}); `especialidade` e
    `minimo_trimestre` são opcionais.

Enquanto `app/core/epas.py` não existir, o portfólio mostra as 16 EPAs do
catálogo com a trajetória esperada (R1→R2→R3) e o nível atual "sem
registro". Não é preciso mexer no portfólio quando a tarefa 1 subir.
"""
from __future__ import annotations

import importlib
import importlib.util
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.catalogo_epas import (
    EPAS,
    FONTE,
    NIVEIS_CURTOS,
    NIVEIS_ENTRUSTAMENTO,
    EPA,
    normalizar_codigo,
    obter_epa,
)

MODULO_EPAS = "app.core.epas"
FUNCAO_EPAS = "progresso_do_residente"
NIVEL_MAXIMO = 5


class ProgressoEPAInvalido(ValueError):
    """A tarefa 1 devolveu uma entrada que não dá para exibir."""


@dataclass(frozen=True)
class ProgressoEPA:
    codigo: str
    nome: str
    especialidade: str | None
    niveis_esperados: dict[str, int]
    ano_residente: str | None
    nivel_atual: int | None
    observacoes_trimestre: int | None = None
    minimo_trimestre: int | None = None
    regra_minimo: str | None = None
    atualizado_em: datetime | None = None

    @property
    def nivel_esperado(self) -> int | None:
        """Nível esperado ao fim do ano em que o residente está."""
        if self.ano_residente is None:
            return None
        return self.niveis_esperados.get(self.ano_residente)

    @property
    def situacao(self) -> str:
        """`atingido` | `abaixo` | `sem_nivel` | `sem_referencia`."""
        if self.nivel_atual is None:
            return "sem_nivel"
        if self.nivel_esperado is None:
            return "sem_referencia"
        return "atingido" if self.nivel_atual >= self.nivel_esperado else "abaixo"

    def como_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "nome": self.nome,
            "especialidade": self.especialidade,
            "niveis_esperados": self.niveis_esperados,
            "ano_residente": self.ano_residente,
            "nivel_esperado": self.nivel_esperado,
            "nivel_atual": self.nivel_atual,
            "observacoes_trimestre": self.observacoes_trimestre,
            "minimo_trimestre": self.minimo_trimestre,
            "regra_minimo": self.regra_minimo,
            "atualizado_em": self.atualizado_em,
            "situacao": self.situacao,
            "nivel_esperado_rotulo": NIVEIS_CURTOS.get(self.nivel_esperado) if self.nivel_esperado else None,
            "nivel_atual_rotulo": NIVEIS_CURTOS.get(self.nivel_atual) if self.nivel_atual else None,
        }


@dataclass(frozen=True)
class ResultadoEPAs:
    # True quando os níveis atuais vêm do sistema (tarefa 1); False quando
    # só temos o catálogo (trajetória esperada, sem nível atual).
    niveis_do_sistema: bool
    ano_residente: str | None
    itens: list[ProgressoEPA] = field(default_factory=list)
    fonte: str = FONTE


def _ler(entrada: Any, campo: str, padrao: Any = None) -> Any:
    if isinstance(entrada, dict):
        return entrada.get(campo, padrao)
    return getattr(entrada, campo, padrao)


def _ano(valor: Any) -> str | None:
    if valor is None or str(valor).strip() == "":
        return None
    texto = str(valor).strip().upper()
    return texto if texto.startswith("R") else f"R{texto}"


def _do_catalogo(epa: EPA, ano: str | None) -> ProgressoEPA:
    return ProgressoEPA(
        codigo=epa.codigo,
        nome=epa.titulo,
        especialidade=epa.especialidade,
        niveis_esperados=dict(epa.niveis_esperados),
        ano_residente=ano,
        nivel_atual=None,
        minimo_trimestre=epa.minimo_trimestre,
        regra_minimo=epa.regra_minimo,
    )


def _normalizar(entrada: Any, ano: str | None) -> ProgressoEPA:
    codigo_bruto = _ler(entrada, "codigo")
    if codigo_bruto is None:
        raise ProgressoEPAInvalido("Entrada de EPA sem 'codigo'.")

    epa = obter_epa(codigo_bruto)
    nome = _ler(entrada, "nome") or (epa.titulo if epa else None)
    niveis = _ler(entrada, "niveis_esperados") or (dict(epa.niveis_esperados) if epa else None)
    if not nome or not niveis:
        raise ProgressoEPAInvalido(
            f"EPA '{codigo_bruto}' não está no catálogo: envie também 'nome' e "
            "'niveis_esperados' (ex.: {'R4': 2, 'R5': 3})."
        )

    nivel_atual = _ler(entrada, "nivel_atual")
    observacoes = _ler(entrada, "observacoes_trimestre", _ler(entrada, "observacoes"))
    minimo = _ler(entrada, "minimo_trimestre", _ler(entrada, "observacoes_minimas"))
    if minimo is None and epa is not None:
        minimo = epa.minimo_trimestre

    return ProgressoEPA(
        codigo=epa.codigo if epa else normalizar_codigo(codigo_bruto),
        nome=str(nome),
        especialidade=_ler(entrada, "especialidade") or (epa.especialidade if epa else None),
        niveis_esperados={_ano(k): int(v) for k, v in dict(niveis).items()},
        ano_residente=ano,
        nivel_atual=int(nivel_atual) if nivel_atual is not None else None,
        observacoes_trimestre=int(observacoes) if observacoes is not None else None,
        minimo_trimestre=int(minimo) if minimo is not None else None,
        regra_minimo=_ler(entrada, "regra_minimo") or (epa.regra_minimo if epa else None),
        atualizado_em=_ler(entrada, "atualizado_em"),
    )


def _provedor() -> Callable[[Session, uuid.UUID], Any] | None:
    """Acha a função da tarefa 1, se ela já existir no código."""
    if importlib.util.find_spec(MODULO_EPAS) is None:
        return None
    # Se o módulo existe mas quebra ao importar, o erro sobe de propósito:
    # esconder isso faria o portfólio mostrar "sem registro" em tudo.
    modulo = importlib.import_module(MODULO_EPAS)
    return getattr(modulo, FUNCAO_EPAS, None)


def _chave_ordem(item: ProgressoEPA) -> tuple:
    numero = item.codigo.replace("EPA", "").strip()
    return (item.especialidade or "", int(numero) if numero.isdigit() else 999, item.codigo)


def progresso_epas(db: Session, residente_id: uuid.UUID) -> ResultadoEPAs:
    provedor = _provedor()
    if provedor is None:
        return ResultadoEPAs(
            niveis_do_sistema=False,
            ano_residente=None,
            itens=[_do_catalogo(e, None) for e in EPAS],
        )

    resposta = provedor(db, residente_id) or []
    if isinstance(resposta, dict):
        ano = _ano(resposta.get("ano_residente"))
        entradas = resposta.get("epas") or []
    else:
        ano, entradas = None, resposta

    itens = [_normalizar(e, ano) for e in entradas]
    return ResultadoEPAs(
        niveis_do_sistema=True,
        ano_residente=ano,
        itens=sorted(itens, key=_chave_ordem),
    )


__all__ = [
    "NIVEIS_ENTRUSTAMENTO",
    "NIVEIS_CURTOS",
    "NIVEL_MAXIMO",
    "ProgressoEPA",
    "ProgressoEPAInvalido",
    "ResultadoEPAs",
    "progresso_epas",
]
