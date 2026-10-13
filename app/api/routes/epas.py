
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    SomenteAdministrador,
    SomenteAvaliador,
    UsuarioAtual,
)
from app.core.auth_service import registrar_auditoria
from app.core.epa_service import (
    atualizar_progresso,
    calcular_mapa_epas,
)
from app.core.permissoes_avaliacao import exigir_pode_avaliar
from app.db.models import EPA, Papel, Usuario
from app.db.session import get_db
from app.schemas.cadastros import EPACreate, EPAPublico
from app.schemas.epas import ItemMapaEPA, ProgressoEPAUpdate


router = APIRouter(prefix="/epas", tags=["EPAs"])


# CADASTRAR EPA - JOANA

@router.post(
    "",
    response_model=EPAPublico,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar EPA (somente administrador)",
)
def cadastrar_epa(
    dados: EPACreate,
    admin: SomenteAdministrador,
    db: Annotated[Session, Depends(get_db)],
) -> EPAPublico:

    epa = EPA(**dados.model_dump())

    db.add(epa)
    db.flush()

    registrar_auditoria(
        db,
        acao="epa.criada",
        usuario_id=admin.id,
        entidade="epas",
        entidade_id=epa.id,
        detalhe={
            "codigo": epa.codigo,
            "titulo": epa.titulo,
            "programa_id": str(epa.programa_id),
        },
    )

    db.commit()

    return EPAPublico.model_validate(epa)


# LISTAR EPAS - JOANA

@router.get(
    "",
    response_model=list[EPAPublico],
    summary="Listar EPAs",
)
def listar_epas(
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
) -> list[EPAPublico]:

    epas = db.scalars(
        select(EPA)
        .where(EPA.ativo.is_(True))
        .order_by(EPA.codigo)
    ).all()

    return [
        EPAPublico.model_validate(epa)
        for epa in epas
    ]


# MAPA DE PROGRESSO - NAKEANO ADAPTADO

@router.get(
    "/mapa/{residente_id}",
    response_model=list[ItemMapaEPA],
    summary="Mapa de progresso das EPAs do residente",
)
def mapa_epas_residente(
    residente_id: uuid.UUID,
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
) -> list[ItemMapaEPA]:

    residente = db.get(Usuario, residente_id)

    if residente is None or residente.papel != Papel.RESIDENTE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Residente não encontrado.",
        )

    eh_proprio_residente = usuario.id == residente.id

    eh_avaliador_ou_admin = usuario.papel in {
        Papel.ADMINISTRADOR,
        Papel.PRECEPTOR,
        Papel.AVALIADOR_INTERMEDIARIO,
    }

    if not (eh_proprio_residente or eh_avaliador_ou_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sem permissão para visualizar este mapa.",
        )

    mapa = calcular_mapa_epas(db, residente)

    return [ItemMapaEPA(**item) for item in mapa]


# ATUALIZAR PROGRESSO - NAKEANO ADAPTADO

@router.put(
    "/progresso",
    response_model=ItemMapaEPA,
    summary="Atualizar progresso de uma EPA",
)
def atualizar_progresso_epa(
    dados: ProgressoEPAUpdate,
    avaliador: SomenteAvaliador,
    db: Annotated[Session, Depends(get_db)],
) -> ItemMapaEPA:

    residente = db.get(Usuario, dados.residente_id)

    if residente is None or residente.papel != Papel.RESIDENTE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Residente não encontrado.",
        )

    exigir_pode_avaliar(avaliador, residente)

    epa = db.get(EPA, dados.epa_id)

    if epa is None or not epa.ativo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="EPA não encontrada.",
        )

    if residente.programa_id != epa.programa_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="EPA não pertence ao programa do residente.",
        )

    atualizar_progresso(
        db,
        residente_id=residente.id,
        epa_id=epa.id,
        nivel_atual=dados.nivel_atual,
        atualizado_por=avaliador.id,
    )

    registrar_auditoria(
        db,
        acao="epa.progresso_atualizado",
        usuario_id=avaliador.id,
        entidade="progresso_epa",
        entidade_id=epa.id,
        detalhe={
            "residente_id": str(residente.id),
            "nivel_atual": dados.nivel_atual,
        },
    )

    db.commit()

    mapa = calcular_mapa_epas(db, residente)

    for item in mapa:
        if item["epa_id"] == epa.id:
            return ItemMapaEPA(**item)

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Progresso da EPA não encontrado.",
    )
