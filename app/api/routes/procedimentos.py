"""Procedimentos realizados pelo residente (entram no portfólio).

Regra do documento do projeto: o que o residente registra só conta na
estatística depois de validado por um profissional. A decisão (validar ou
recusar) é final — gera hash de integridade e trava o registro.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SomenteAvaliador, SomenteResidente, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.core.confirmar_registro import confirmar_registro
from app.core.immutability import bloquear_se_confirmado
from app.core.permissoes_avaliacao import exigir_pode_avaliar, pode_avaliar
from app.core.permissoes_portfolio import exigir_pode_ver_portfolio
from app.db.models import Papel, Procedimento, Servico, Usuario, agora_utc
from app.db.session import get_db
from app.schemas.procedimentos import (
    ProcedimentoCriar,
    ProcedimentoDecidir,
    ProcedimentoPublico,
)

router = APIRouter(prefix="/procedimentos", tags=["procedimentos"])

STATUS_VALIDOS = ("pendente", "validado", "recusado")


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post(
    "",
    response_model=ProcedimentoPublico,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar procedimento realizado (fica pendente de validação)",
)
def registrar_procedimento(
    dados: ProcedimentoCriar,
    request: Request,
    residente: SomenteResidente,
    db: Annotated[Session, Depends(get_db)],
):
    if dados.data_realizacao > date.today():
        raise HTTPException(
            status_code=422,
            detail="A data do procedimento não pode estar no futuro.",
        )

    if dados.servico_id is not None:
        servico = db.get(Servico, dados.servico_id)
        if servico is None:
            raise HTTPException(status_code=404, detail="Serviço não encontrado.")
        if residente.programa_id and servico.programa_id != residente.programa_id:
            raise HTTPException(
                status_code=400,
                detail="O serviço informado não pertence ao seu programa.",
            )

    procedimento = Procedimento(
        residente_id=residente.id,
        nome=dados.nome.strip(),
        data_realizacao=dados.data_realizacao,
        participacao=dados.participacao,
        servico_id=dados.servico_id,
        observacoes=dados.observacoes,
        status="pendente",
    )
    db.add(procedimento)
    db.flush()

    registrar_auditoria(
        db,
        acao="procedimento.registrado",
        usuario_id=residente.id,
        entidade="procedimentos",
        entidade_id=procedimento.id,
        detalhe={"nome": procedimento.nome, "participacao": procedimento.participacao},
        ip_origem=_ip(request),
    )
    db.commit()
    db.refresh(procedimento)
    return procedimento


@router.get(
    "",
    response_model=list[ProcedimentoPublico],
    summary="Listar procedimentos de um residente",
)
def listar_procedimentos(
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
    residente_id: Annotated[
        uuid.UUID | None,
        Query(description="Obrigatório para preceptor/admin; o residente vê os próprios."),
    ] = None,
    status_filtro: Annotated[
        str | None, Query(alias="status", description="pendente | validado | recusado")
    ] = None,
):
    if residente_id is None:
        if usuario.papel != Papel.RESIDENTE:
            raise HTTPException(status_code=400, detail="Informe o residente_id.")
        residente_id = usuario.id

    residente = db.get(Usuario, residente_id)
    if residente is None:
        raise HTTPException(status_code=404, detail="Residente não encontrado.")
    exigir_pode_ver_portfolio(usuario, residente)

    consulta = select(Procedimento).where(Procedimento.residente_id == residente_id)
    if status_filtro is not None:
        if status_filtro not in STATUS_VALIDOS:
            raise HTTPException(
                status_code=422,
                detail=f"Status inválido. Use: {', '.join(STATUS_VALIDOS)}.",
            )
        consulta = consulta.where(Procedimento.status == status_filtro)

    consulta = consulta.order_by(Procedimento.data_realizacao.desc())
    return db.scalars(consulta).all()


@router.get(
    "/pendentes",
    response_model=list[ProcedimentoPublico],
    summary="Procedimentos aguardando a sua validação",
)
def listar_pendentes(
    avaliador: SomenteAvaliador,
    db: Annotated[Session, Depends(get_db)],
):
    pendentes = db.scalars(
        select(Procedimento)
        .where(Procedimento.status == "pendente")
        .order_by(Procedimento.data_realizacao)
    ).all()

    residentes = {p.residente_id for p in pendentes}
    permitidos = {
        rid
        for rid in residentes
        if (r := db.get(Usuario, rid)) is not None and pode_avaliar(avaliador, r)
    }
    return [p for p in pendentes if p.residente_id in permitidos]


@router.post(
    "/{procedimento_id}/decidir",
    response_model=ProcedimentoPublico,
    summary="Validar ou recusar um procedimento (decisão final, trava o registro)",
)
def decidir_procedimento(
    procedimento_id: uuid.UUID,
    corpo: ProcedimentoDecidir,
    request: Request,
    avaliador: SomenteAvaliador,
    db: Annotated[Session, Depends(get_db)],
):
    procedimento = db.get(Procedimento, procedimento_id)
    if procedimento is None:
        raise HTTPException(status_code=404, detail="Procedimento não encontrado.")

    bloquear_se_confirmado(procedimento)

    residente = db.get(Usuario, procedimento.residente_id)
    if residente is None:
        raise HTTPException(status_code=404, detail="Residente não encontrado.")
    exigir_pode_avaliar(avaliador, residente)

    procedimento.status = "validado" if corpo.aprovado else "recusado"
    procedimento.motivo_recusa = None if corpo.aprovado else corpo.motivo_recusa.strip()
    procedimento.validador_id = avaliador.id
    procedimento.validado_em = agora_utc()

    confirmar_registro(
        db,
        registro=procedimento,
        campos_para_hash={
            "id": str(procedimento.id),
            "residente_id": str(procedimento.residente_id),
            "nome": procedimento.nome,
            "data_realizacao": procedimento.data_realizacao.isoformat(),
            "participacao": procedimento.participacao,
            "status": procedimento.status,
            "validador_id": str(procedimento.validador_id),
            "motivo_recusa": procedimento.motivo_recusa,
        },
        usuario_id=avaliador.id,
        entidade="procedimentos",
        ip_origem=_ip(request),
    )

    registrar_auditoria(
        db,
        acao=f"procedimento.{procedimento.status}",
        usuario_id=avaliador.id,
        entidade="procedimentos",
        entidade_id=procedimento.id,
        detalhe={"residente_id": str(residente.id)},
        ip_origem=_ip(request),
    )
    db.commit()
    db.refresh(procedimento)
    return procedimento
