"""Metadados dos instrumentos de avaliação.

Serve a definição das fichas (domínios, escala, faixas) para quem for montar
o formulário. Assim a ficha não precisa ser reescrita no frontend — ela é
gerada a partir da mesma fonte que o backend usa para validar.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import UsuarioAtual
from app.core.instrumentos import (
    INSTRUMENTOS,
    Instrumento,
    InstrumentoDesconhecido,
    obter_instrumento,
)
from app.schemas.avaliacoes import InstrumentoPublico

router = APIRouter(
    prefix="/instrumentos",
    tags=["instrumentos"],
)


def _serializar(instrumento: Instrumento) -> dict:
    return {
        "codigo": instrumento.codigo,
        "nome": instrumento.nome,
        "escala_min": instrumento.escala_min,
        "escala_max": instrumento.escala_max,
        "ancora_escala": instrumento.ancora_escala,
        "agregacao": instrumento.agregacao,
        "total_minimo": instrumento.total_minimo,
        "total_maximo": instrumento.total_maximo,
        "dominios_fixos": instrumento.dominios_fixos,
        "anonimo": instrumento.anonimo,
        "dominios": [
            {"codigo": d.codigo, "titulo": d.titulo, "descricao": d.descricao}
            for d in instrumento.dominios
        ],
        "faixas": [
            {
                "minimo": f.minimo,
                "maximo": f.maximo,
                "rotulo": f.rotulo,
                "descricao": f.descricao,
            }
            for f in instrumento.faixas
        ],
        "observacao_interna": instrumento.observacao_interna,
    }


@router.get(
    "",
    response_model=list[InstrumentoPublico],
    summary="Listar instrumentos de avaliação disponíveis",
)
def listar_instrumentos(_: UsuarioAtual):
    return [_serializar(i) for i in INSTRUMENTOS.values()]


@router.get(
    "/{codigo}",
    response_model=InstrumentoPublico,
    summary="Detalhar um instrumento (domínios, escala e faixas)",
)
def detalhar_instrumento(codigo: str, _: UsuarioAtual):
    try:
        return _serializar(obter_instrumento(codigo))
    except InstrumentoDesconhecido as erro:
        raise HTTPException(status_code=404, detail=str(erro)) from None
