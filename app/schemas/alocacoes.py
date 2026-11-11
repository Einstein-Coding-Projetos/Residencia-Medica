import uuid
from datetime import date
from pydantic import BaseModel, model_validator

class AlocacaoBase(BaseModel):
    usuario_id: uuid.UUID
    servico_id: uuid.UUID
    data_inicio: date
    data_fim: date

    @model_validator(mode='after')
    def validar_datas(self) -> 'AlocacaoBase':
        if self.data_inicio > self.data_fim:
            raise ValueError("A data de início não pode ser posterior à data de fim.")
        return self

class AlocacaoCreate(AlocacaoBase):
    pass

class AlocacaoResponse(AlocacaoBase):
    id: uuid.UUID

    class Config:
        from_attributes = True