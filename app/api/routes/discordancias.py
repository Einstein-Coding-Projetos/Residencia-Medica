"""Discordância formal do residente sobre uma avaliação (Sprint 4).

Regras:
- só o residente avaliado abre, uma única vez por avaliação;
- só avaliação já confirmada, e em até 7 dias da confirmação;
- SETQ Smart não entra (é o residente quem avalia, de forma anônima);
- a avaliação original não muda: a discordância fica anexada, com hash;
- o avaliador original responde uma vez; a resposta também recebe hash;
- avaliador e administradores são notificados na abertura, o residente na resposta.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import SomenteResidente, UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.core.notificacoes_service import notificar, notificar_administradores
from app.db.models import Avaliacao, Discordancia, Papel, agora_utc
from app.db.session import get_db
from app.schemas.governanca import DiscordanciaCriar, DiscordanciaPublica, DiscordanciaResponder
from app.utils.hash_utils import gerar_hash_registro

PRAZO_DISCORDANCIA = timedelta(days=7)

router = APIRouter(tags=["discordâncias"])


def _utc(momento: datetime) -> datetime:
    # SQLite devolve datetime sem fuso; tudo é gravado em UTC.
    return momento if momento.tzinfo else momento.replace(tzinfo=timezone.utc)


def _publica(d: Discordancia) -> dict:
    return {
        **{c: getattr(d, c) for c in DiscordanciaPublica.model_fields if c != "status"},
        "status": "respondida" if d.resposta is not None else "aberta",
    }


def prazo_discordancia(avaliacao: Avaliacao) -> datetime | None:
    if not avaliacao.confirmado_em:
        return None
    return _utc(avaliacao.confirmado_em) + PRAZO_DISCORDANCIA


@router.post(
    "/avaliacoes/{avaliacao_id}/discordancia",
    response_model=DiscordanciaPublica,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar discordância formal (residente, até 7 dias após a confirmação)",
)
def abrir_discordancia(
    avaliacao_id: uuid.UUID,
    dados: DiscordanciaCriar,
    request: Request,
    residente: SomenteResidente,
    db: Annotated[Session, Depends(get_db)],
):
    avaliacao = db.get(Avaliacao, avaliacao_id)
    if avaliacao is None or avaliacao.residente_id != residente.id or avaliacao.instrumento == "setq_smart":
        raise HTTPException(status_code=404, detail="Avaliação não encontrada.")

    if not avaliacao.confirmado:
        raise HTTPException(status_code=400, detail="Esta avaliação ainda não foi enviada.")

    prazo = prazo_discordancia(avaliacao)
    if prazo is not None and agora_utc() > prazo:
        raise HTTPException(
            status_code=400,
            detail=f"O prazo de 7 dias para discordar terminou em {prazo:%d/%m/%Y}.",
        )

    if db.scalar(select(Discordancia.id).where(Discordancia.avaliacao_id == avaliacao.id)):
        raise HTTPException(status_code=409, detail="Já existe uma discordância para esta avaliação.")

    criada_em = agora_utc()
    discordancia_id = uuid.uuid4()
    discordancia = Discordancia(
        id=discordancia_id,
        avaliacao_id=avaliacao.id,
        residente_id=residente.id,
        avaliador_id=avaliacao.avaliador_id,
        motivo=dados.motivo.strip(),
        criada_em=criada_em,
        hash_integridade=gerar_hash_registro(
            {
                "id": str(discordancia_id),
                "avaliacao_id": str(avaliacao.id),
                "hash_avaliacao": avaliacao.hash_integridade,
                "residente_id": str(residente.id),
                "motivo": dados.motivo.strip(),
                "criada_em": criada_em.isoformat(),
            }
        ),
    )
    db.add(discordancia)
    db.flush()

    referencia = {"discordancia_id": str(discordancia.id), "avaliacao_id": str(avaliacao.id)}
    notificar(
        db,
        avaliacao.avaliador_id,
        tipo="discordancia_aberta",
        titulo=f"{residente.nome} registrou discordância sobre sua avaliação",
        mensagem="Responda formalmente pelo sistema. A avaliação original não é alterada.",
        referencia=referencia,
    )
    notificar_administradores(
        db,
        tipo="discordancia_aberta",
        titulo="Nova discordância formal registrada",
        mensagem=f"Residente {residente.nome} contestou uma avaliação.",
        referencia=referencia,
    )
    registrar_auditoria(
        db,
        acao="discordancia.aberta",
        usuario_id=residente.id,
        entidade="discordancias",
        entidade_id=discordancia.id,
        detalhe={**referencia, "hash": discordancia.hash_integridade},
        ip_origem=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(discordancia)
    return _publica(discordancia)


@router.post(
    "/discordancias/{discordancia_id}/resposta",
    response_model=DiscordanciaPublica,
    summary="Responder discordância (avaliador que fez a avaliação, uma única vez)",
)
def responder_discordancia(
    discordancia_id: uuid.UUID,
    dados: DiscordanciaResponder,
    request: Request,
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
):
    discordancia = db.get(Discordancia, discordancia_id)
    if discordancia is None:
        raise HTTPException(status_code=404, detail="Discordância não encontrada.")
    if discordancia.avaliador_id != usuario.id:
        raise HTTPException(status_code=403, detail="Só o avaliador desta avaliação pode responder.")
    if discordancia.resposta is not None:
        raise HTTPException(status_code=423, detail="Esta discordância já foi respondida.")

    respondida_em = agora_utc()
    discordancia.resposta = dados.resposta.strip()
    discordancia.respondida_em = respondida_em
    discordancia.hash_resposta = gerar_hash_registro(
        {
            "discordancia_id": str(discordancia.id),
            "hash_discordancia": discordancia.hash_integridade,
            "avaliador_id": str(usuario.id),
            "resposta": discordancia.resposta,
            "respondida_em": respondida_em.isoformat(),
        }
    )

    notificar(
        db,
        discordancia.residente_id,
        tipo="discordancia_respondida",
        titulo="Sua discordância foi respondida",
        mensagem=f"{usuario.nome} respondeu à discordância que você registrou.",
        referencia={"discordancia_id": str(discordancia.id), "avaliacao_id": str(discordancia.avaliacao_id)},
    )
    registrar_auditoria(
        db,
        acao="discordancia.respondida",
        usuario_id=usuario.id,
        entidade="discordancias",
        entidade_id=discordancia.id,
        detalhe={"hash_resposta": discordancia.hash_resposta},
        ip_origem=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(discordancia)
    return _publica(discordancia)


@router.get(
    "/discordancias",
    response_model=list[DiscordanciaPublica],
    summary="Listar discordâncias (residente: as suas; avaliador: sobre as suas avaliações; admin: todas)",
)
def listar_discordancias(
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
    status_filtro: str | None = None,
    avaliacao_id: uuid.UUID | None = None,
):
    query = select(Discordancia).order_by(Discordancia.criada_em.desc())
    if usuario.papel == Papel.RESIDENTE:
        query = query.where(Discordancia.residente_id == usuario.id)
    elif usuario.papel != Papel.ADMINISTRADOR:
        query = query.where(Discordancia.avaliador_id == usuario.id)
    if avaliacao_id is not None:
        query = query.where(Discordancia.avaliacao_id == avaliacao_id)
    if status_filtro == "aberta":
        query = query.where(Discordancia.resposta.is_(None))
    elif status_filtro == "respondida":
        query = query.where(Discordancia.resposta.is_not(None))
    return [_publica(d) for d in db.scalars(query)]
