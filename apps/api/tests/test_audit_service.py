import json
import audit_log
from audit_service import registrar_auditoria


def test_registrar_auditoria_salva_no_arquivo(tmp_path, monkeypatch):
    arquivo_temp = tmp_path / "audit_log.json"
    arquivo_temp.write_text("[]", encoding="utf-8")

    # Redireciona o audit_log para usar o arquivo temporário
    monkeypatch.setattr(audit_log, "AUDIT_LOG", str(arquivo_temp))

    entrada = registrar_auditoria(
        usuario_id=1,
        acao="criacao",
        tabela_afetada="avaliacao",
        registro_id=42,
        ip_origem="127.0.0.1",
    )

    assert entrada["id"] == 1
    assert entrada["usuario_id"] == 1
    assert entrada["acao"] == "criacao"

    conteudo = json.loads(arquivo_temp.read_text(encoding="utf-8"))
    assert len(conteudo) == 1
    assert conteudo[0]["registro_id"] == 42