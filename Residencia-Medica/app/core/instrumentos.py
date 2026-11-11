"""Registro central dos instrumentos de avaliação.

Este módulo é o CONTRATO COMPARTILHADO entre as três frentes do Sprint 2.
Cada instrumento declara aqui a sua escala, os seus domínios e a forma de
calcular o resultado. As rotas e os schemas leem daqui — nenhum arquivo de
rota deve ter escala ou domínio escrito na mão.

Como adicionar/ajustar um instrumento:
    1. Edite (ou acrescente) a entrada correspondente em INSTRUMENTOS.
    2. Não mexa em mais nada. Rota, validação e cálculo já leem do registro.

Estado por instrumento (Sprint 2):
    osats       — COMPLETO
    mini_cex    — COMPLETO
    notss       — escala e domínios preenchidos a partir do documento técnico;
                  descritores comportamentais e faixas de corte pendentes —
                  falta dado clínico de origem, não é lacuna de código
    zwisch      — COMPLETO. Não é soma de domínios: uma avaliação = uma etapa
                  cirúrgica + um nível Z1–Z4 (`validar_zwisch`/`resultado_zwisch`)
    setq_smart  — COMPLETO. Fluxo invertido (residente avalia preceptor),
                  anonimizado, com agregação mínima de 3 residentes (COI-03)
                  via `POST /avaliacoes/setq` e `GET /avaliacoes/setq/resumo`

Referência: RMS-Brasil, Documento Técnico v3.2, Parte VI.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class InstrumentoDesconhecido(ValueError):
    """Código de instrumento que não existe no registro."""


class ItensInvalidos(ValueError):
    """Os itens enviados não batem com a definição do instrumento."""


DECLARACAO_OBSERVACAO_DIRETA = (
    "Confirmo que observei este residente pessoalmente nesta atividade "
    "na data informada."
)


@dataclass(frozen=True)
class Dominio:
    """Um domínio (linha) da ficha de avaliação."""

    codigo: str
    titulo: str
    descricao: str = ""


@dataclass(frozen=True)
class Faixa:
    """Faixa de corte do score total, com a leitura pedagógica correspondente."""

    minimo: float
    maximo: float
    rotulo: str
    descricao: str = ""

    def contem(self, valor: float) -> bool:
        return self.minimo <= valor <= self.maximo


@dataclass(frozen=True)
class Instrumento:
    codigo: str
    nome: str
    escala_min: int
    escala_max: int
    dominios: tuple[Dominio, ...]
    agregacao: str = "soma"  # "soma" | "media" | "nao_aplicavel"
    faixas: tuple[Faixa, ...] = ()
    dominios_fixos: bool = True
    anonimo: bool = False
    observacao_interna: str = ""
    ancora_escala: dict[int, str] = field(default_factory=dict)
    texto_confirmacao: str = DECLARACAO_OBSERVACAO_DIRETA

    @property
    def total_minimo(self) -> int:
        return self.escala_min * len(self.dominios)

    @property
    def total_maximo(self) -> int:
        return self.escala_max * len(self.dominios)

    @property
    def codigos_dominios(self) -> tuple[str, ...]:
        return tuple(d.codigo for d in self.dominios)


# ---------------------------------------------------------------------------
# OSATS — frente A
# ---------------------------------------------------------------------------
OSATS = Instrumento(
    codigo="osats",
    nome="OSATS — Objective Structured Assessment of Technical Skills",
    escala_min=1,
    escala_max=5,
    agregacao="soma",
    ancora_escala={
        1: "Muito abaixo do esperado",
        3: "No nível esperado",
        5: "Muito acima do esperado",
    },
    dominios=(
        Dominio(
            "respeito_tecidos",
            "Respeito pelos tecidos",
            "Manuseio gentil dos tecidos; tração adequada; evita lesões "
            "desnecessárias; reconhece e preserva estruturas importantes.",
        ),
        Dominio(
            "tempo_fluxo",
            "Tempo e fluxo operatório",
            "Progressão lógica da cirurgia; sem pausas desnecessárias; "
            "eficiência sem precipitação; ritmo adequado ao nível de treinamento.",
        ),
        Dominio(
            "manejo_instrumentos",
            "Manejo de instrumentos",
            "Uso correto e seguro dos instrumentos; troca eficiente; "
            "posicionamento adequado; evita movimentos desnecessários.",
        ),
        Dominio(
            "conhecimento_procedimento",
            "Conhecimento do procedimento",
            "Demonstra conhecimento dos passos operatórios; antecipa próximas "
            "etapas; reconhece variações anatômicas; sabe o que fazer se algo "
            "der errado.",
        ),
        Dominio(
            "uso_assistentes",
            "Uso de assistentes",
            "Orienta e posiciona o assistente eficientemente; comunicação clara "
            "sobre o que precisa; aproveita a ajuda disponível.",
        ),
        Dominio(
            "hemostasia",
            "Hemostasia",
            "Controle eficiente do sangramento; antecipa e previne quando "
            "possível; escolha adequada da técnica hemostática.",
        ),
        Dominio(
            "impressao_global",
            "Impressão global",
            "Julgamento global sobre a performance técnica observada; captura "
            "aspectos não cobertos pelos outros domínios.",
        ),
    ),
    faixas=(
        Faixa(7, 17, "supervisao_direta", "Supervisão direta obrigatória."),
        Faixa(18, 27, "assistencia_ocasional", "Assistência ocasional."),
        Faixa(28, 35, "autonomia_supervisionada", "Autonomia supervisionada."),
    ),
    observacao_interna=(
        "Uso restrito a performance técnica em procedimento observável "
        "(centro cirúrgico ou simulação). Não usar para consulta clínica."
    ),
)


# ---------------------------------------------------------------------------
# Mini-CEX — frente A
# ---------------------------------------------------------------------------
MINI_CEX = Instrumento(
    codigo="mini_cex",
    nome="Mini-CEX — Mini Clinical Evaluation Exercise",
    escala_min=1,
    escala_max=9,
    agregacao="soma",
    ancora_escala={
        1: "Insatisfatório",
        4: "Satisfatório",
        7: "Superior",
    },
    dominios=(
        Dominio(
            "anamnese",
            "Anamnese",
            "Coleta dirigida, eficiente e completa de dados clínicos relevantes. "
            "Em CCP: disfagia, disfonia, dispneia, perda de peso, tabagismo e "
            "etilismo como fatores de risco oncológico.",
        ),
        Dominio(
            "exame_fisico",
            "Exame físico",
            "Exame adequado para a queixa; técnica correta; achados "
            "interpretados. Em CCP: palpação de cadeia ganglionar, tireoide e "
            "glândulas salivares; laringoscopia flexível quando indicado.",
        ),
        Dominio(
            "raciocinio_clinico",
            "Raciocínio clínico",
            "Formulação de hipóteses diagnósticas; diagnóstico diferencial; "
            "seleção de exames. Em CCP: critérios de indicação de biópsia e "
            "estadiamento TNM.",
        ),
        Dominio(
            "comunicacao",
            "Comunicação",
            "Linguagem adequada; escuta ativa; explica o plano ao paciente. "
            "Em CCP: comunicação de diagnóstico oncológico e envolvimento da "
            "família.",
        ),
        Dominio(
            "organizacao_eficiencia",
            "Organização e eficiência",
            "Gestão do tempo da consulta; documentação adequada no prontuário; "
            "prescrição pré e pós-operatória correta.",
        ),
    ),
    faixas=(
        Faixa(5, 19, "insatisfatorio", "Abaixo do esperado — requer plano de apoio."),
        Faixa(20, 34, "em_desenvolvimento", "Em desenvolvimento — abaixo do corte de 35."),
        Faixa(35, 45, "satisfatorio", "Satisfatório para o nível esperado."),
    ),
    observacao_interna=(
        "Observação direta de 15–25 minutos, com feedback imediato em seguida "
        "(5–10 minutos). Corte de referência do documento: score ≥ 35."
    ),
)


# ---------------------------------------------------------------------------
# NOTSS — frente B (estrutura pronta, descritores e faixas pendentes)
# ---------------------------------------------------------------------------
NOTSS = Instrumento(
    codigo="notss",
    nome="NOTSS — Non-Technical Skills for Surgeons",
    escala_min=1,
    escala_max=4,
    agregacao="soma",
    ancora_escala={
        1: "Deficiente",
        2: "Marginal",
        3: "Aceitável",
        4: "Excelente",
    },
    dominios=(
        Dominio("consciencia_situacional", "Consciência situacional"),
        Dominio("tomada_decisao", "Tomada de decisão"),
        Dominio("comunicacao_equipe", "Comunicação e trabalho em equipe"),
        Dominio("lideranca", "Liderança"),
    ),
    faixas=(),  # PENDENTE frente B — o documento não define faixas de corte.
    observacao_interna=(
        "PENDENTE (frente B): descritores comportamentais positivos/negativos por "
        "domínio e definição de faixas de corte. Uso exclusivo em contexto "
        "cirúrgico intraoperatório."
    ),
)


# ---------------------------------------------------------------------------
# Zwisch — NÃO é soma de domínios: um nível por etapa cirúrgica
# ---------------------------------------------------------------------------
ZWISCH = Instrumento(
    codigo="zwisch",
    nome="Zwisch Scale — Escala de Autonomia Cirúrgica",
    escala_min=1,
    escala_max=4,
    agregacao="nao_aplicavel",
    dominios_fixos=False,
    ancora_escala={
        1: "Z1 — Show and tell",
        2: "Z2 — Active help",
        3: "Z3 — Passive help",
        4: "Z4 — Supervision only",
    },
    dominios=(),
    faixas=(),
    observacao_interna=(
        "Cada avaliação Zwisch cobre uma etapa cirúrgica: o preceptor registra "
        "o nível de autonomia (Z1–Z4) observado naquela etapa, não uma soma de "
        "domínios. Um mesmo procedimento pode gerar várias avaliações Zwisch, "
        "uma por etapa. Ver `validar_zwisch`/`resultado_zwisch` neste módulo."
    ),
)


# ---------------------------------------------------------------------------
# SETQ Smart — frente C (anonimização pendente)
# ---------------------------------------------------------------------------
SETQ_SMART = Instrumento(
    codigo="setq_smart",
    nome="SETQ Smart — System for Evaluation of Teaching Qualities",
    escala_min=1,
    escala_max=5,
    agregacao="media",
    anonimo=True,
    dominios=(
        Dominio("aprendizagem", "Aprendizagem"),
        Dominio("feedback", "Feedback"),
        Dominio("colaboracao", "Colaboração"),
        Dominio("planejamento", "Planejamento e organização"),
        Dominio("profissionalismo", "Profissionalismo"),
    ),
    faixas=(),
    texto_confirmacao=(
        "Confirmo que esta avaliação reflete minha experiência genuína com "
        "este preceptor."
    ),
    observacao_interna=(
        "Inverte o sentido da avaliação — o RESIDENTE avalia o PRECEPTOR, "
        "via `POST /avaliacoes/setq`. O resultado só fica visível ao preceptor "
        "de forma agregada e anônima, a partir de 3 residentes (regra COI-03) "
        "— ver `GET /avaliacoes/setq/resumo/{preceptor_id}`."
    ),
)


INSTRUMENTOS: dict[str, Instrumento] = {
    i.codigo: i for i in (OSATS, MINI_CEX, NOTSS, ZWISCH, SETQ_SMART)
}


# ---------------------------------------------------------------------------
# API do módulo
# ---------------------------------------------------------------------------
def codigos_disponiveis() -> tuple[str, ...]:
    return tuple(INSTRUMENTOS.keys())


def obter_instrumento(codigo: str) -> Instrumento:
    try:
        return INSTRUMENTOS[codigo]
    except KeyError:
        validos = ", ".join(codigos_disponiveis())
        raise InstrumentoDesconhecido(
            f"Instrumento '{codigo}' não existe. Disponíveis: {validos}."
        ) from None


def validar_itens(instrumento: Instrumento, itens: list) -> None:
    """Confere se os itens enviados batem com a definição do instrumento.

    Cada item precisa ter `.dominio` (str) e `.nota` (int). Levanta
    ItensInvalidos com mensagem legível quando algo não bate.
    """
    if not itens:
        raise ItensInvalidos("A avaliação precisa ter pelo menos um item.")

    for item in itens:
        if not (instrumento.escala_min <= item.nota <= instrumento.escala_max):
            raise ItensInvalidos(
                f"Nota {item.nota} fora da escala do {instrumento.nome}: "
                f"{instrumento.escala_min} a {instrumento.escala_max}."
            )

    codigos = [item.dominio for item in itens]

    duplicados = {c for c in codigos if codigos.count(c) > 1}
    if duplicados:
        raise ItensInvalidos(
            "Domínio repetido na mesma avaliação: " + ", ".join(sorted(duplicados)) + "."
        )

    if not instrumento.dominios_fixos:
        return

    esperados = set(instrumento.codigos_dominios)
    enviados = set(codigos)

    desconhecidos = enviados - esperados
    if desconhecidos:
        raise ItensInvalidos(
            "Domínio não pertence a este instrumento: "
            + ", ".join(sorted(desconhecidos))
            + "."
        )

    faltando = esperados - enviados
    if faltando:
        raise ItensInvalidos(
            f"O {instrumento.nome} exige os {len(esperados)} domínios preenchidos. "
            "Faltando: " + ", ".join(sorted(faltando)) + "."
        )


@dataclass(frozen=True)
class Resultado:
    """Resultado calculado de uma ficha preenchida."""

    valor: float
    agregacao: str
    total_minimo: int
    total_maximo: int
    faixa_rotulo: str | None
    faixa_descricao: str | None


def calcular_resultado(instrumento: Instrumento, itens: list) -> Resultado:
    """Calcula o score do instrumento e classifica na faixa correspondente.

    OSATS e Mini-CEX usam SOMA (7–35 e 5–45 respectivamente), conforme o
    documento técnico — não média.
    """
    notas = [item.nota for item in itens]

    if instrumento.agregacao == "soma":
        valor: float = float(sum(notas))
    elif instrumento.agregacao == "media":
        valor = round(sum(notas) / len(notas), 2)
    else:  # nao_aplicavel — Zwisch: guarda o nível declarado
        valor = float(max(notas))

    faixa = next((f for f in instrumento.faixas if f.contem(valor)), None)

    return Resultado(
        valor=valor,
        agregacao=instrumento.agregacao,
        total_minimo=instrumento.total_minimo,
        total_maximo=instrumento.total_maximo,
        faixa_rotulo=faixa.rotulo if faixa else None,
        faixa_descricao=faixa.descricao if faixa else None,
    )


def validar_zwisch(instrumento: Instrumento, etapa_cirurgica: str | None, nivel: int | None) -> None:
    """Zwisch não usa `validar_itens` — é etapa + nível, não domínio + soma."""
    if not etapa_cirurgica or not etapa_cirurgica.strip():
        raise ItensInvalidos("A Zwisch exige a etapa cirúrgica observada.")

    if nivel is None:
        raise ItensInvalidos("A Zwisch exige o nível de autonomia (Z1 a Z4).")

    if not (instrumento.escala_min <= nivel <= instrumento.escala_max):
        raise ItensInvalidos(
            f"Nível {nivel} fora da escala da Zwisch: "
            f"{instrumento.escala_min} a {instrumento.escala_max}."
        )


def resultado_zwisch(instrumento: Instrumento, nivel: int) -> Resultado:
    """O 'resultado' da Zwisch é o próprio nível declarado — não há soma."""
    return Resultado(
        valor=float(nivel),
        agregacao=instrumento.agregacao,
        total_minimo=instrumento.escala_min,
        total_maximo=instrumento.escala_max,
        faixa_rotulo=f"Z{nivel}",
        faixa_descricao=instrumento.ancora_escala.get(nivel),
    )
