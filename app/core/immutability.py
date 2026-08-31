from __future__ import annotations

from fastapi import HTTPException, status


def bloquear_se_confirmado(registro) -> None:
    if getattr(registro, "confirmado", False):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Registro confirmado não pode ser alterado ou removido.",
        )