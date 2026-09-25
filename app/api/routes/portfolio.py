"""Portfólio do residente: visão agregada (JSON) e exportação em PDF."""
from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import UsuarioAtual
from app.core.auth_service import registrar_auditoria
from app.core.permissoes_portfolio import exigir_pode_ver_portfolio, pode_ver_portfolio
from app.core.portfolio import montar_portfolio
from app.core.portfolio_pdf import gerar_pdf_portfolio
from app.db.models import Papel, Usuario
from app.db.session import get_db
from app.schemas.portfolio import PortfolioPublico
from app.schemas.auth import UsuarioPublico

router = APIRouter(prefix="/portfolio", tags=["portfólio"])


def _residente_visivel(db: Session, usuario: Usuario, residente_id: uuid.UUID) -> Usuario:
    residente = db.get(Usuario, residente_id)
    if residente is None or residente.papel != Papel.RESIDENTE:
        raise HTTPException(status_code=404, detail="Residente não encontrado.")
    exigir_pode_ver_portfolio(usuario, residente)
    return residente


def _eu_residente(usuario: Usuario) -> Usuario:
    if usuario.papel != Papel.RESIDENTE:
        raise HTTPException(
            status_code=400,
            detail="Só residentes têm portfólio próprio. Use /portfolio/{residente_id}.",
        )
    return usuario


def _nome_arquivo(nome: str, gerado_em) -> str:
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").lower() or "residente"
    return f"portfolio-{base}-{gerado_em:%Y-%m-%d}.pdf"


def _responder_pdf(db: Session, usuario: Usuario, residente: Usuario, request: Request) -> Response:
    portfolio = montar_portfolio(db, residente)
    conteudo = gerar_pdf_portfolio(portfolio)

    # Exportar dado de residente é evento relevante para LGPD: fica na trilha.
    registrar_auditoria(
        db,
        acao="portfolio.exportado_pdf",
        usuario_id=usuario.id,
        entidade="usuarios",
        entidade_id=residente.id,
        detalhe={"bytes": len(conteudo)},
        ip_origem=request.client.host if request.client else None,
    )
    db.commit()

    nome = _nome_arquivo(residente.nome, portfolio["gerado_em"])
    return Response(
        content=conteudo,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get(
    "/residentes",
    response_model=list[UsuarioPublico],
    summary="Residentes cujo portfólio você pode abrir",
)
def listar_residentes_visiveis(
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
):
    residentes = db.scalars(
        select(Usuario)
        .where(Usuario.papel == Papel.RESIDENTE, Usuario.ativo.is_(True))
        .order_by(Usuario.nome)
    ).all()
    return [r for r in residentes if pode_ver_portfolio(usuario, r)]


@router.get("/meu", response_model=PortfolioPublico, summary="Meu portfólio (residente)")
def meu_portfolio(usuario: UsuarioAtual, db: Annotated[Session, Depends(get_db)]):
    return montar_portfolio(db, _eu_residente(usuario))


@router.get("/meu/pdf", summary="Exportar meu portfólio em PDF (residente)")
def meu_portfolio_pdf(
    request: Request, usuario: UsuarioAtual, db: Annotated[Session, Depends(get_db)]
):
    residente = _eu_residente(usuario)
    return _responder_pdf(db, usuario, residente, request)


@router.get(
    "/{residente_id}",
    response_model=PortfolioPublico,
    summary="Portfólio de um residente (próprio, preceptor do programa ou admin)",
)
def portfolio_do_residente(
    residente_id: uuid.UUID,
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
):
    return montar_portfolio(db, _residente_visivel(db, usuario, residente_id))


@router.get(
    "/{residente_id}/pdf",
    summary="Exportar o portfólio de um residente em PDF",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
def portfolio_do_residente_pdf(
    residente_id: uuid.UUID,
    request: Request,
    usuario: UsuarioAtual,
    db: Annotated[Session, Depends(get_db)],
):
    residente = _residente_visivel(db, usuario, residente_id)
    return _responder_pdf(db, usuario, residente, request)
