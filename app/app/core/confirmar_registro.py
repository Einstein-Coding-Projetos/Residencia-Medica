from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.auth_service import registrar_auditoria
from app.utils.hash_utils import gerar_hash_registro


def confirmar_registro(
    db: Session,
    *,
    registro,
    campos_para_hash: dict,
    usuario_id: uuid.UUID,
    entidade: str,
    ip_origem: str | None = None,
) -> None:
    if getattr(registro, "confirmado", False):
        raise ValueError("Registro já confirmado — não pode ser confirmado novamente.")

    registro.hash_integridade = gerar_hash_registro(campos_para_hash)
    registro.confirmado = True
    db.add(registro)
    db.flush()

    registrar_auditoria(
        db,
        acao="registro.confirmado",
        usuario_id=usuario_id,
        entidade=entidade,
        entidade_id=registro.id,
        detalhe={"hash": registro.hash_integridade},
        ip_origem=ip_origem,
    )