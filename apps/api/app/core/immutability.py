class RegistroImutavelError(Exception):
   
    def __init__(self, detail="Registro confirmado não pode ser alterado ou removido."):
        self.detail = detail
        super().__init__(detail)


def bloquear_se_confirmado(registro: dict) -> None:
    
    if registro.get("confirmado", False):
        raise RegistroImutavelError()