"""Testes da ficha Zwisch: uma avaliação = uma etapa cirúrgica + um nível Z1-Z4.

Sobe a app com banco SQLite em memória e usuários fictícios.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import usuario_atual
from app.db.models import Base, Especialidade, Papel, Programa, Usuario
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def ambiente():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = Sessao()

    especialidade = Especialidade(nome=f"Cirurgia Geral {uuid.uuid4()}")
    db.add(especialidade)
    db.flush()

    programa = Programa(
        nome="Residência em Cirurgia Geral",
        especialidade_id=especialidade.id,
        instituicao="HSPM",
    )
    db.add(programa)
    db.flush()

    def _usuario(papel: Papel, programa_id=programa.id) -> Usuario:
        u = Usuario(
            nome=f"Teste {papel.value}",
            email=f"{uuid.uuid4()}@hspm.test",
            senha_hash="x",
            papel=papel,
            programa_id=programa_id,
        )
        db.add(u)
        db.flush()
        return u

    preceptor = _usuario(Papel.PRECEPTOR)
    residente = _usuario(Papel.RESIDENTE)
    outro_programa = Programa(
        nome="Outro programa",
        especialidade_id=especialidade.id,
        instituicao="HSPM",
    )
    db.add(outro_programa)
    db.flush()
    residente_outro_programa = _usuario(Papel.RESIDENTE, outro_programa.id)
    db.commit()

    estado = {"usuario": preceptor}

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[usuario_atual] = lambda: estado["usuario"]

    cliente = TestClient(app)
    yield {
        "cliente": cliente,
        "preceptor": preceptor,
        "residente": residente,
        "residente_outro_programa": residente_outro_programa,
        "estado": estado,
    }

    app.dependency_overrides.clear()
    db.close()


def _criar(cliente, residente_id, etapa, nivel):
    return cliente.post(
        "/api/v1/avaliacoes",
        json={
            "residente_id": str(residente_id),
            "instrumento": "zwisch",
            "etapa_cirurgica": etapa,
            "nivel_autonomia": nivel,
            "observacoes": "",
        },
    )


def test_registra_etapa_com_nivel_e_confirma(ambiente):
    r = _criar(ambiente["cliente"], ambiente["residente"].id, "Dissecção do triângulo de Calot", 2)
    assert r.status_code == 201, r.text

    corpo = r.json()
    assert corpo["etapa_cirurgica"] == "Dissecção do triângulo de Calot"
    assert corpo["nota"] == 2
    assert corpo["faixa_rotulo"] == "Z2"
    assert corpo["confirmado"] is False
    assert corpo["hash_integridade"] is None

    confirmada = ambiente["cliente"].post(
        f"/api/v1/avaliacoes/{corpo['id']}/confirmar",
        json={"confirmo_observacao_direta": True},
    )
    assert confirmada.status_code == 200, confirmada.text
    assert confirmada.json()["confirmado"] is True
    assert confirmada.json()["hash_integridade"] is not None


def test_exige_etapa_cirurgica(ambiente):
    r = _criar(ambiente["cliente"], ambiente["residente"].id, "", 2)
    assert r.status_code == 422


def test_exige_nivel_dentro_da_escala(ambiente):
    r = _criar(ambiente["cliente"], ambiente["residente"].id, "Hemostasia", 5)
    assert r.status_code == 422


def test_permite_varias_etapas_do_mesmo_residente(ambiente):
    primeira = _criar(ambiente["cliente"], ambiente["residente"].id, "Exposição", 1)
    segunda = _criar(ambiente["cliente"], ambiente["residente"].id, "Fechamento", 4)
    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert primeira.json()["id"] != segunda.json()["id"]


def test_preceptor_de_outro_programa_recebe_403(ambiente):
    r = _criar(ambiente["cliente"], ambiente["residente_outro_programa"].id, "Exposição", 1)
    assert r.status_code == 403
