from fastapi import HTTPException, status


class RegistroImutavelError(HTTPException):
    def __init__(self, detail: str = "Registro confirmado não pode ser alterado ou removido."):
        super().__init__(status_code=status.HTTP_423_LOCKED, detail=detail)


def bloquear_se_confirmado(registro) -> None:
    if getattr(registro, "confirmado", False):
        raise RegistroImutavelError()