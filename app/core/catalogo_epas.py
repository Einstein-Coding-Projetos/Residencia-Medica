"""Catálogo das EPAs — fonte: documento das EPAs do programa.

Referência: "Série EPAs na formação em saúde — Cadernos da Residência
Médica, Volume 1: o currículo baseado em EPAs do Programa de Residência
Médica de Cirurgia Geral" (Santa Casa de Belo Horizonte, 2022).

- Quadro 1 (p. 15): as 16 EPAs e o nível de autonomia esperado ao fim de
  cada ano (R1, R2, R3). É a versão revisada em 2021 — as EPAs são
  longitudinais: as mesmas 16 nos três anos, mudando só o nível esperado.
- Apêndices (p. 20-51), item 6b de cada EPA: "Mínimo de 12 vezes no
  trimestre, em contextos cirúrgicos de complexidades diversas e sob a
  observação de diferentes supervisores". Exceções: EPA 11 (referência do
  CBC em gastrectomias) e EPA 16 (supervisionada por gestores).
- Item 7 de cada EPA: escala de confiança/supervisão de 1 a 5 (Ten Cate).
- A decisão de nível é TRIMESTRAL, do Comitê de Competência Clínica (CCC).

Este módulo é só dado estático (como app/core/instrumentos.py). As
tarefas 1 e 2 podem popular o banco a partir daqui ou substituí-lo.

PENDENTE: as 8 EPAs de Cirurgia de Cabeça e Pescoço (R4/R5) NÃO estão
neste documento. Quando chegar o documento delas, acrescente em EPAS.
"""
from __future__ import annotations

from dataclasses import dataclass, field

FONTE = (
    "Cadernos da Residência Médica — Cirurgia Geral, vol. 1 (2022), "
    "Quadro 1 e Apêndices"
)

# Item 7 de cada EPA no documento (redação do próprio documento).
NIVEIS_ENTRUSTAMENTO: dict[int, str] = {
    1: "Pode estar presente e observar, não pode realizar a EPA",
    2: "Executa com supervisão direta e proativa, presente na sala",
    3: "Realiza sem supervisor na sala, com supervisão indireta e reativa",
    4: "Realiza sem supervisão",
    5: "Supervisiona aprendizes iniciantes na EPA",
}

# Versão curta, para tabela e PDF.
NIVEIS_CURTOS: dict[int, str] = {
    1: "Observa",
    2: "Supervisão direta",
    3: "Supervisão reativa",
    4: "Sem supervisão",
    5: "Supervisiona",
}

ANOS_PROGRAMA = ("R1", "R2", "R3")

MINIMO_PADRAO_TRIMESTRE = 12
REGRA_MINIMO_PADRAO = (
    "Mínimo de 12 vezes no trimestre, em contextos cirúrgicos de complexidades "
    "diversas e sob a observação de diferentes supervisores."
)


@dataclass(frozen=True)
class EPA:
    numero: int
    titulo: str
    niveis_esperados: dict[str, int]
    especialidade: str = "Cirurgia Geral"
    minimo_trimestre: int | None = MINIMO_PADRAO_TRIMESTRE
    regra_minimo: str = REGRA_MINIMO_PADRAO
    procedimentos_referencia: tuple[str, ...] = field(default_factory=tuple)

    @property
    def codigo(self) -> str:
        return f"EPA {self.numero}"

    def nivel_esperado(self, ano: str | None) -> int | None:
        if ano is None:
            return None
        return self.niveis_esperados.get(ano.upper())


def _cg(numero: int, titulo: str, r1: int, r2: int, r3: int, **extra) -> EPA:
    return EPA(numero=numero, titulo=titulo, niveis_esperados={"R1": r1, "R2": r2, "R3": r3}, **extra)


# Quadro 1 — Elenco das 16 EPAs do PRMCG, revisado em 2021.
EPAS: tuple[EPA, ...] = (
    _cg(1, "Admitindo o paciente cirúrgico", 2, 3, 5),
    _cg(2, "Cuidando do paciente em pré-operatório", 2, 3, 5),
    _cg(3, "Cuidando do paciente em pós-operatório", 2, 3, 5),
    _cg(4, "Cuidando do paciente cirúrgico crítico", 2, 3, 3),
    _cg(5, "Tratando cirurgicamente o paciente com defeito na parede abdominal", 2, 3, 3),
    _cg(6, "Acessando a cavidade abdominal do paciente cirúrgico", 2, 3, 3),
    _cg(7, "Tratando do paciente com apendicite aguda", 2, 3, 3),
    _cg(8, "Abordando cirurgicamente o paciente para via nutricional alternativa", 2, 3, 3),
    _cg(9, "Tratando pacientes com colecistopatia", 1, 2, 3),
    _cg(10, "Abordando o paciente em urgência cirúrgica", 1, 2, 3),
    _cg(
        11, "Abordando cirurgicamente o paciente com câncer do aparelho digestivo", 1, 2, 3,
        minimo_trimestre=None,
        regra_minimo=(
            "Referência: câncer gástrico. Ponto de proficiência do CBC: pelo menos "
            "5 gastrectomias parciais e 2 totais durante o R2; a decisão considera "
            "os casos disponíveis até o fim do programa."
        ),
        procedimentos_referencia=("Gastrectomia parcial", "Gastrectomia total"),
    ),
    _cg(12, "Abordando o paciente para cateterizações e sondagens", 3, 4, 5),
    _cg(13, "Abordando o paciente para acesso venoso central/dissecção venosa", 3, 4, 5),
    _cg(14, "Abordando o paciente para pequenos procedimentos cirúrgicos", 3, 4, 5),
    _cg(15, "Abordando cirurgicamente o paciente com obesidade mórbida", 1, 2, 3),
    _cg(
        16, "Realizando a gestão da excelência do cuidado em cirurgia geral", 2, 3, 4,
        minimo_trimestre=None,
        regra_minimo="Supervisionada por gestores de saúde em estágio específico.",
    ),
)

EPAS_POR_CODIGO: dict[str, EPA] = {e.codigo: e for e in EPAS}


def normalizar_codigo(codigo: str | int) -> str:
    """Aceita 7, "7", "EPA7", "EPA 07", "epa-7" e devolve "EPA 7"."""
    texto = str(codigo).upper().replace("EPA", "").replace("-", "").replace("_", "").strip()
    if texto.isdigit():
        return f"EPA {int(texto)}"
    return str(codigo)


def obter_epa(codigo: str | int) -> EPA | None:
    return EPAS_POR_CODIGO.get(normalizar_codigo(codigo))
