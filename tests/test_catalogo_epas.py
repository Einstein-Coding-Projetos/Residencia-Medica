"""Catálogo das EPAs conferido contra o Quadro 1 do documento (p. 15)."""

import pytest

from app.core.catalogo_epas import (
    EPAS,
    NIVEIS_ENTRUSTAMENTO,
    normalizar_codigo,
    obter_epa,
)

# (R1, R2, R3) exatamente como no Quadro 1 — revisado em 2021
QUADRO_1 = {
    1: (2, 3, 5), 2: (2, 3, 5), 3: (2, 3, 5), 4: (2, 3, 3), 5: (2, 3, 3), 6: (2, 3, 3),
    7: (2, 3, 3), 8: (2, 3, 3), 9: (1, 2, 3), 10: (1, 2, 3), 11: (1, 2, 3), 12: (3, 4, 5),
    13: (3, 4, 5), 14: (3, 4, 5), 15: (1, 2, 3), 16: (2, 3, 4),
}


def test_sao_16_epas_de_cirurgia_geral():
    assert [e.numero for e in EPAS] == list(range(1, 17))
    assert {e.especialidade for e in EPAS} == {"Cirurgia Geral"}


@pytest.mark.parametrize("numero, esperado", QUADRO_1.items())
def test_niveis_por_ano_batem_com_o_quadro_1(numero, esperado):
    epa = obter_epa(numero)
    assert tuple(epa.niveis_esperados[a] for a in ("R1", "R2", "R3")) == esperado


def test_nivel_esperado_nunca_diminui_ao_longo_dos_anos():
    for e in EPAS:
        r1, r2, r3 = (e.niveis_esperados[a] for a in ("R1", "R2", "R3"))
        assert r1 <= r2 <= r3, e.codigo


def test_minimo_de_12_por_trimestre_exceto_11_e_16():
    sem_minimo = {e.numero for e in EPAS if e.minimo_trimestre is None}
    assert sem_minimo == {11, 16}
    assert {e.minimo_trimestre for e in EPAS if e.minimo_trimestre} == {12}
    assert "gastrectomias" in obter_epa(11).regra_minimo


def test_escala_de_1_a_5():
    assert sorted(NIVEIS_ENTRUSTAMENTO) == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("entrada", [7, "7", "EPA7", "EPA 07", "epa-7", "EPA 7"])
def test_codigo_aceita_varias_grafias(entrada):
    assert normalizar_codigo(entrada) == "EPA 7"
    assert obter_epa(entrada).titulo == "Tratando do paciente com apendicite aguda"


def test_nivel_esperado_por_ano():
    epa = obter_epa(12)
    assert epa.nivel_esperado("r2") == 4
    assert epa.nivel_esperado("R4") is None and epa.nivel_esperado(None) is None
