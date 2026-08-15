from datetime import datetime, timezone

from audit_log import ler_audit_log, salvar_audit_log


def registrar_auditoria(usuario_id, acao, tabela_afetada, registro_id, ip_origem=None):
   
    lista = ler_audit_log()

    novo_id = max([item["id"] for item in lista], default=0) + 1

    entrada = {
        "id": novo_id,
        "usuario_id": usuario_id,
        "acao": acao,
        "tabela_afetada": tabela_afetada,
        "registro_id": registro_id,
        "timestamp_servidor": datetime.now(timezone.utc).isoformat(),
        "ip_origem": ip_origem,
    }

    lista.append(entrada)
    salvar_audit_log(lista)

    return entrada