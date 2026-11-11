import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db  # Confirme se o caminho do seu get_db é este
from app.db.models import Alocacao, Usuario
from app.schemas.alocacoes import AlocacaoCreate, AlocacaoResponse

router = APIRouter()

@router.post(
    "/",
    response_model=AlocacaoResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Criar uma nova alocação",
)
def criar_alocacao(
    dados: AlocacaoCreate,
    db: Annotated[Session, Depends(get_db)],
):
    # Trava básica de integridade: garante que o usuário existe no banco
    usuario = db.get(Usuario, dados.usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
        
    nova_alocacao = Alocacao(**dados.model_dump())
    db.add(nova_alocacao)
    db.commit()
    db.refresh(nova_alocacao)
    
    return nova_alocacao

@router.get(
    "/",
    response_model=list[AlocacaoResponse],
    summary="Listar alocações (com filtro opcional por usuário)",
)
def listar_alocacoes(
    db: Annotated[Session, Depends(get_db)],
    usuario_id: uuid.UUID | None = None,
):
    query = select(Alocacao)
    
    if usuario_id:
        query = query.where(Alocacao.usuario_id == usuario_id)
        
    alocacoes = db.scalars(query).all()
    return alocacoes