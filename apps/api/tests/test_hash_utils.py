from app.utils.hash_utils import gerar_hash_registro


def test_hash_e_deterministico():
    dados_a = {"nota": 8, "residente_id": 1, "preceptor_id": 2}
    dados_b = {"preceptor_id": 2, "nota": 8, "residente_id": 1}  # ordem diferente
    assert gerar_hash_registro(dados_a) == gerar_hash_registro(dados_b)


def test_hash_muda_se_dado_mudar():
    dados_a = {"nota": 8, "residente_id": 1}
    dados_b = {"nota": 9, "residente_id": 1}
    assert gerar_hash_registro(dados_a) != gerar_hash_registro(dados_b)