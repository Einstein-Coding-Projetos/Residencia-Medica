from __future__ import annotations

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
    criados = {
        "admin": criar_usuario(
            db_sessao, nome="Carla Admin", email="carla@hospital.br",
            senha=SENHA_OK, papel=Papel.ADMINISTRADOR,
        ),
        "residente": criar_usuario(
            db_sessao, nome="Ana Residente", email="ana@hospital.br",
            senha=SENHA_OK, papel=Papel.RESIDENTE,
        ),
    }
    db_sessao.commit()
    return criados


def cabecalho(cliente, email: str) -> dict[str, str]:
    token = cliente.post(
        f"{PREFIXO}/auth/login", json={"email": email, "senha": SENHA_OK}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_cadastra_usuario(cliente, usuarios):
    r = cliente.post(
        f"{PREFIXO}/usuarios",
        json={
            "nome": "Dr. Bruno Lima",
            "email": "bruno@hospital.br",
            "senha": SENHA_OK,
            "papel": "preceptor",
        },
        headers=cabecalho(cliente, "carla@hospital.br"),
    )
    assert r.status_code == 201
    corpo = r.json()
    assert corpo["email"] == "bruno@hospital.br"
    assert corpo["papel"] == "preceptor"
    assert "senha" not in str(corpo) and "senha_hash" not in str(corpo)


def test_nao_admin_recebe_403(cliente, usuarios):
    r = cliente.post(
        f"{PREFIXO}/usuarios",
        json={
            "nome": "Outro Residente",
            "email": "outro@hospital.br",
            "senha": SENHA_OK,
            "papel": "residente",
        },
        headers=cabecalho(cliente, "ana@hospital.br"),
    )
    assert r.status_code == 403


def test_email_duplicado_recebe_409(cliente, usuarios):
    r = cliente.post(
        f"{PREFIXO}/usuarios",
        json={
            "nome": "Ana Duplicada",
            "email": "ana@hospital.br",
            "senha": SENHA_OK,
            "papel": "residente",
        },
        headers=cabecalho(cliente, "carla@hospital.br"),
    )
    assert r.status_code == 409


def test_senha_curta_recebe_422(cliente, usuarios):
    r = cliente.post(
        f"{PREFIXO}/usuarios",
        json={
            "nome": "Senha Fraca",
            "email": "fraca@hospital.br",
            "senha": "123",
            "papel": "residente",
        },
        headers=cabecalho(cliente, "carla@hospital.br"),
    )
    assert r.status_code == 422
