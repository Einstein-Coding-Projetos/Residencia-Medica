"""Quem pode ver o portfólio (e os procedimentos) de um residente.

- o próprio residente;
- preceptor ou avaliador intermediário (R4/R5) que pode avaliá-lo — mesma
  regra de `pode_avaliar` (mesmo programa), para as duas telas não
  divergirem;
- administrador (papel de gestão, precisa exportar para a coordenação).

Qualquer outro residente, inclusive do mesmo programa, NÃO vê.
"""
from __future__ import annotations

from fastapi import HTTPException, status

from app.core.permissoes_avaliacao import pode_avaliar
from app.db.models import Papel, Usuario


def pode_ver_portfolio(usuario: Usuario, residente: Usuario) -> bool:
    if residente.papel != Papel.RESIDENTE:
        return False
    if usuario.id == residente.id:
        return True
    if usuario.papel == Papel.ADMINISTRADOR:
        return True
    return pode_avaliar(usuario, residente)


def exigir_pode_ver_portfolio(usuario: Usuario, residente: Usuario) -> None:
    if not pode_ver_portfolio(usuario, residente):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não tem acesso ao portfólio deste residente.",
        )
