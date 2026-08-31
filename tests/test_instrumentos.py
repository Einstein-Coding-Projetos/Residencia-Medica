"""Testes da camada de instrumentos — escala, domínios e cálculo de nota.

Cobre principalmente OSATS e Mini-CEX (frente A), mais as garantias gerais
que valem para os cinco instrumentos.
"""

import pytest

from app.core.instrumentos import (
    INSTRUMENTOS,
    InstrumentoDesconhecido,
    ItensInvalidos,
    calcular_resultado,
    obter_instrumento,
    validar_itens,
)


class ItemFalso:
    def __init__(self, dominio: str, nota: int):
        self.dominio = dominio
        self.nota = nota


def _ficha_completa(codigo: str, nota: int) -> list[ItemFalso]:
    instrumento = obter_instrumento(codigo)
    return [ItemFalso(d.codigo, nota) for d in instrumento.dominios]


# --------------------------------------------------------------------------
# Registro
# --------------------------------------------------------------------------
def test_os_cinco_instrumentos_estao_registrados():
    assert set(INSTRUMENTOS) == {
        "osats",
        "mini_cex",
        "notss",
        "zwisch",
        "setq_smart",
    }


def test_instrumento_inexistente_levanta_erro():
    with pytest.raises(InstrumentoDesconhecido):
        obter_instrumento("osatz")


# --------------------------------------------------------------------------
# OSATS — 7 domínios, escala 1–5, total 7–35
# --------------------------------------------------------------------------
def test_osats_tem_sete_dominios_e_total_de_7_a_35():
    osats = obter_instrumento("osats")
    assert len(osats.dominios) == 7
    assert (osats.escala_min, osats.escala_max) == (1, 5)
    assert (osats.total_minimo, osats.total_maximo) == (7, 35)


@pytest.mark.parametrize(
    "nota_por_dominio, total_esperado, faixa_esperada",
    [
        (1, 7, "supervisao_direta"),
        (2, 14, "supervisao_direta"),
        (3, 21, "assistencia_ocasional"),
        (4, 28, "autonomia_supervisionada"),
        (5, 35, "autonomia_supervisionada"),
    ],
)
def test_osats_soma_e_classifica_na_faixa_certa(
    nota_por_dominio, total_esperado, faixa_esperada
):
    osats = obter_instrumento("osats")
    itens = _ficha_completa("osats", nota_por_dominio)
    resultado = calcular_resultado(osats, itens)

    assert resultado.valor == total_esperado
    assert resultado.faixa_rotulo == faixa_esperada


def test_osats_usa_soma_e_nao_media():
    """Regressão: a implementação anterior devolvia a média (1–5)."""
    osats = obter_instrumento("osats")
    resultado = calcular_resultado(osats, _ficha_completa("osats", 4))
    assert resultado.valor == 28
    assert resultado.valor != 4


def test_osats_rejeita_nota_fora_da_escala():
    osats = obter_instrumento("osats")
    itens = _ficha_completa("osats", 3)
    itens[0].nota = 6
    with pytest.raises(ItensInvalidos):
        validar_itens(osats, itens)


def test_osats_exige_os_sete_dominios():
    osats = obter_instrumento("osats")
    itens = _ficha_completa("osats", 3)[:5]
    with pytest.raises(ItensInvalidos) as erro:
        validar_itens(osats, itens)
    assert "Faltando" in str(erro.value)


# --------------------------------------------------------------------------
# Mini-CEX — 5 domínios, escala 1–9, total 5–45
# --------------------------------------------------------------------------
def test_mini_cex_tem_cinco_dominios_e_total_de_5_a_45():
    mini = obter_instrumento("mini_cex")
    assert len(mini.dominios) == 5
    assert (mini.escala_min, mini.escala_max) == (1, 9)
    assert (mini.total_minimo, mini.total_maximo) == (5, 45)


def test_mini_cex_aceita_nota_9():
    """Regressão: o schema anterior travava em ge=1, le=5 e barrava o Mini-CEX."""
    mini = obter_instrumento("mini_cex")
    itens = _ficha_completa("mini_cex", 9)
    validar_itens(mini, itens)  # não deve levantar
    assert calcular_resultado(mini, itens).valor == 45


def test_mini_cex_corte_de_35_e_satisfatorio():
    mini = obter_instrumento("mini_cex")
    itens = _ficha_completa("mini_cex", 7)  # 7 x 5 = 35
    resultado = calcular_resultado(mini, itens)
    assert resultado.valor == 35
    assert resultado.faixa_rotulo == "satisfatorio"


def test_mini_cex_abaixo_de_35_nao_e_satisfatorio():
    mini = obter_instrumento("mini_cex")
    itens = _ficha_completa("mini_cex", 6)  # 6 x 5 = 30
    resultado = calcular_resultado(mini, itens)
    assert resultado.valor == 30
    assert resultado.faixa_rotulo != "satisfatorio"


def test_mini_cex_rejeita_nota_10():
    mini = obter_instrumento("mini_cex")
    itens = _ficha_completa("mini_cex", 5)
    itens[0].nota = 10
    with pytest.raises(ItensInvalidos):
        validar_itens(mini, itens)


# --------------------------------------------------------------------------
# Garantias gerais
# --------------------------------------------------------------------------
def test_dominio_repetido_e_rejeitado():
    osats = obter_instrumento("osats")
    itens = _ficha_completa("osats", 3)
    itens[1].dominio = itens[0].dominio
    with pytest.raises(ItensInvalidos) as erro:
        validar_itens(osats, itens)
    assert "repetido" in str(erro.value)


def test_dominio_de_outro_instrumento_e_rejeitado():
    osats = obter_instrumento("osats")
    itens = _ficha_completa("osats", 3)
    itens[0].dominio = "anamnese"  # domínio do Mini-CEX
    with pytest.raises(ItensInvalidos):
        validar_itens(osats, itens)


def test_ficha_vazia_e_rejeitada():
    with pytest.raises(ItensInvalidos):
        validar_itens(obter_instrumento("osats"), [])


def test_notss_respeita_escala_de_1_a_4():
    notss = obter_instrumento("notss")
    assert (notss.escala_min, notss.escala_max) == (1, 4)
    itens = _ficha_completa("notss", 4)
    itens[0].nota = 5
    with pytest.raises(ItensInvalidos):
        validar_itens(notss, itens)


def test_zwisch_aceita_itens_livres_por_enquanto():
    """Zwisch ainda não tem modelagem própria (frente B)."""
    zwisch = obter_instrumento("zwisch")
    assert zwisch.dominios_fixos is False
    validar_itens(zwisch, [ItemFalso("dissecao_calot", 3)])


def test_setq_smart_e_anonimo():
    assert obter_instrumento("setq_smart").anonimo is True
