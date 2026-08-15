import audit_log
from confirmar_avaliacao import confirmar_registro


def test_confirmar_registro_gera_hash_e_bloqueia(tmp_path, monkeypatch):
    arquivo_temp = tmp_path / "audit_log.json"
    arquivo_temp.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(audit_log, "AUDIT_LOG", str(arquivo_temp))

    registro = {"id": 1, "nota": 8, "confirmado": False}

    confirmar_registro(
        registro=registro,
        campos_para_hash={"id": 1, "nota": 8},
        usuario_id=1,
        tabela_afetada="avaliacao",
        ip_origem="127.0.0.1",
    )

    assert registro["confirmado"] is True
    assert registro["hash_integridade"] is not None


def test_confirmar_registro_ja_confirmado_gera_erro(tmp_path, monkeypatch):
    arquivo_temp = tmp_path / "audit_log.json"
    arquivo_temp.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(audit_log, "AUDIT_LOG", str(arquivo_temp))

    registro = {"id": 2, "nota": 9, "confirmado": True}

    try:
        confirmar_registro(
            registro=registro,
            campos_para_hash={"id": 2, "nota": 9},
            usuario_id=1,
            tabela_afetada="avaliacao",
        )
        assert False, "Deveria ter levantado erro"
    except ValueError:
        pass