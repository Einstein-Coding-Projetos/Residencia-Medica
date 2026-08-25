"""Testes ponta a ponta das rotas de avaliação (OSATS e Mini-CEX).

Sobe a app com banco SQLite em memória e usuários fictícios.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import usuario_atual
from app.core.instrumentos import obter_instrumento
from app.db.models import Base, Papel, Programa, Especialidade, Usuario
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

    def _usuario(papel: Papel) -> Usuario:
        u = Usuario(
            nome=f"Teste {papel.value}",
            email=f"{uuid.uuid4()}@hspm.test",
            senha_hash="x",
            papel=papel,
            programa_id=programa.id,
        )
        db.add(u)
        db.flush()
        return u

    preceptor = _usuario(Papel.PRECEPTOR)
    residente = _usuario(Papel.RESIDENTE)
    outro_preceptor = _usuario(Papel.PRECEPTOR)
    db.commit()

    estado = {"usuario": preceptor}

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[usuario_atual] = lambda: estado["usuario"]

    cliente = TestClient(app)
    yield {
        "cliente": cliente,
        "db": db,
        "preceptor": preceptor,
        "residente": residente,
        "outro_preceptor": outro_preceptor,
        "estado": estado,
    }

    app.dependency_overrides.clear()
    db.close()


def _itens(codigo: str, nota: int) -> list[dict]:
    return [
        {"dominio": d.codigo, "nota": nota}
        for d in obter_instrumento(codigo).dominios
    ]


def _criar(cliente, residente, codigo, nota):
    return cliente.post(
        "/api/v1/avaliacoes",
        json={
            "residente_id": str(residente.id),
            "instrumento": codigo,
            "itens": _itens(codigo, nota),
            "observacoes": "Observação de teste.",
        },
    )


# --------------------------------------------------------------------------
# Criação
# --------------------------------------------------------------------------
def test_cria_osats_com_soma_e_faixa(ambiente):
    r = _criar(ambiente["cliente"], ambiente["residente"], "osats", 4)
    assert r.status_code == 201, r.text

    corpo = r.json()
    assert corpo["nota"] == 28
    assert corpo["total_maximo"] == 35
    assert corpo["faixa_rotulo"] == "autonomia_supervisionada"
    assert corpo["confirmado"] is False
    assert corpo["hash_integridade"] is None


def test_cria_mini_cex_com_nota_9(ambiente):
    r = _criar(ambiente["cliente"], ambiente["residente"], "mini_cex", 9)
    assert r.status_code == 201, r.text
    assert r.json()["nota"] == 45
    assert r.json()["faixa_rotulo"] == "satisfatorio"


def test_recusa_ficha_incompleta(ambiente):
    r = ambiente["cliente"].post(
        "/api/v1/avaliacoes",
        json={
            "residente_id": str(ambiente["residente"].id),
            "instrumento": "osats",
            "itens": _itens("osats", 3)[:4],
        },
    )
    assert r.status_code == 422
    assert "Faltando" in r.json()["detail"]


def test_recusa_instrumento_inexistente(ambiente):
    r = ambiente["cliente"].post(
        "/api/v1/avaliacoes",
        json={
            "residente_id": str(ambiente["residente"].id),
            "instrumento": "inventado",
            "itens": [{"dominio": "x", "nota": 1}],
        },
    )
    assert r.status_code == 400


def test_recusa_setq_nesta_rota(ambiente):
    r = _criar(ambiente["cliente"], ambiente["residente"], "setq_smart", 4)
    assert r.status_code == 400
    assert "anonimizado" in r.json()["detail"]


# --------------------------------------------------------------------------
# Confirmação de envio (INT-04)
# --------------------------------------------------------------------------
def test_confirmacao_exige_declaracao(ambiente):
    criada = _criar(ambiente["cliente"], ambiente["residente"], "osats", 3).json()

    r = ambiente["cliente"].post(
        f"/api/v1/avaliacoes/{criada['id']}/confirmar",
        json={"confirmo_observacao_direta": False},
    )
    assert r.status_code == 422
    assert "observação direta" in r.json()["detail"]


def test_confirmacao_grava_declaracao_e_hash(ambiente):
    criada = _criar(ambiente["cliente"], ambiente["residente"], "osats", 3).json()

    r = ambiente["cliente"].post(
        f"/api/v1/avaliacoes/{criada['id']}/confirmar",
        json={"confirmo_observacao_direta": True},
    )
    assert r.status_code == 200, r.text

    corpo = r.json()
    assert corpo["confirmado"] is True
    assert corpo["hash_integridade"] is not None
    assert len(corpo["hash_integridade"]) == 64
    assert "observei este residente pessoalmente" in corpo["declaracao_observacao"]
    assert corpo["confirmado_em"] is not None


def test_nao_confirma_duas_vezes(ambiente):
    criada = _criar(ambiente["cliente"], ambiente["residente"], "osats", 3).json()
    corpo = {"confirmo_observacao_direta": True}

    ambiente["cliente"].post(f"/api/v1/avaliacoes/{criada['id']}/confirmar", json=corpo)
    r = ambiente["cliente"].post(
        f"/api/v1/avaliacoes/{criada['id']}/confirmar", json=corpo
    )
    assert r.status_code == 423


def test_outro_avaliador_nao_confirma(ambiente):
    criada = _criar(ambiente["cliente"], ambiente["residente"], "osats", 3).json()

    ambiente["estado"]["usuario"] = ambiente["outro_preceptor"]
    r = ambiente["cliente"].post(
        f"/api/v1/avaliacoes/{criada['id']}/confirmar",
        json={"confirmo_observacao_direta": True},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------
# Consulta
# --------------------------------------------------------------------------
def test_residente_nao_ve_avaliacao_nao_enviada(ambiente):
    criada = _criar(ambiente["cliente"], ambiente["residente"], "osats", 3).json()

    ambiente["estado"]["usuario"] = ambiente["residente"]
    r = ambiente["cliente"].get(f"/api/v1/avaliacoes/{criada['id']}")
    assert r.status_code == 403


def test_residente_ve_avaliacao_depois_de_enviada(ambiente):
    criada = _criar(ambiente["cliente"], ambiente["residente"], "osats", 3).json()
    ambiente["cliente"].post(
        f"/api/v1/avaliacoes/{criada['id']}/confirmar",
        json={"confirmo_observacao_direta": True},
    )

    ambiente["estado"]["usuario"] = ambiente["residente"]
    r = ambiente["cliente"].get(f"/api/v1/avaliacoes/{criada['id']}")
    assert r.status_code == 200
    assert r.json()["nota"] == 21


# --------------------------------------------------------------------------
# Metadados
# --------------------------------------------------------------------------
def test_lista_instrumentos(ambiente):
    r = ambiente["cliente"].get("/api/v1/instrumentos")
    assert r.status_code == 200
    assert {i["codigo"] for i in r.json()} == {
        "osats",
        "mini_cex",
        "notss",
        "zwisch",
        "setq_smart",
    }


def test_detalha_osats(ambiente):
    r = ambiente["cliente"].get("/api/v1/instrumentos/osats")
    assert r.status_code == 200
    corpo = r.json()
    assert len(corpo["dominios"]) == 7
    assert corpo["escala_max"] == 5
    assert len(corpo["faixas"]) == 3
