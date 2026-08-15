from hash_utils import gerar_hash_registro
from audit_service import registrar_auditoria


def confirmar_registro(registro: dict, campos_para_hash: dict, usuario_id, tabela_afetada, ip_origem=None):
  
    if registro.get("confirmado", False):
        raise ValueError("Registro já confirmado — não pode ser confirmado novamente.")

    registro["hash_integridade"] = gerar_hash_registro(campos_para_hash)
    registro["confirmado"] = True

    registrar_auditoria(
        usuario_id=usuario_id,
        acao="confirmacao",
        tabela_afetada=tabela_afetada,
        registro_id=registro["id"],
        ip_origem=ip_origem,
    )