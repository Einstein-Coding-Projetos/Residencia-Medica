from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.core.audit_service import registrar_auditoria


def test_registrar_auditoria_salva_no_banco():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    entrada = registrar_auditoria(
        db=db,
        usuario_id=1,
        acao="criacao",
        tabela_afetada="avaliacao",
        registro_id=42,
        ip_origem="127.0.0.1",
    )

    assert entrada.id is not None
    assert entrada.usuario_id == 1
    assert entrada.acao == "criacao"