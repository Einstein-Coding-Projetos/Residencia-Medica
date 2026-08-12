from sqlalchemy.orm import Session

from app.utils.hash_utils import gerar_hash_registro
from app.core.audit_service import registrar_auditoria


def confirmar_registro(
    db: Session,
    registro,
    campos_para_hash: dict,
    usuario_id: int,
    ip_origem: str | None = None,
) -> None:
    """
    Executa a confirmação final de um registro (ex: avaliação):
    1. Calcula o hash de integridade a partir dos campos definidos.
    2. Salva o hash no registro (campo write-once).
    3. Marca o registro como confirmado (bloqueia futuras edições).
    4. Registra a ação na trilha de auditoria.

    'registro' precisa ter os atributos 'hash_integridade' e 'confirmado'.
    Deve ser chamado apenas uma vez, no momento da confirmação —
    nunca em rascunho.
    """
    if getattr(registro, "confirmado", False):
        raise ValueError("Registro já confirmado — não pode ser confirmado novamente.")

    registro.hash_integridade = gerar_hash_registro(campos_para_hash)
    registro.confirmado = True

    db.add(registro)
    db.commit()

    registrar_auditoria(
        db=db,
        usuario_id=usuario_id,
        acao="confirmacao",
        tabela_afetada=registro.__tablename__,
        registro_id=registro.id,
        ip_origem=ip_origem,
    )