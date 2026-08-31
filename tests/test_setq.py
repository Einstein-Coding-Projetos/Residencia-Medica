"""Testes do SETQ Smart: fluxo invertido (residente avalia preceptor),
anonimizado, com resumo liberado só a partir de 3 respostas (regra COI-03).
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import usuario_atual
from app.core.instrumentos import obter_instrumento
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

    def _usuario(papel: Papel) -> Usuario:
        u = Usuario(
            nome=f"Teste {papel.value} {uuid.uuid4()}",
            email=f"{uuid.uuid4()}@hspm.test",
            senha_hash="x",
            papel=papel,
            programa_id=programa.id,
        )
        db.add(u)
        db.flush()
        return u

    preceptor = _usuario(Papel.PRECEPTOR)
    outro_preceptor = _usuario(Papel.PRECEPTOR)
    residentes = [_usuario(Papel.RESIDENTE) for _ in range(4)]
    db.commit()

    estado = {"usuario": residentes[0]}

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[usuario_atual] = lambda: estado["usuario"]

    cliente = TestClient(app)
    yield {
        "cliente": cliente,
        "preceptor": preceptor,
        "outro_preceptor": outro_preceptor,
        "residentes": residentes,
        "estado": estado,
    }

    app.dependency_overrides.clear()
    db.close()


def _itens(nota: int) -> list[dict]:
    return [{"dominio": d.codigo, "nota": nota} for d in obter_instrumento("setq_smart").dominios]


def _enviar_e_confirmar(cliente, estado, autor, preceptor, nota):
    estado["usuario"] = autor
    criada = cliente.post(
        "/api/v1/avaliacoes/setq",
        json={
            "preceptor_id": str(preceptor.id),
            "itens": _itens(nota),
            "observacoes": "",
        },
    )
    assert criada.status_code == 201, criada.text
    confirmada = cliente.post(
        f"/api/v1/avaliacoes/{criada.json()['id']}/confirmar",
        json={"confirmo_observacao_direta": True},
    )
    assert confirmada.status_code == 200, confirmada.text
    return confirmada.json()


def test_residente_envia_setq_sobre_preceptor(ambiente):
    estado = ambiente["estado"]
    estado["usuario"] = ambiente["residentes"][0]

    r = ambiente["cliente"].post(
        "/api/v1/avaliacoes/setq",
        json={
            "preceptor_id": str(ambiente["preceptor"].id),
            "itens": _itens(4),
            "observacoes": "",
        },
    )
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["residente_id"] == str(ambiente["preceptor"].id)
    assert corpo["avaliador_id"] == str(ambiente["residentes"][0].id)
    assert corpo["nota"] == 4


def test_preceptor_nao_pode_enviar_setq(ambiente):
    ambiente["estado"]["usuario"] = ambiente["preceptor"]
    r = ambiente["cliente"].post(
        "/api/v1/avaliacoes/setq",
        json={
            "preceptor_id": str(ambiente["outro_preceptor"].id),
            "itens": _itens(4),
            "observacoes": "",
        },
    )
    assert r.status_code == 403


def test_confirmacao_usa_texto_proprio_do_setq(ambiente):
    ambiente["estado"]["usuario"] = ambiente["residentes"][0]
    criada = ambiente["cliente"].post(
        "/api/v1/avaliacoes/setq",
        json={
            "preceptor_id": str(ambiente["preceptor"].id),
            "itens": _itens(5),
            "observacoes": "",
        },
    ).json()

    confirmada = ambiente["cliente"].post(
        f"/api/v1/avaliacoes/{criada['id']}/confirmar",
        json={"confirmo_observacao_direta": True},
    )
    assert confirmada.status_code == 200
    assert "experiência genuína" in confirmada.json()["declaracao_observacao"]


def test_residente_nao_ve_setq_de_outro_diretamente(ambiente):
    estado = ambiente["estado"]
    criada = _enviar_e_confirmar(
        ambiente["cliente"], estado, ambiente["residentes"][0], ambiente["preceptor"], 4
    )

    estado["usuario"] = ambiente["residentes"][1]
    r = ambiente["cliente"].get(f"/api/v1/avaliacoes/{criada['id']}")
    assert r.status_code == 403


def test_preceptor_nao_ve_setq_individual(ambiente):
    estado = ambiente["estado"]
    criada = _enviar_e_confirmar(
        ambiente["cliente"], estado, ambiente["residentes"][0], ambiente["preceptor"], 4
    )

    estado["usuario"] = ambiente["preceptor"]
    r = ambiente["cliente"].get(f"/api/v1/avaliacoes/{criada['id']}")
    assert r.status_code == 403


def test_resumo_indisponivel_abaixo_de_tres(ambiente):
    estado = ambiente["estado"]
    _enviar_e_confirmar(ambiente["cliente"], estado, ambiente["residentes"][0], ambiente["preceptor"], 5)
    _enviar_e_confirmar(ambiente["cliente"], estado, ambiente["residentes"][1], ambiente["preceptor"], 3)

    estado["usuario"] = ambiente["preceptor"]
    r = ambiente["cliente"].get(f"/api/v1/avaliacoes/setq/resumo/{ambiente['preceptor'].id}")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["disponivel"] is False
    assert corpo["total_respostas"] == 2
    assert corpo["media_por_dominio"] is None


def test_resumo_libera_a_partir_de_tres_e_nao_identifica_ninguem(ambiente):
    estado = ambiente["estado"]
    notas = [5, 3, 4]
    for residente, nota in zip(ambiente["residentes"][:3], notas):
        _enviar_e_confirmar(ambiente["cliente"], estado, residente, ambiente["preceptor"], nota)

    estado["usuario"] = ambiente["preceptor"]
    r = ambiente["cliente"].get(f"/api/v1/avaliacoes/setq/resumo/{ambiente['preceptor'].id}")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["disponivel"] is True
    assert corpo["total_respostas"] == 3

    media_esperada = round(sum(notas) / len(notas), 2)
    for media in corpo["media_por_dominio"].values():
        assert media == media_esperada

    texto = str(corpo)
    for residente in ambiente["residentes"][:3]:
        assert str(residente.id) not in texto


def test_outro_preceptor_nao_ve_resumo_alheio(ambiente):
    estado = ambiente["estado"]
    for residente in ambiente["residentes"][:3]:
        _enviar_e_confirmar(ambiente["cliente"], estado, residente, ambiente["preceptor"], 4)

    estado["usuario"] = ambiente["outro_preceptor"]
    r = ambiente["cliente"].get(f"/api/v1/avaliacoes/setq/resumo/{ambiente['preceptor'].id}")
    assert r.status_code == 403
