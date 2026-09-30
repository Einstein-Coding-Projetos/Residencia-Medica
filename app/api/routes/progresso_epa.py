from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import SomenteAvaliador, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.core.epa_service import atualizar_progresso, calcular_mapa_epas
from app.core.permissoes_avaliacao import exigir_pode_avaliar
from app.db.models import EPA, Papel, Usuario
from app.db.session import get_db
from app.schemas.epas import ItemMapaEPA, ProgressoEPAUpdate

router = APIRouter(prefix="/epas", tags=["progresso-epa"])


@router.get(
    "/mapa/{residente_id}",
    response_model=list[ItemMapaEPA],
    summary="Mapa de progresso de EPAs de um residente",
)
def mapa_epas_residente(
    residente_id: str,
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
) -> list[ItemMapaEPA]:
    residente = db.get(Usuario, residente_id)
    if residente is None or residente.papel != Papel.RESIDENTE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Residente não encontrado.")

    eh_o_proprio = usuario.id == residente.id
    eh_avaliador_ou_admin = usuario.papel in {Papel.ADMINISTRADOR, Papel.PRECEPTOR, Papel.AVALIADOR_INTERMEDIARIO}
    if not (eh_o_proprio or eh_avaliador_ou_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para ver o mapa de EPAs deste residente.",
        )

    return calcular_mapa_epas(db, residente)


@router.put(
    "/progresso",
    response_model=ItemMapaEPA,
    summary="Atualizar o nível atual de um residente numa EPA (somente avaliadores)",
)
def atualizar_progresso_epa(
    dados: ProgressoEPAUpdate,
    avaliador: SomenteAvaliador,
    db: Annotated[Session, Depends(get_db)],
) -> ItemMapaEPA:
    residente = db.get(Usuario, dados.residente_id)
    if residente is None or residente.papel != Papel.RESIDENTE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Residente não encontrado.")

    exigir_pode_avaliar(avaliador, residente)

    epa = db.get(EPA, dados.epa_id)
    if epa is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="EPA não encontrada.")

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
        detalhe={"residente_id": str(residente.id), "nivel_atual": dados.nivel_atual},
    )
    db.commit()

    mapa = calcular_mapa_epas(db, residente)
    item = next(i for i in mapa if i["epa_id"] == epa.id)
    return ItemMapaEPA(**item)