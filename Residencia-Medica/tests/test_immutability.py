import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, Boolean, String, Uuid
from sqlalchemy.orm import sessionmaker, Mapped, mapped_column

from app.db.models import Base
from app.core.immutability import bloquear_se_confirmado
from app.core.confirmar_registro import confirmar_registro


class RegistroFake(Base):
    __tablename__ = "registro_fake"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nota: Mapped[int] = mapped_column(default=0)
    confirmado: Mapped[bool] = mapped_column(Boolean, default=False)
    hash_integridade: Mapped[str | None] = mapped_column(String, nullable=True)


def _sessao():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_confirmar_gera_hash_e_trava():
    db = _sessao()
    registro = RegistroFake(nota=8)
    db.add(registro)
    db.flush()

    confirmar_registro(
        db,
        registro=registro,
        campos_para_hash={"id": str(registro.id), "nota": 8},
        usuario_id=uuid.uuid4(),
        entidade="registro_fake",
    )
    db.commit()

    assert registro.confirmado is True
    assert registro.hash_integridade is not None


def test_bloqueia_edicao_apos_confirmado():
    db = _sessao()
    registro = RegistroFake(nota=9, confirmado=True)
    db.add(registro)
    db.flush()

    with pytest.raises(HTTPException) as exc:
        bloquear_se_confirmado(registro)
    assert exc.value.status_code == 423