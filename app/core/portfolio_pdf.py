"""Exportação do portfólio do residente em PDF.

Recebe o dicionário de `app.core.portfolio.montar_portfolio` e devolve os
bytes de um PDF A4 pronto para compartilhar. Usa ReportLab (Python puro,
instala com `pip` em qualquer sistema — sem dependência de sistema como
Cairo/Pango, que o WeasyPrint exigiria).

Estrutura do documento:
    1. Cabeçalho com identificação do residente + números-resumo
    2. Mapa das EPAs (esperado × atual)
    3. Desempenho por instrumento (evolução + média por domínio)
    4. Zwisch — autonomia por etapa cirúrgica
    5. Procedimentos realizados (somente validados)
    6. Histórico de avaliações com feedback e código de integridade
"""
from __future__ import annotations

import io
from datetime import date, datetime, timedelta, timezone
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Circle, Drawing, Line, PolyLine, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    CondPageBreak,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Identidade visual (mesmas cores de frontend/style.css)
# ---------------------------------------------------------------------------
TINTA = colors.HexColor("#13262D")
TINTA_FRACA = colors.HexColor("#53686E")
CIRURGICO = colors.HexColor("#0F6157")
CIRURGICO_ESCURO = colors.HexColor("#0A4740")
CIRURGICO_CLARO = colors.HexColor("#9FC8C0")
PAPEL = colors.HexColor("#EAEEEC")
BORDA = colors.HexColor("#C3CFCB")
ALERTA = colors.HexColor("#8C2B22")
ATENCAO = colors.HexColor("#A86400")
VAZIO = colors.HexColor("#E3E8E6")

# Fundo das faixas de corte nos gráficos (da mais baixa para a mais alta).
TONS_FAIXA = [
    colors.HexColor("#F6E9E7"),
    colors.HexColor("#F5F0E1"),
    colors.HexColor("#E2F0EC"),
]

FUSO_BRASILIA = timezone(timedelta(hours=-3))  # Brasil sem horário de verão desde 2019

MARGEM = 18 * mm
LARGURA_PAGINA, ALTURA_PAGINA = A4
LARGURA_UTIL = LARGURA_PAGINA - 2 * MARGEM

COR_SITUACAO = {
    "atingido": CIRURGICO, "abaixo": ATENCAO, "sem_nivel": TINTA_FRACA, "sem_referencia": TINTA_FRACA,
}
TEXTO_SITUACAO = {
    "atingido": "No nível", "abaixo": "Abaixo", "sem_nivel": "Sem registro", "sem_referencia": "Sem ano",
}
DESTAQUE_ANO = colors.HexColor("#D9ECE7")


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
def _limpo(texto) -> str:
    """Escapa XML e troca caracteres que as fontes padrão do PDF não têm."""
    if texto is None:
        return ""
    texto = str(texto)
    texto = texto.encode("cp1252", errors="replace").decode("cp1252")
    return escape(texto)


def _estilos() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9.5, leading=13, textColor=TINTA)
    return {
        "base": base,
        "fraco": ParagraphStyle("fraco", parent=base, textColor=TINTA_FRACA, fontSize=8.5, leading=11),
        "pequeno": ParagraphStyle("pequeno", parent=base, fontSize=8, leading=10),
        "celula": ParagraphStyle("celula", parent=base, fontSize=8.5, leading=10.5),
        "celula_negrito": ParagraphStyle(
            "celula_negrito", parent=base, fontName="Helvetica-Bold", fontSize=8.5, leading=10.5
        ),
        "feedback": ParagraphStyle(
            "feedback", parent=base, fontName="Helvetica-Oblique", fontSize=8.3, leading=10.5,
            textColor=TINTA_FRACA,
        ),
        "secao": ParagraphStyle(
            "secao", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=16,
            textColor=CIRURGICO_ESCURO, spaceBefore=4, spaceAfter=2,
        ),
        "subsecao": ParagraphStyle(
            "subsecao", parent=base, fontName="Helvetica-Bold", fontSize=10.5, leading=13,
            spaceBefore=2, spaceAfter=1,
        ),
        "nome": ParagraphStyle(
            "nome", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24,
            textColor=colors.white,
        ),
        "capa": ParagraphStyle(
            "capa", parent=base, fontSize=9.5, leading=13, textColor=colors.HexColor("#D7E6E2"),
        ),
        "rotulo_capa": ParagraphStyle(
            "rotulo_capa", parent=base, fontName="Helvetica-Bold", fontSize=7.5, leading=10,
            textColor=CIRURGICO_CLARO,
        ),
        "kpi_numero": ParagraphStyle(
            "kpi_numero", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=21,
            textColor=CIRURGICO_ESCURO, alignment=TA_LEFT,
        ),
        "kpi_rotulo": ParagraphStyle(
            "kpi_rotulo", parent=base, fontSize=8, leading=10, textColor=TINTA_FRACA,
        ),
    }


def _dt_local(valor) -> datetime | None:
    if valor is None:
        return None
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor)
    if valor.tzinfo is None:  # SQLite devolve sem fuso; o banco grava em UTC
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(FUSO_BRASILIA)


def _data(valor) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y")
    return _dt_local(valor).strftime("%d/%m/%Y")


def _data_curta(valor) -> str:
    return _dt_local(valor).strftime("%d/%m")


def _numero(valor, casas: int = 1) -> str:
    if valor is None:
        return "—"
    if float(valor).is_integer():
        return str(int(valor))
    return f"{valor:.{casas}f}".replace(".", ",")


# ---------------------------------------------------------------------------
# Página: rodapé com "Página X de Y" e cabeçalho a partir da página 2
# ---------------------------------------------------------------------------
def _fabrica_canvas(nome_residente: str, gerado_em: str):
    class CanvasNumerado(rl_canvas.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._paginas: list[dict] = []

        def showPage(self):  # noqa: N802 (API do ReportLab)
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self._decorar(total)
                super().showPage()
            super().save()

        def _decorar(self, total: int) -> None:
            pagina = self._pageNumber
            self.setStrokeColor(BORDA)
            self.setLineWidth(0.5)
            self.line(MARGEM, 13 * mm, LARGURA_PAGINA - MARGEM, 13 * mm)
            self.setFont("Helvetica", 7.5)
            self.setFillColor(TINTA_FRACA)
            self.drawString(
                MARGEM, 9 * mm,
                _limpo_canvas(
                    f"Portfólio do residente · {nome_residente} · gerado em {gerado_em}"
                ),
            )
            self.drawRightString(
                LARGURA_PAGINA - MARGEM, 9 * mm, f"Página {pagina} de {total}"
            )
            self.drawString(
                MARGEM, 5.5 * mm,
                "Somente registros confirmados. Cada avaliação é imutável e identificada "
                "por hash SHA-256 (coluna Integridade).",
            )
            if pagina > 1:
                self.setFillColor(CIRURGICO)
                self.rect(0, ALTURA_PAGINA - 4 * mm, LARGURA_PAGINA, 4 * mm, stroke=0, fill=1)
                self.setFillColor(TINTA_FRACA)
                self.setFont("Helvetica", 7.5)
                self.drawRightString(
                    LARGURA_PAGINA - MARGEM, ALTURA_PAGINA - 10 * mm,
                    _limpo_canvas(nome_residente),
                )

    return CanvasNumerado


def _limpo_canvas(texto: str) -> str:
    return str(texto).encode("cp1252", errors="replace").decode("cp1252")


# ---------------------------------------------------------------------------
# Desenhos
# ---------------------------------------------------------------------------
def _segmentos(atual: int | None, esperado: int | None, total: int, cor: colors.Color,
               largura_seg: float = 6.2 * mm, altura: float = 3.6 * mm) -> Drawing:
    """Barra de `total` blocos: preenche até `atual`, marca `esperado`."""
    espaco = 1.2
    desenho = Drawing(total * (largura_seg + espaco), altura + 4)
    for i in range(1, total + 1):
        x = (i - 1) * (largura_seg + espaco)
        preenchido = atual is not None and i <= atual
        desenho.add(
            Rect(x, 0, largura_seg, altura, fillColor=cor if preenchido else VAZIO,
                 strokeColor=None, strokeWidth=0)
        )
        if esperado is not None and i == esperado:
            desenho.add(
                Rect(x - 0.6, -0.6, largura_seg + 1.2, altura + 1.2, fillColor=None,
                     strokeColor=TINTA, strokeWidth=1.1)
            )
            meio = x + largura_seg / 2
            desenho.add(
                Polygon([meio - 2.4, altura + 4, meio + 2.4, altura + 4, meio, altura + 1],
                        fillColor=TINTA, strokeColor=None)
            )
    return desenho


def _grafico_evolucao(inst: dict, largura: float, altura: float = 46 * mm) -> Drawing:
    desenho = Drawing(largura, altura)
    esq, dir_, base, topo = 24, 70, 16, 8
    area_l = largura - esq - dir_
    area_a = altura - base - topo

    y_min = inst["total_minimo"] if inst["agregacao"] == "soma" else inst["escala_min"]
    y_max = inst["total_maximo"] if inst["agregacao"] == "soma" else inst["escala_max"]
    faixa_y = (y_max - y_min) or 1

    def y_de(valor: float) -> float:
        return base + (valor - y_min) / faixa_y * area_a

    # Faixas de corte ao fundo, com o nome à direita
    faixas = inst["faixas"]
    for i, faixa in enumerate(faixas):
        # cada faixa vai do seu mínimo até o mínimo da próxima (sem buracos)
        y0 = y_de(y_min if i == 0 else faixa["minimo"])
        y1 = y_de(faixas[i + 1]["minimo"] if i + 1 < len(faixas) else y_max)
        desenho.add(Rect(esq, y0, area_l, y1 - y0,
                         fillColor=TONS_FAIXA[min(i, len(TONS_FAIXA) - 1)], strokeColor=None))
        desenho.add(String(esq + area_l + 4, (y0 + y1) / 2 - 2.5, _limpo_canvas(faixa["texto"] or ""),
                           fontName="Helvetica", fontSize=6.3, fillColor=TINTA_FRACA))
    if not faixas:
        desenho.add(Rect(esq, base, area_l, area_a, fillColor=colors.HexColor("#F4F6F5"), strokeColor=None))

    # Eixo Y: mínimo, máximo e cortes
    marcas = {y_min, y_max} | {f["minimo"] for f in faixas}
    for valor in sorted(marcas):
        y = y_de(valor)
        desenho.add(Line(esq, y, esq + area_l, y, strokeColor=colors.white, strokeWidth=0.6))
        desenho.add(String(esq - 4, y - 2.5, _numero(valor), fontName="Helvetica", fontSize=6.5,
                           fillColor=TINTA_FRACA, textAnchor="end"))
    desenho.add(Line(esq, base, esq + area_l, base, strokeColor=BORDA, strokeWidth=0.6))

    pontos = inst["evolucao"]
    n = len(pontos)
    if n == 1:
        xs = [esq + area_l / 2]
    else:
        xs = [esq + 10 + i * (area_l - 20) / (n - 1) for i in range(n)]
    ys = [y_de(p["nota"]) for p in pontos]

    if n > 1:
        coordenadas = [v for par in zip(xs, ys) for v in par]
        desenho.add(PolyLine(coordenadas, strokeColor=CIRURGICO, strokeWidth=1.6))

    rotular_todos = n <= 12
    for i, (x, y, p) in enumerate(zip(xs, ys, pontos)):
        desenho.add(Circle(x, y, 2.4, fillColor=CIRURGICO_ESCURO, strokeColor=colors.white, strokeWidth=0.8))
        if rotular_todos or i in (0, n - 1):
            desenho.add(String(x, y + 4.5, _numero(p["nota"]), fontName="Helvetica-Bold", fontSize=6.8,
                               fillColor=TINTA, textAnchor="middle"))
        if rotular_todos or i % max(1, n // 8) == 0 or i == n - 1:
            desenho.add(String(x, base - 9, _data_curta(p["data"]), fontName="Helvetica", fontSize=6.3,
                               fillColor=TINTA_FRACA, textAnchor="middle"))
    return desenho


def _grafico_dominios(inst: dict, largura: float) -> Drawing:
    linhas = inst["media_por_dominio"]
    altura_linha = 12
    rotulo_l = 58 * mm
    valor_l = 14 * mm
    trilho_l = largura - rotulo_l - valor_l
    altura = altura_linha * len(linhas) + 12
    desenho = Drawing(largura, altura)

    minimo, maximo = inst["escala_min"], inst["escala_max"]
    for i, linha in enumerate(linhas):
        y = altura - 12 - i * altura_linha
        desenho.add(String(0, y + 1.5, _limpo_canvas(linha["titulo"]), fontName="Helvetica", fontSize=7.5,
                           fillColor=TINTA))
        desenho.add(Rect(rotulo_l, y, trilho_l, 7, fillColor=VAZIO, strokeColor=None))
        if linha["media"] is not None:
            proporcao = (linha["media"] - minimo) / ((maximo - minimo) or 1)
            desenho.add(Rect(rotulo_l, y, max(1.5, trilho_l * proporcao), 7, fillColor=CIRURGICO,
                             strokeColor=None))
        desenho.add(String(largura, y + 1.5, f"{_numero(linha['media'])} / {maximo}",
                           fontName="Helvetica-Bold", fontSize=7.5, fillColor=TINTA, textAnchor="end"))
    desenho.add(String(rotulo_l, 0, f"Média por domínio (escala {minimo} a {maximo})",
                       fontName="Helvetica", fontSize=6.5, fillColor=TINTA_FRACA))
    return desenho


# ---------------------------------------------------------------------------
# Blocos do documento
# ---------------------------------------------------------------------------
def _tabela_base(dados, larguras, cabecalho: bool = True, extras: list | None = None) -> Table:
    tabela = Table(dados, colWidths=larguras, repeatRows=1 if cabecalho else 0)
    estilo = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORDA),
    ]
    if cabecalho:
        estilo += [
            ("BACKGROUND", (0, 0), (-1, 0), PAPEL),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, CIRURGICO),
        ]
    tabela.setStyle(TableStyle(estilo + (extras or [])))
    return tabela


def _cab(texto: str, e: dict) -> Paragraph:
    return Paragraph(f"<b>{_limpo(texto)}</b>", e["pequeno"])


def _bloco_capa(p: dict, e: dict) -> list:
    r = p["residente"]
    resumo = p["resumo"]

    periodo = "Sem avaliações confirmadas"
    if resumo["primeira_avaliacao"]:
        periodo = f"{_data(resumo['primeira_avaliacao'])} a {_data(resumo['ultima_avaliacao'])}"

    ident = [
        [Paragraph("PORTFÓLIO DO RESIDENTE", e["rotulo_capa"])],
        [Paragraph(_limpo(r["nome"]), e["nome"])],
        [Paragraph(
            " · ".join(_limpo(x) for x in (r["programa"], r["instituicao"]) if x) or "Programa não informado",
            e["capa"],
        )],
        [Paragraph(
            f"Especialidade: {_limpo(r['especialidade'] or '—')} &nbsp;&nbsp;|&nbsp;&nbsp; "
            + (f"Ano: {_limpo(r['ano_residencia'])} &nbsp;&nbsp;|&nbsp;&nbsp; " if r.get("ano_residencia") else "")
            + f"Período avaliado: {_limpo(periodo)} &nbsp;&nbsp;|&nbsp;&nbsp; {_limpo(r['email'])}",
            e["capa"],
        )],
    ]
    faixa = Table(ident, colWidths=[LARGURA_UTIL])
    faixa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CIRURGICO_ESCURO),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, 0), 14),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
    ]))

    epas_txt = (
        f"{resumo['epas_atingidas']}/{resumo['epas_total']}" if resumo["epas_comparavel"] else "—"
    )
    kpis = [
        (str(resumo["total_avaliacoes"]), "avaliações confirmadas"),
        (str(resumo["instrumentos_utilizados"]), "instrumentos utilizados"),
        (str(resumo["procedimentos_validados"]), "procedimentos validados"),
        (epas_txt, "EPAs no nível esperado"),
    ]
    celulas = [[
        [Paragraph(numero, e["kpi_numero"]), Paragraph(rotulo, e["kpi_rotulo"])]
        for numero, rotulo in kpis
    ]]
    largura_kpi = (LARGURA_UTIL - 3 * 6) / 4
    tabela_kpi = Table(celulas, colWidths=[largura_kpi] * 4, spaceBefore=8)
    tabela_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPEL),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEBEFORE", (1, 0), (-1, -1), 6, colors.white),
    ]))
    return [faixa, tabela_kpi, Spacer(1, 10)]


def _titulo_secao(numero: int, texto: str, e: dict) -> list:
    return [
        CondPageBreak(40 * mm),
        Paragraph(f"{numero}. {_limpo(texto)}", e["secao"]),
        Table([[""]], colWidths=[LARGURA_UTIL], rowHeights=[1.2],
              style=[("LINEABOVE", (0, 0), (-1, -1), 1.2, CIRURGICO)]),
        Spacer(1, 5),
    ]


def _caixa_aviso(texto: str, e: dict) -> Table:
    caixa = Table([[Paragraph(_limpo(texto), e["fraco"])]], colWidths=[LARGURA_UTIL])
    caixa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PAPEL),
        ("LINEBEFORE", (0, 0), (0, -1), 3, BORDA),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return caixa


def _bloco_epas(p: dict, e: dict, numero: int) -> list:
    epas = p["epas"]
    partes = _titulo_secao(numero, "Mapa das EPAs", e)
    if not epas["itens"]:
        partes.append(_caixa_aviso(epas["mensagem"] or "Sem EPAs para exibir.", e))
        partes.append(Spacer(1, 10))
        return partes

    anos = epas["anos"]
    ano_atual = epas["ano_residente"]
    comparar = epas["niveis_do_sistema"]

    if epas["mensagem"]:
        partes.append(_caixa_aviso(epas["mensagem"], e))
        partes.append(Spacer(1, 5))

    if comparar:
        partes.append(Paragraph(
            "Barra preenchida = nível atual na EPA. Bloco contornado com seta = nível esperado ao fim do "
            + (f"<b>{_limpo(ano_atual)}</b>, ano atual do residente." if ano_atual else "ano (ano não informado).")
            + " Colunas R1–R3 = trajetória esperada pelo documento.",
            e["fraco"],
        ))
    else:
        partes.append(Paragraph(
            "Nível de autonomia esperado ao fim de cada ano, conforme o documento das EPAs.",
            e["fraco"],
        ))
    partes.append(Spacer(1, 4))

    col_ano = 8 * mm
    if comparar:
        fixas = [14 * mm, 0, *[col_ano] * len(anos), 36 * mm, 17 * mm, 19 * mm]
        cabecalho = ["EPA", "Atividade", *anos, "Nível atual", "Obs. trim.*", "Situação"]
    else:
        fixas = [14 * mm, 0, *[col_ano] * len(anos), 30 * mm]
        cabecalho = ["EPA", "Atividade", *anos, "Mínimo p/ certificar"]
    fixas[1] = LARGURA_UTIL - sum(fixas)
    n_col = len(fixas)
    primeira_ano = 2

    dados = [[_cab(t, e) for t in cabecalho]]
    extras = [("ALIGN", (primeira_ano, 0), (primeira_ano + len(anos) - 1, -1), "CENTER")]
    if ano_atual in anos:
        c = primeira_ano + anos.index(ano_atual)
        extras.append(("BACKGROUND", (c, 0), (c, -1), DESTAQUE_ANO))

    especialidade_atual = None
    for item in epas["itens"]:
        if item.get("especialidade") and item["especialidade"] != especialidade_atual:
            especialidade_atual = item["especialidade"]
            dados.append([Paragraph(f"<b>{_limpo(especialidade_atual)}</b>", e["celula"])] + [""] * (n_col - 1))
            linha = len(dados) - 1
            extras += [
                ("SPAN", (0, linha), (-1, linha)),
                ("BACKGROUND", (0, linha), (-1, linha), colors.HexColor("#F4F6F5")),
            ]

        esperados = [
            Paragraph(str(item["niveis_esperados"].get(ano, "—")), e["celula"]) for ano in anos
        ]
        linha = [
            Paragraph(_limpo(item["codigo"]), e["celula_negrito"]),
            Paragraph(_limpo(item["nome"]), e["celula"]),
            *esperados,
        ]
        if comparar:
            cor = COR_SITUACAO[item["situacao"]]
            obs = "—"
            if item["observacoes_trimestre"] is not None:
                obs = str(item["observacoes_trimestre"])
                if item["minimo_trimestre"]:
                    obs += f" / {item['minimo_trimestre']}"
            linha += [
                _segmentos(item["nivel_atual"], item["nivel_esperado"], 5, cor, largura_seg=5.4 * mm),
                Paragraph(obs, e["celula"]),
                Paragraph(f'<font color="{cor.hexval()}"><b>{TEXTO_SITUACAO[item["situacao"]]}</b></font>', e["celula"]),
            ]
        else:
            minimo = f"{item['minimo_trimestre']} vezes / trimestre" if item["minimo_trimestre"] else "Regra própria**"
            linha.append(Paragraph(minimo, e["celula"]))
        dados.append(linha)

    partes.append(_tabela_base(dados, fixas, extras=extras))
    partes.append(Spacer(1, 3))

    notas = []
    if comparar:
        notas.append("* Observações no trimestre / mínimo do documento para a certificação pelo CCC.")
    especiais = [i for i in epas["itens"] if not i["minimo_trimestre"] and i.get("regra_minimo")]
    for item in especiais:
        notas.append(f"{'' if comparar else '** '}{_limpo(item['codigo'])}: {_limpo(item['regra_minimo'])}")
    niveis = " · ".join(f"{n} = {_limpo(t)}" for n, t in epas["niveis"].items())
    notas.append(f"Níveis de confiança: {niveis}.")
    notas.append(f"Fonte: {_limpo(epas['fonte'])}.")
    for nota in notas:
        partes.append(Paragraph(nota, e["fraco"]))
    partes.append(Spacer(1, 12))
    return partes


def _bloco_instrumentos(p: dict, e: dict, numero: int) -> list:
    partes = _titulo_secao(numero, "Desempenho por instrumento", e)
    if not p["instrumentos"]:
        partes.append(_caixa_aviso("Nenhuma avaliação OSATS, Mini-CEX ou NOTSS confirmada até o momento.", e))
        partes.append(Spacer(1, 10))
        return partes

    for indice, inst in enumerate(p["instrumentos"]):
        escala = (
            f"soma de {len(inst['media_por_dominio'])} domínios, {inst['total_minimo']} a {inst['total_maximo']}"
            if inst["agregacao"] == "soma" else f"média, {inst['escala_min']} a {inst['escala_max']}"
        )
        estatisticas = (
            f"{inst['quantidade']} avaliação(ões) · média <b>{_numero(inst['media'])}</b> · "
            f"última <b>{_numero(inst['ultima_nota'])}</b>"
            + (f" ({_limpo(inst['ultima_faixa'])})" if inst["ultima_faixa"] else "")
            + f" · melhor <b>{_numero(inst['melhor'])}</b>"
        )
        bloco = [
            Paragraph(f"{_limpo(inst['nome'])} <font size=8 color='#53686E'>— {_limpo(escala)}</font>", e["subsecao"]),
            Paragraph(estatisticas, e["fraco"]),
            Spacer(1, 4),
            _grafico_evolucao(inst, LARGURA_UTIL),
            Spacer(1, 6),
            _grafico_dominios(inst, LARGURA_UTIL),
        ]
        if inst["faixas"]:
            contagem = " · ".join(
                f"{_limpo(f['texto'])} ({_numero(f['minimo'])}–{_numero(f['maximo'])}): <b>{f['quantidade']}</b>"
                for f in inst["faixas"]
            )
            bloco += [Spacer(1, 4), Paragraph(f"Distribuição por faixa: {contagem}", e["fraco"])]
        elif inst["codigo"] == "notss":
            bloco += [Spacer(1, 4), Paragraph("NOTSS ainda sem faixas de corte definidas no documento técnico.", e["fraco"])]
        bloco.append(Spacer(1, 12))
        if indice == 0:
            # título da seção nunca fica sozinho no pé da página
            partes = [KeepTogether(partes + bloco)]
        else:
            partes.append(KeepTogether(bloco))
    return partes


def _bloco_zwisch(p: dict, e: dict, numero: int) -> list:
    if not p["zwisch"]:
        return []
    partes = _titulo_secao(numero, "Autonomia cirúrgica por etapa (Zwisch)", e)
    partes.append(Paragraph(
        "Nível mais recente observado em cada etapa. Z1 show and tell · Z2 active help · "
        "Z3 passive help · Z4 supervision only.",
        e["fraco"],
    ))
    partes.append(Spacer(1, 4))
    larguras = [62 * mm, 32 * mm, 40 * mm, 12 * mm, LARGURA_UTIL - 146 * mm]
    dados = [[_cab(t, e) for t in ("Etapa cirúrgica", "Nível atual", "Histórico", "Nº", "Última")]]
    for etapa in p["zwisch"]:
        dados.append([
            Paragraph(_limpo(etapa["etapa"]), e["celula"]),
            _segmentos(etapa["nivel_atual"], None, 4, CIRURGICO, largura_seg=5.5 * mm),
            Paragraph(" → ".join(f"Z{n}" for n in etapa["historico"][-5:]), e["celula"]),
            Paragraph(str(etapa["quantidade"]), e["celula"]),
            Paragraph(_data(etapa["ultima_data"]), e["celula"]),
        ])
    partes.append(_tabela_base(dados, larguras))
    partes.append(Spacer(1, 12))
    return partes


def _bloco_procedimentos(p: dict, e: dict, numero: int) -> list:
    proc = p["procedimentos"]
    partes = _titulo_secao(numero, "Procedimentos realizados", e)

    resumo = " · ".join(
        f"{_limpo(c['texto'])}: <b>{c['quantidade']}</b>" for c in proc["por_participacao"]
    )
    partes.append(Paragraph(
        f"<b>{proc['total_validados']}</b> procedimento(s) validado(s) por preceptor — {resumo}. "
        f"Não contam na estatística: {proc['pendentes']} pendente(s) de validação e "
        f"{proc['recusados']} recusado(s).",
        e["fraco"],
    ))
    partes.append(Spacer(1, 5))

    if not proc["por_nome"]:
        partes.append(_caixa_aviso("Nenhum procedimento validado até o momento.", e))
        partes.append(Spacer(1, 10))
        return partes

    larguras = [LARGURA_UTIL - 4 * 24 * mm, 24 * mm, 24 * mm, 24 * mm, 24 * mm]
    dados = [[_cab(t, e) for t in ("Procedimento", "Total", "Cirurgião principal", "1º auxiliar", "2º auxiliar")]]
    for linha in proc["por_nome"]:
        dados.append([
            Paragraph(_limpo(linha["nome"]), e["celula"]),
            Paragraph(f"<b>{linha['total']}</b>", e["celula"]),
            Paragraph(str(linha["cirurgiao_principal"]), e["celula"]),
            Paragraph(str(linha["primeiro_auxiliar"]), e["celula"]),
            Paragraph(str(linha["segundo_auxiliar"]), e["celula"]),
        ])
    partes.append(_tabela_base(dados, larguras))
    partes.append(Spacer(1, 12))
    return partes


def _bloco_historico(p: dict, e: dict, numero: int) -> list:
    partes = _titulo_secao(numero, "Histórico de avaliações e feedback", e)
    if not p["avaliacoes"]:
        partes.append(_caixa_aviso("Nenhuma avaliação confirmada até o momento.", e))
        return partes

    larguras = [18 * mm, 20 * mm, 38 * mm, 18 * mm, 48 * mm, LARGURA_UTIL - 142 * mm]
    dados = [[_cab(t, e) for t in ("Data", "Instrumento", "Avaliador", "Resultado", "Faixa / etapa", "Integridade")]]
    extras = []
    for a in p["avaliacoes"]:
        if a["instrumento"] == "zwisch":
            resultado = f"Z{int(a['nota'])}"
            faixa = f"{_limpo(a['etapa_cirurgica'] or '')}"
        else:
            resultado = f"{_numero(a['nota'])}/{a['total_maximo']}"
            faixa = _limpo(a["faixa_texto"] or "—")
        integridade = (a["hash_integridade"] or "")[:12]
        dados.append([
            Paragraph(_data(a["data"]), e["celula"]),
            Paragraph(_limpo(a["instrumento_nome"]), e["celula_negrito"]),
            Paragraph(_limpo(a["avaliador_nome"]), e["celula"]),
            Paragraph(f"<b>{resultado}</b>", e["celula"]),
            Paragraph(faixa, e["celula"]),
            Paragraph(f'<font face="Courier" size="7">{integridade}</font>', e["celula"]),
        ])
        if a["observacoes"].strip():
            dados.append([Paragraph(f"“{_limpo(a['observacoes'].strip())}”", e["feedback"]), "", "", "", "", ""])
            linha = len(dados) - 1
            extras += [
                ("SPAN", (0, linha), (-1, linha)),
                ("LINEBELOW", (0, linha - 1), (-1, linha - 1), 0, colors.white),
                ("TOPPADDING", (0, linha), (-1, linha), 0),
                ("LEFTPADDING", (0, linha), (-1, linha), 10),
            ]
    partes.append(_tabela_base(dados, larguras, extras=extras))
    return partes


# ---------------------------------------------------------------------------
# API do módulo
# ---------------------------------------------------------------------------
def gerar_pdf_portfolio(portfolio: dict) -> bytes:
    e = _estilos()
    gerado_em = _dt_local(portfolio["gerado_em"]).strftime("%d/%m/%Y %H:%M")
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        topMargin=16 * mm,
        bottomMargin=20 * mm,
        title=f"Portfólio — {portfolio['residente']['nome']}",
        author="Sistema de Residência Médica",
        subject="Portfólio do residente",
    )

    historia: list = []
    historia += _bloco_capa(portfolio, e)
    numero = 1
    for bloco in (_bloco_epas, _bloco_instrumentos, _bloco_zwisch, _bloco_procedimentos, _bloco_historico):
        partes = bloco(portfolio, e, numero)
        if partes:
            historia += partes
            numero += 1

    doc.build(historia, canvasmaker=_fabrica_canvas(portfolio["residente"]["nome"], gerado_em))
    return buffer.getvalue()
