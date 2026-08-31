from __future__ import annotations

import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SomenteAvaliador, SomenteResidente, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.core.confirmar_registro import confirmar_registro
from app.core.immutability import bloquear_se_confirmado
from app.core.instrumentos import (
    InstrumentoDesconhecido,
    ItensInvalidos,
    calcular_resultado,
    obter_instrumento,
    resultado_zwisch,
    validar_itens,
    validar_zwisch,
)
from app.core.permissoes_avaliacao import exigir_pode_avaliar, exigir_pode_avaliar_setq
from app.db.models import Avaliacao, Papel, Usuario, agora_utc
from app.db.session import get_db
from app.schemas.avaliacoes import (
    AvaliacaoCriar,
    AvaliacaoPublica,
    ConfirmarAvaliacao,
    SetqCriar,
    SetqResumoPublico,
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

    if instrumento.codigo == "zwisch":
        # Zwisch não soma domínios: o "total" é a própria escala Z1-Z4, e a
        # descrição da faixa vem da âncora do nível declarado (avaliacao.nota).
        total_minimo, total_maximo = instrumento.escala_min, instrumento.escala_max
        faixa_descricao = instrumento.ancora_escala.get(int(avaliacao.nota))
    else:
        total_minimo, total_maximo = instrumento.total_minimo, instrumento.total_maximo
        faixa_descricao = next(
            (
                f.descricao
                for f in instrumento.faixas
                if f.rotulo == avaliacao.faixa_rotulo
            ),
            None,
        )

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
        "total_minimo": total_minimo,
        "total_maximo": total_maximo,
        "faixa_rotulo": avaliacao.faixa_rotulo,
        "faixa_descricao": faixa_descricao,
        "etapa_cirurgica": avaliacao.etapa_cirurgica,
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
                "preceptor, em POST /avaliacoes/setq — não use esta rota."
            ),
        )

    residente = db.get(Usuario, dados.residente_id)

    if residente is None:
        raise HTTPException(status_code=404, detail="Residente não encontrado.")

    if residente.papel != Papel.RESIDENTE:
        raise HTTPException(
            status_code=400,
            detail="O usuário informado não é um residente.",
        )

    exigir_pode_avaliar(avaliador, residente)

    if instrumento.codigo == "zwisch":
        try:
            validar_zwisch(instrumento, dados.etapa_cirurgica, dados.nivel_autonomia)
        except ItensInvalidos as erro:
            raise HTTPException(status_code=422, detail=str(erro)) from None

        resultado = resultado_zwisch(instrumento, dados.nivel_autonomia)
        itens_json: list[dict] = []
        etapa_cirurgica = dados.etapa_cirurgica
    else:
        try:
            validar_itens(instrumento, dados.itens)
        except ItensInvalidos as erro:
            raise HTTPException(status_code=422, detail=str(erro)) from None

        resultado = calcular_resultado(instrumento, dados.itens)
        itens_json = [
            {"dominio": item.dominio, "nota": item.nota} for item in dados.itens
        ]
        etapa_cirurgica = None

    avaliacao = Avaliacao(
        residente_id=residente.id,
        avaliador_id=avaliador.id,
        instrumento=instrumento.codigo,
        itens=json.dumps(itens_json, ensure_ascii=False),
        observacoes=dados.observacoes,
        etapa_cirurgica=etapa_cirurgica,
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
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
):
    avaliacao = db.get(Avaliacao, avaliacao_id)

    if avaliacao is None:
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    instrumento = obter_instrumento(avaliacao.instrumento)

    if not corpo.confirmo_observacao_direta:
        raise HTTPException(
            status_code=422,
            detail=(
                "É obrigatório confirmar a declaração para enviar a avaliação: "
                f'"{instrumento.texto_confirmacao}"'
            ),
        )

    # Quem preenche é sempre `avaliador_id`, mesmo no SETQ (onde é o
    # residente) — ver comentário em app.db.models.Avaliacao.
    if avaliacao.avaliador_id != usuario.id:
        raise HTTPException(
            status_code=403,
            detail="Você não é o responsável por esta avaliação.",
        )

    bloquear_se_confirmado(avaliacao)

    sujeito = db.get(Usuario, avaliacao.residente_id)

    if sujeito is None:
        raise HTTPException(status_code=404, detail="Usuário avaliado não encontrado.")

    if instrumento.codigo == "setq_smart":
        exigir_pode_avaliar_setq(usuario, sujeito)
    else:
        exigir_pode_avaliar(usuario, sujeito)

    avaliacao.declaracao_observacao = instrumento.texto_confirmacao

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
        usuario_id=usuario.id,
        entidade="avaliacoes",
        ip_origem=ip,
    )

    avaliacao.confirmado_em = agora_utc()

    registrar_auditoria(
        db,
        acao="avaliacao.enviada",
        usuario_id=usuario.id,
        entidade="avaliacoes",
        entidade_id=avaliacao.id,
        detalhe={
            "instrumento": avaliacao.instrumento,
            "nota": avaliacao.nota,
            "faixa": avaliacao.faixa_rotulo,
            "declaracao": instrumento.texto_confirmacao,
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

    if avaliacao.instrumento == "setq_smart":
        # Anonimato (COI-03): só quem preencheu (o residente) ou admin veem
        # o registro individual. O preceptor avaliado só acessa o resumo
        # agregado em GET /avaliacoes/setq/resumo/{preceptor_id}.
        if usuario.id != avaliacao.avaliador_id and usuario.papel != Papel.ADMINISTRADOR:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Avaliações SETQ individuais não são visíveis — consulte "
                    "o resumo agregado."
                ),
            )
        return _montar_resposta(avaliacao)

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


@router.post(
    "/setq",
    response_model=AvaliacaoPublica,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar SETQ Smart sobre um preceptor (rascunho, ainda não enviado)",
)
def criar_setq(
    dados: SetqCriar,
    request: Request,
    residente: SomenteResidente,
    db: Annotated[Session, Depends(get_db)],
):
    instrumento = obter_instrumento("setq_smart")

    preceptor = db.get(Usuario, dados.preceptor_id)

    if preceptor is None:
        raise HTTPException(status_code=404, detail="Preceptor não encontrado.")

    exigir_pode_avaliar_setq(residente, preceptor)

    try:
        validar_itens(instrumento, dados.itens)
    except ItensInvalidos as erro:
        raise HTTPException(status_code=422, detail=str(erro)) from None

    resultado = calcular_resultado(instrumento, dados.itens)
    itens_json = [
        {"dominio": item.dominio, "nota": item.nota} for item in dados.itens
    ]

    # `residente_id`/`avaliador_id` invertem sentido aqui: quem preenche
    # (o residente) vai em avaliador_id, o preceptor avaliado vai em
    # residente_id — ver comentário em app.db.models.Avaliacao.
    avaliacao = Avaliacao(
        residente_id=preceptor.id,
        avaliador_id=residente.id,
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
        usuario_id=residente.id,
        entidade="avaliacoes",
        entidade_id=avaliacao.id,
        detalhe={
            "instrumento": instrumento.codigo,
            "preceptor_id": str(preceptor.id),
            "nota_calculada": resultado.valor,
        },
        ip_origem=ip,
    )

    db.commit()
    db.refresh(avaliacao)

    return _montar_resposta(avaliacao)


@router.get(
    "/setq/resumo/{preceptor_id}",
    response_model=SetqResumoPublico,
    summary="Resumo agregado e anônimo do SETQ Smart de um preceptor (COI-03)",
)
def resumo_setq(
    preceptor_id: uuid.UUID,
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
):
    if usuario.id != preceptor_id and usuario.papel != Papel.ADMINISTRADOR:
        raise HTTPException(
            status_code=403,
            detail="Você só pode consultar o próprio resumo de SETQ.",
        )

    respostas = db.scalars(
        select(Avaliacao).where(
            Avaliacao.instrumento == "setq_smart",
            Avaliacao.residente_id == preceptor_id,
            Avaliacao.confirmado.is_(True),
        )
    ).all()

    total = len(respostas)

    # Regra COI-03: abaixo de 3 respostas confirmadas, não expõe nada — nem
    # a média parcial — pra não dar margem a identificar quem respondeu.
    if total < 3:
        return SetqResumoPublico(
            preceptor_id=preceptor_id,
            total_respostas=total,
            disponivel=False,
            media_por_dominio=None,
        )

    somas: dict[str, float] = {}
    contagens: dict[str, int] = {}
    for resposta in respostas:
        for item in json.loads(resposta.itens):
            dominio = item["dominio"]
            somas[dominio] = somas.get(dominio, 0.0) + item["nota"]
            contagens[dominio] = contagens.get(dominio, 0) + 1

    media_por_dominio = {
        dominio: round(somas[dominio] / contagens[dominio], 2) for dominio in somas
    }

    return SetqResumoPublico(
        preceptor_id=preceptor_id,
        total_respostas=total,
        disponivel=True,
        media_por_dominio=media_por_dominio,
    )
