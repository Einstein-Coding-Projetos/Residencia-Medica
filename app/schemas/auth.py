from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models import Papel


class LoginRequest(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=200)


class UsuarioPublico(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nome: str
    email: EmailStr
    papel: Papel
    programa_id: uuid.UUID | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: int
    usuario: UsuarioPublico


class UsuarioCreate(BaseModel):
    """Cadastro de usuário pela API — só administrador pode chamar essa rota."""

    nome: str = Field(min_length=2, max_length=180)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=72)
    papel: Papel
    programa_id: uuid.UUID | None = None