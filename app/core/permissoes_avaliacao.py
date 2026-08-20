"""Matriz de permissões de avaliação: quem pode avaliar quem.

Regra fechada no Sprint 1: só PRECEPTOR e AVALIADOR_INTERMEDIARIO (R4/R5)
avaliam; só RESIDENTE é avaliado; ADMINISTRADOR nunca avalia (papel de
gestão, não função clínica).

Regra adicional ASSUMIDA aqui, a confirmar com o time: avaliador e
residente precisam pertencer ao mesmo programa. Se isso não bater com a
realidade, é só remover o bloco de `programa_id` abaixo.
"""
from __future__ import annotations

from fastapi import HTTPException, status

from app.db.models import PAPEIS_AVALIADORES, Papel, Usuario


def pode_avaliar(avaliador: Usuario, residente: Usuario) -> bool:
    if avaliador.papel not in PAPEIS_AVALIADORES:
        return False
    if residente.papel != Papel.RESIDENTE:
        return False
    if avaliador.programa_id and residente.programa_id:
        if avaliador.programa_id != residente.programa_id:
            return False
    return True


def exigir_pode_avaliar(avaliador: Usuario, residente: Usuario) -> None:
    """Levanta 403 se `avaliador` não puder avaliar `residente`.

    Chamar isso no início de toda rota de avaliação (Sprint 2), antes de
    criar ou confirmar qualquer registro.
    """
    if not pode_avaliar(avaliador, residente):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem permissão para avaliar este residente.",
        )