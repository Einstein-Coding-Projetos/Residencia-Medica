from sqlalchemy import create_engine, Column, Integer, String, Boolean
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.core.confirmar_avaliacao import confirmar_registro


class AvaliacaoFake(Base):
    __tablename__ = "avaliacao_fake"

    id = Column(Integer, primary_key=True)
    nota = Column(Integer)
    confirmado = Column(Boolean, default=False)
    hash_integridade = Column(String, nullable=True)


def _criar_sessao():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_confirmar_registro_gera_hash_e_bloqueia():
    db = _criar_sessao()
    registro = AvaliacaoFake(nota=8)
    db.add(registro)
    db.commit()
    db.refresh(registro)

    confirmar_registro(
        db=db,
        registro=registro,
        campos_para_hash={"nota": 8, "id": registro.id},
        usuario_id=1,
        ip_origem="127.0.0.1",
    )

    assert registro.confirmado is True
    assert registro.hash_integridade is not None


def test_confirmar_registro_ja_confirmado_gera_erro():
    db = _criar_sessao()
    registro = AvaliacaoFake(nota=9, confirmado=True)
    db.add(registro)
    db.commit()
    db.refresh(registro)

    try:
        confirmar_registro(
            db=db,
            registro=registro,
            campos_para_hash={"nota": 9, "id": registro.id},
            usuario_id=1,
        )
        assert False, "Deveria ter levantado erro"
    except ValueError:
        pass