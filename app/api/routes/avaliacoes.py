from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import SomenteAvaliador, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.core.confirmar_registro import confirmar_registro
from app.core.immutability import bloquear_se_confirmado
from app.core.instrumentos import (
    DECLARACAO_OBSERVACAO_DIRETA,
    InstrumentoDesconhecido,
    ItensInvalidos,
    calcular_resultado,
    obter_instrumento,
    validar_itens,
)
from app.core.permissoes_avaliacao import exigir_pode_avaliar
from app.db.models import Avaliacao, Papel, Usuario, agora_utc
from app.db.session import get_db
from app.schemas.avaliacoes import (
    AvaliacaoCriar,
    AvaliacaoPublica,
    ConfirmarAvaliacao,
)

router = APIRouter(
    prefix="/avaliacoes",
    tags=["avaliações"],
)


def _resolver_instrumento(codigo: str):
    try:
        return obter_instrumento(codigo)
    except InstrumentoDesconhecido as erro:
        raise HTTPException(status_code=400, detail=str(erro)) from None


def _montar_resposta(avaliacao: Avaliacao) -> dict:
    instrumento = obter_instrumento(avaliacao.instrumento)

    return {
        "id": avaliacao.id,
        "residente_id": avaliacao.residente_id,
        "avaliador_id": avaliacao.avaliador_id,
        "instrumento": avaliacao.instrumento,
        "instrumento_nome": instrumento.nome,
        "itens": json.loads(avaliacao.itens),
        "observacoes": avaliacao.observacoes,
        "nota": avaliacao.nota,
        "agregacao": instrumento.agregacao,
        "total_minimo": instrumento.total_minimo,
        "total_maximo": instrumento.total_maximo,
        "faixa_rotulo": avaliacao.faixa_rotulo,
        "faixa_descricao": next(
            (
                f.descricao
                for f in instrumento.faixas
                if f.rotulo == avaliacao.faixa_rotulo
            ),
            None,
        ),
        "confirmado": avaliacao.confirmado,
        "hash_integridade": avaliacao.hash_integridade,
        "declaracao_observacao": avaliacao.declaracao_observacao,
        "confirmado_em": avaliacao.confirmado_em,
    }


@router.post(
    "",
    response_model=AvaliacaoPublica,
    status_code=status.HTTP_201_CREATED,
    summary="Criar avaliação (rascunho, ainda não enviada)",
)
def criar_avaliacao(
    dados: AvaliacaoCriar,
    request: Request,
    avaliador: SomenteAvaliador,
    db: Annotated[Session, Depends(get_db)],
):
    instrumento = _resolver_instrumento(dados.instrumento)

    if instrumento.anonimo:
        raise HTTPException(
            status_code=400,
            detail=(
                f"O {instrumento.nome} é preenchido pelo residente sobre o "
                "preceptor e exige fluxo anonimizado próprio. Não use esta rota."
            ),
        )

    try:
        validar_itens(instrumento, dados.itens)
    except ItensInvalidos as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from None

    residente = db.get(Usuario, dados.residente_id)

    if residente is None:
        raise HTTPException(status_code=404, detail="Residente não encontrado.")

    if residente.papel != Papel.RESIDENTE:
        raise HTTPException(
            status_code=400,
            detail="O usuário informado não é um residente.",
        )

    exigir_pode_avaliar(avaliador, residente)

    resultado = calcular_resultado(instrumento, dados.itens)

    itens_json = [
        {"dominio": item.dominio, "nota": item.nota} for item in dados.itens
    ]

    avaliacao = Avaliacao(
        residente_id=residente.id,
        avaliador_id=avaliador.id,
        instrumento=instrumento.codigo,
        itens=json.dumps(itens_json, ensure_ascii=False),
        observacoes=dados.observacoes,
        nota=resultado.valor,
        faixa_rotulo=resultado.faixa_rotulo,
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
            "instrumento": instrumento.codigo,
            "residente_id": str(residente.id),
            "nota_calculada": resultado.valor,
            "faixa": resultado.faixa_rotulo,
        },
        ip_origem=ip,
    )

    db.commit()
    db.refresh(avaliacao)

    return _montar_resposta(avaliacao)


@router.post(
    "/{avaliacao_id}/confirmar",
    response_model=AvaliacaoPublica,
    summary="Confirmar envio da avaliação (torna o registro imutável)",
)
def confirmar_avaliacao(
    avaliacao_id: uuid.UUID,
    corpo: ConfirmarAvaliacao,
    request: Request,
    avaliador: SomenteAvaliador,
    db: Annotated[Session, Depends(get_db)],
):
    if not corpo.confirmo_observacao_direta:
        raise HTTPException(
            status_code=422,
            detail=(
                "É obrigatório declarar a observação direta para enviar a "
                f'avaliação: "{DECLARACAO_OBSERVACAO_DIRETA}"'
            ),
        )

    avaliacao = db.get(Avaliacao, avaliacao_id)

    if avaliacao is None:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    if avaliacao.avaliador_id != avaliador.id:
        raise HTTPException(
            status_code=403,
            detail="Você não é o responsável por esta avaliação.",
        )

    bloquear_se_confirmado(avaliacao)

    residente = db.get(Usuario, avaliacao.residente_id)

    if residente is None:
        raise HTTPException(status_code=404, detail="Residente não encontrado.")

    exigir_pode_avaliar(avaliador, residente)

    avaliacao.declaracao_observacao = DECLARACAO_OBSERVACAO_DIRETA

    ip = request.client.host if request.client else None

    campos_para_hash = {
        "id": str(avaliacao.id),
        "residente_id": str(avaliacao.residente_id),
        "avaliador_id": str(avaliacao.avaliador_id),
        "instrumento": avaliacao.instrumento,
        "itens": avaliacao.itens,
        "observacoes": avaliacao.observacoes,
        "nota": avaliacao.nota,
        "faixa_rotulo": avaliacao.faixa_rotulo,
        "declaracao_observacao": avaliacao.declaracao_observacao,
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
            "faixa": avaliacao.faixa_rotulo,
            "declaracao": DECLARACAO_OBSERVACAO_DIRETA,
        },
        ip_origem=ip,
    )

    db.commit()
    db.refresh(avaliacao)

    return _montar_resposta(avaliacao)


@router.get(
    "/{avaliacao_id}",
    response_model=AvaliacaoPublica,
    summary="Consultar avaliação",
)
def buscar_avaliacao(
    avaliacao_id: uuid.UUID,
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
):
    avaliacao = db.get(Avaliacao, avaliacao_id)

    if avaliacao is None:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    if (
        usuario.id != avaliacao.avaliador_id
        and usuario.id != avaliacao.residente_id
        and usuario.papel != Papel.ADMINISTRADOR
    ):
        raise HTTPException(
            status_code=403,
            detail="Você não tem acesso a esta avaliação.",
        )

    if usuario.id == avaliacao.residente_id and not avaliacao.confirmado:
        raise HTTPException(
            status_code=403,
            detail="Esta avaliação ainda não foi enviada pelo avaliador.",
        )

    return _montar_resposta(avaliacao)
