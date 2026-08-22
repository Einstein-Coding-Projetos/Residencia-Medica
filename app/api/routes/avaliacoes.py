from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import SomenteAvaliador, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.core.confirmar_registro import confirmar_registro
from app.core.immutability import bloquear_se_confirmado
from app.core.permissoes_avaliacao import exigir_pode_avaliar
from app.db.models import Avaliacao, Usuario, agora_utc, Papel
from app.db.session import get_db
from app.schemas.avaliacoes import AvaliacaoCriar, AvaliacaoPublica


router = APIRouter(
    prefix="/avaliacoes",
    tags=["avaliações"],
)


def calcular_nota(itens: list) -> float:
    """
    Calcula a média das notas dos itens.

    Cada item recebe uma nota de 1 a 5.
    A nota final é a média dos itens.
    """

    if not itens:
        raise HTTPException(
            status_code=400,
            detail="A avaliação precisa ter pelo menos um item.",
        )

    notas = [item.nota for item in itens]

    return round(sum(notas) / len(notas), 2)


def validar_instrumento(instrumento: str) -> None:
    instrumentos_permitidos = {
        "zwisch",
        "setq_smart",
    }

    if instrumento not in instrumentos_permitidos:
        raise HTTPException(
            status_code=400,
            detail="Instrumento de avaliação inválido.",
        )


@router.post(
    "",
    response_model=AvaliacaoPublica,
    status_code=status.HTTP_201_CREATED,
    summary="Criar avaliação",
)
def criar_avaliacao(
    dados: AvaliacaoCriar,
    request: Request,
    avaliador: SomenteAvaliador,
    db: Annotated[Session, Depends(get_db)],
):
    validar_instrumento(dados.instrumento)

    residente = db.get(Usuario, dados.residente_id)

    if residente is None:
        raise HTTPException(
            status_code=404,
            detail="Residente não encontrado.",
        )

    if residente.papel != Papel.RESIDENTE:
        raise HTTPException(
            status_code=400,
            detail="O usuário informado não é um residente.",
        )

    exigir_pode_avaliar(avaliador, residente)

    nota = calcular_nota(dados.itens)

    itens_json = [
        {
            "item": item.item,
            "nota": item.nota,
        }
        for item in dados.itens
    ]

    avaliacao = Avaliacao(
        residente_id=residente.id,
        avaliador_id=avaliador.id,
        instrumento=dados.instrumento,
        itens=json.dumps(
            itens_json,
            ensure_ascii=False,
        ),
        observacoes=dados.observacoes,
        nota=nota,
        confirmado=False,
    )

    db.add(avaliacao)
    db.flush()

    ip = request.client.host if request.client else None

    registrar_auditoria(
        db,
        acao="avaliacao.criada",
        usuario_id=avaliador.id,
        entidade="avaliacoes",
        entidade_id=avaliacao.id,
        detalhe={
            "instrumento": dados.instrumento,
            "residente_id": str(residente.id),
            "nota_calculada": nota,
        },
        ip_origem=ip,
    )

    db.commit()
    db.refresh(avaliacao)

    return {
        "id": avaliacao.id,
        "residente_id": avaliacao.residente_id,
        "avaliador_id": avaliacao.avaliador_id,
        "instrumento": avaliacao.instrumento,
        "itens": itens_json,
        "observacoes": avaliacao.observacoes,
        "nota": avaliacao.nota,
        "confirmado": avaliacao.confirmado,
        "hash_integridade": avaliacao.hash_integridade,
    }


@router.post(
    "/{avaliacao_id}/confirmar",
    response_model=AvaliacaoPublica,
    summary="Confirmar envio da avaliação",
)
def confirmar_avaliacao(
    avaliacao_id: str,
    request: Request,
    avaliador: SomenteAvaliador,
    db: Annotated[Session, Depends(get_db)],
):
    avaliacao = db.get(Avaliacao, avaliacao_id)

    if avaliacao is None:
        raise HTTPException(
            status_code=404,
            detail="Avaliação não encontrada.",
        )

    if avaliacao.avaliador_id != avaliador.id:
        raise HTTPException(
            status_code=403,
            detail="Você não é o responsável por esta avaliação.",
        )

    bloquear_se_confirmado(avaliacao)

    residente = db.get(Usuario, avaliacao.residente_id)

    if residente is None:
        raise HTTPException(
            status_code=404,
            detail="Residente não encontrado.",
        )

    exigir_pode_avaliar(avaliador, residente)

    ip = request.client.host if request.client else None

    campos_para_hash = {
        "id": str(avaliacao.id),
        "residente_id": str(avaliacao.residente_id),
        "avaliador_id": str(avaliacao.avaliador_id),
        "instrumento": avaliacao.instrumento,
        "itens": avaliacao.itens,
        "observacoes": avaliacao.observacoes,
        "nota": avaliacao.nota,
    }

    confirmar_registro(
        db,
        registro=avaliacao,
        campos_para_hash=campos_para_hash,
        usuario_id=avaliador.id,
        entidade="avaliacoes",
        ip_origem=ip,
    )

    avaliacao.confirmado_em = agora_utc()

    registrar_auditoria(
        db,
        acao="avaliacao.enviada",
        usuario_id=avaliador.id,
        entidade="avaliacoes",
        entidade_id=avaliacao.id,
        detalhe={
            "instrumento": avaliacao.instrumento,
            "nota": avaliacao.nota,
        },
        ip_origem=ip,
    )

    db.commit()
    db.refresh(avaliacao)

    return {
        "id": avaliacao.id,
        "residente_id": avaliacao.residente_id,
        "avaliador_id": avaliacao.avaliador_id,
        "instrumento": avaliacao.instrumento,
        "itens": json.loads(avaliacao.itens),
        "observacoes": avaliacao.observacoes,
        "nota": avaliacao.nota,
        "confirmado": avaliacao.confirmado,
        "hash_integridade": avaliacao.hash_integridade,
    }


@router.get(
    "/{avaliacao_id}",
    response_model=AvaliacaoPublica,
    summary="Consultar avaliação",
)
def buscar_avaliacao(
    avaliacao_id: str,
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
):
    avaliacao = db.get(Avaliacao, avaliacao_id)

    if avaliacao is None:
        raise HTTPException(
            status_code=404,
            detail="Avaliação não encontrada.",
        )

    if (
        usuario.id != avaliacao.avaliador_id
        and usuario.id != avaliacao.residente_id
        and usuario.papel != Papel.ADMINISTRADOR
    ):
        raise HTTPException(
            status_code=403,
            detail="Você não tem acesso a esta avaliação.",
        )

    return {
        "id": avaliacao.id,
        "residente_id": avaliacao.residente_id,
        "avaliador_id": avaliacao.avaliador_id,
        "instrumento": avaliacao.instrumento,
        "itens": json.loads(avaliacao.itens),
        "observacoes": avaliacao.observacoes,
        "nota": avaliacao.nota,
        "confirmado": avaliacao.confirmado,
        "hash_integridade": avaliacao.hash_integridade,
    }
