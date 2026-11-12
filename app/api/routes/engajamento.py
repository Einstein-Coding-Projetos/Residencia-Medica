from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SomenteAdministrador, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.core.engajamento_service import (
    bloqueios_certificacao,
    competencia_de,
    pendencias_do_mes,
    verificar_engajamento,
)
from app.core.permissoes_portfolio import exigir_pode_ver_portfolio
from app.db.models import AlertaEngajamento, OmissaoAvaliacao, Papel, Usuario
from app.db.session import get_db
from app.schemas.governanca import OmissaoPublica, PendenciaEngajamento, StatusCertificacao

router = APIRouter(prefix="/engajamento", tags=["governança"])


def montar_pendencias(
    db: Session, hoje: date, preceptor_id: uuid.UUID | None = None
) -> list[dict]:
    competencia = competencia_de(hoje)
    pares = pendencias_do_mes(db, hoje, preceptor_id)
    if not pares:
        return []
    ids = {i for par in pares for i in par}
    nomes = dict(db.execute(select(Usuario.id, Usuario.nome).where(Usuario.id.in_(ids))).all())
    saida = []
    for p_id, r_id in pares:
        marcos = sorted(
            db.scalars(
                select(AlertaEngajamento.marco)
                .where(AlertaEngajamento.preceptor_id == p_id)
                .where(AlertaEngajamento.residente_id == r_id)
                .where(AlertaEngajamento.competencia == competencia)
            )
        )
        saida.append(
            {
                "preceptor_id": p_id,
                "preceptor_nome": nomes.get(p_id, ""),
                "residente_id": r_id,
                "residente_nome": nomes.get(r_id, ""),
                "competencia": competencia,
                "marcos_disparados": marcos,
            }
        )
    return saida


@router.post(
    "/verificar",
    summary="Rodar a verificação D15/D20/D25 e o fechamento do mês (somente administrador)",
)
def rodar_verificacao(
    request: Request,
    admin: SomenteAdministrador,
    db: Annotated[Session, Depends(get_db)],
    data: date | None = None,
) -> dict:
    """Normalmente roda pelo job diário (`python -m app.jobs.verificar_engajamento`).
    `data` permite simular outro dia (testes e homologação)."""
    resultado = verificar_engajamento(db, data)
    registrar_auditoria(
        db,
        acao="engajamento.verificacao_manual",
        usuario_id=admin.id,
        detalhe={"data": resultado.data.isoformat()},
        ip_origem=request.client.host if request.client else None,
    )
    db.commit()
    return resultado.como_dict()


@router.get(
    "/pendencias",
    response_model=list[PendenciaEngajamento],
    summary="Avaliações pendentes no mês (preceptor: as suas; administrador: todas)",
)
def listar_pendencias(usuario: UsuarioAtual, db: Annotated[Session, Depends(get_db)]):
    if usuario.papel == Papel.ADMINISTRADOR:
        return montar_pendencias(db, date.today())
    if usuario.papel == Papel.PRECEPTOR:
        return montar_pendencias(db, date.today(), usuario.id)
    raise HTTPException(status_code=403, detail="Pendências de engajamento são do preceptor.")


@router.get(
    "/omissoes",
    response_model=list[OmissaoPublica],
    summary="Omissões registradas (somente administrador)",
)
def listar_omissoes(
    _admin: SomenteAdministrador,
    db: Annotated[Session, Depends(get_db)],
    residente_id: uuid.UUID | None = None,
):
    query = select(OmissaoAvaliacao).order_by(OmissaoAvaliacao.competencia.desc())
    if residente_id is not None:
        query = query.where(OmissaoAvaliacao.residente_id == residente_id)
    omissoes = list(db.scalars(query))
    ativas: dict[uuid.UUID, set[uuid.UUID]] = {}
    for o in omissoes:
        if o.residente_id not in ativas:
            ativas[o.residente_id] = {b.id for b in bloqueios_certificacao(db, o.residente_id)}
    return [
        {**OmissaoPublica.model_validate(o).model_dump(), "ativa": o.id in ativas[o.residente_id]}
        for o in omissoes
    ]


@router.get(
    "/certificacao/{residente_id}",
    response_model=StatusCertificacao,
    summary="A certificação do residente está bloqueada por omissão de avaliação?",
)
def status_certificacao(
    residente_id: uuid.UUID,
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
):
    residente = db.get(Usuario, residente_id)
    if residente is None or residente.papel != Papel.RESIDENTE:
        raise HTTPException(status_code=404, detail="Residente não encontrado.")
    exigir_pode_ver_portfolio(usuario, residente)
    return montar_status_certificacao(db, residente_id)


def montar_status_certificacao(db: Session, residente_id: uuid.UUID) -> dict:
    ativas = bloqueios_certificacao(db, residente_id)
    meses = ", ".join(o.competencia.strftime("%m/%Y") for o in ativas)
    return {
        "residente_id": residente_id,
        "bloqueada": bool(ativas),
        "motivo": f"Meses sem avaliação obrigatória: {meses}." if ativas else None,
        "omissoes": [OmissaoPublica.model_validate(o) for o in ativas],
    }
