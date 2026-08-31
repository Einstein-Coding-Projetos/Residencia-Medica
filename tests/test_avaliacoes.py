from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth_service import criar_usuario
from app.db.models import Base, Papel
from app.db.session import get_db
from app.main import app

PREFIXO = "/api/v1"
SENHA_OK = "SenhaForte123"


@pytest.fixture()
def db_sessao():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    sessao = Sessao()
    try:
        yield sessao
    finally:
        sessao.close()


@pytest.fixture()
def cliente(db_sessao):
    app.dependency_overrides[get_db] = lambda: db_sessao
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def usuarios(db_sessao):
    programa_id = uuid.uuid4()
    outro_programa_id = uuid.uuid4()
    criados = {
        "preceptor": criar_usuario(
            db_sessao, nome="Dr. Bruno", email="bruno@hospital.br",
            senha=SENHA_OK, papel=Papel.PRECEPTOR, programa_id=programa_id,
        ),
        "residente": criar_usuario(
            db_sessao, nome="Ana Residente", email="ana@hospital.br",
            senha=SENHA_OK, papel=Papel.RESIDENTE, programa_id=programa_id,
        ),
        "preceptor_outro_programa": criar_usuario(
            db_sessao, nome="Dr. Outro", email="outro@hospital.br",
            senha=SENHA_OK, papel=Papel.PRECEPTOR, programa_id=outro_programa_id,
        ),
    }
    db_sessao.commit()
    return criados


def cabecalho(cliente, email: str) -> dict[str, str]:
    token = cliente.post(
        f"{PREFIXO}/auth/login", json={"email": email, "senha": SENHA_OK}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _corpo_avaliacao(residente_id) -> dict:
    return {
        "residente_id": str(residente_id),
        "instrumento": "zwisch",
        "itens": [{"item": "Planejamento", "nota": 4}, {"item": "Execução", "nota": 3}],
        "observacoes": "Bom desempenho geral.",
    }


def test_preceptor_cria_e_confirma_avaliacao(cliente, usuarios):
    cab = cabecalho(cliente, "bruno@hospital.br")

    criada = cliente.post(
        f"{PREFIXO}/avaliacoes", json=_corpo_avaliacao(usuarios["residente"].id), headers=cab
    )
    assert criada.status_code == 201
    corpo = criada.json()
    assert corpo["nota"] == 3.5
    assert corpo["confirmado"] is False
    assert corpo["hash_integridade"] is None

    confirmada = cliente.post(
        f"{PREFIXO}/avaliacoes/{corpo['id']}/confirmar", headers=cab
    )
    assert confirmada.status_code == 200
    assert confirmada.json()["confirmado"] is True
    assert confirmada.json()["hash_integridade"] is not None


def test_confirmar_duas_vezes_e_bloqueado(cliente, usuarios):
    cab = cabecalho(cliente, "bruno@hospital.br")
    criada = cliente.post(
        f"{PREFIXO}/avaliacoes", json=_corpo_avaliacao(usuarios["residente"].id), headers=cab
    )
    avaliacao_id = criada.json()["id"]

    cliente.post(f"{PREFIXO}/avaliacoes/{avaliacao_id}/confirmar", headers=cab)
    segunda = cliente.post(f"{PREFIXO}/avaliacoes/{avaliacao_id}/confirmar", headers=cab)
    assert segunda.status_code == 423


def test_avaliador_de_outro_programa_recebe_403(cliente, usuarios):
    cab = cabecalho(cliente, "outro@hospital.br")
    r = cliente.post(
        f"{PREFIXO}/avaliacoes", json=_corpo_avaliacao(usuarios["residente"].id), headers=cab
    )
    assert r.status_code == 403


def test_residente_nao_pode_criar_avaliacao(cliente, usuarios):
    cab = cabecalho(cliente, "ana@hospital.br")
    r = cliente.post(
        f"{PREFIXO}/avaliacoes", json=_corpo_avaliacao(usuarios["residente"].id), headers=cab
    )
    assert r.status_code == 403
