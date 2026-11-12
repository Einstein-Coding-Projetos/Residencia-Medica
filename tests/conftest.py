import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import usuario_atual
from app.db.models import Base, Especialidade, Papel, Programa, Servico, Usuario
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def amb_gov():
    """Programa com dois serviços, preceptores, R4/R5, residentes e admin.

    Nenhuma alocação é criada aqui — cada teste aloca o que precisa.
    """
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    esp = Especialidade(nome=f"Cirurgia Geral {uuid.uuid4()}")
    db.add(esp)
    db.flush()
    prog = Programa(nome="RM Cirurgia Geral", especialidade_id=esp.id, instituicao="HSPM")
    db.add(prog)
    db.flush()
    enfermaria = Servico(nome="Enfermaria", programa_id=prog.id)
    ambulatorio = Servico(nome="Ambulatório", programa_id=prog.id)
    db.add_all([enfermaria, ambulatorio])
    db.flush()

    def usuario(papel, nome):
        u = Usuario(
            nome=nome, email=f"{uuid.uuid4()}@t.br", senha_hash="x", papel=papel, programa_id=prog.id
        )
        db.add(u)
        db.flush()
        return u

    ctx = {
        "db": db,
        "programa": prog,
        "enfermaria": enfermaria,
        "ambulatorio": ambulatorio,
        "preceptor": usuario(Papel.PRECEPTOR, "Dr. Bruno"),
        "outro_preceptor": usuario(Papel.PRECEPTOR, "Dra. Lia"),
        "r4": usuario(Papel.AVALIADOR_INTERMEDIARIO, "Dra. Clara R4"),
        "residente": usuario(Papel.RESIDENTE, "Ana"),
        "outro_residente": usuario(Papel.RESIDENTE, "Beto"),
        "admin": usuario(Papel.ADMINISTRADOR, "Carla Admin"),
    }
    db.commit()
    estado = {"usuario": ctx["preceptor"]}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[usuario_atual] = lambda: estado["usuario"]
    ctx["c"] = TestClient(app)
    ctx["como"] = lambda nome: estado.__setitem__("usuario", ctx[nome])
    yield ctx
    app.dependency_overrides.clear()
    db.close()
