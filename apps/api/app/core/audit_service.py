from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog


def registrar_auditoria(
    db: Session,
    usuario_id: int,
    acao: str,
    tabela_afetada: str,
    registro_id: int,
    ip_origem: str | None = None,
) -> AuditLog:
    """
    Cria e salva uma entrada no audit log. Deve ser chamada
    sempre que uma ação relevante ocorrer: criação de registro,
    confirmação, ou tentativa bloqueada de edição/exclusão.
    """
    entrada = AuditLog(
        usuario_id=usuario_id,
        acao=acao,
        tabela_afetada=tabela_afetada,
        registro_id=registro_id,
        ip_origem=ip_origem,
    )
    db.add(entrada)
    db.commit()
    db.refresh(entrada)
    return entrada