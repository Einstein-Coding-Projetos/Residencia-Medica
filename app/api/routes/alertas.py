from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SomenteAdministrador
from app.db.models import AlertaAnomalia
from app.db.session import get_db
from app.schemas.alocacoes import AlertaAnomaliaPublico

router = APIRouter(prefix="/alertas-anomalia", tags=["governança"])


@router.get(
    "",
    response_model=list[AlertaAnomaliaPublico],
    summary="Listar alertas estatísticos de padrão anômalo (somente administrador)",
)
def listar_alertas(
    _admin: SomenteAdministrador,
    db: Annotated[Session, Depends(get_db)],
    avaliador_id: uuid.UUID | None = None,
    tipo_alerta: str | None = None,
):
    query = select(AlertaAnomalia).order_by(AlertaAnomalia.criado_em.desc())
    if avaliador_id is not None:
        query = query.where(AlertaAnomalia.avaliador_id == avaliador_id)
    if tipo_alerta is not None:
        query = query.where(AlertaAnomalia.tipo_alerta == tipo_alerta)
    return list(db.scalars(query))
