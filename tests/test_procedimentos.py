"""Procedimentos: residente registra, preceptor valida/recusa, decisão trava."""

import uuid
from datetime import date, timedelta

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
def amb():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    esp = Especialidade(nome=f"CG {uuid.uuid4()}")
    db.add(esp)
    db.flush()
    programas = []
    for _ in range(2):
        prog = Programa(nome="Residência", especialidade_id=esp.id, instituicao="HSPM")
        db.add(prog)
        db.flush()
        programas.append(prog)

    def usuario(papel, programa=programas[0]):
        u = Usuario(nome=f"{papel.value} {uuid.uuid4()}", email=f"{uuid.uuid4()}@t.br",
                    senha_hash="x", papel=papel, programa_id=programa.id)
        db.add(u)
        db.flush()
        return u

    ctx = {
        "residente": usuario(Papel.RESIDENTE),
        "outro_residente": usuario(Papel.RESIDENTE),
        "preceptor": usuario(Papel.PRECEPTOR),
        "preceptor_fora": usuario(Papel.PRECEPTOR, programas[1]),
        "admin": usuario(Papel.ADMINISTRADOR),
        "db": db,
    }
    db.commit()
    estado = {"usuario": ctx["residente"]}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[usuario_atual] = lambda: estado["usuario"]
    ctx["cliente"] = TestClient(app)
    ctx["como"] = lambda nome: estado.__setitem__("usuario", ctx[nome])
    yield ctx
    app.dependency_overrides.clear()
    db.close()


def _registrar(amb, **extra):
    amb["como"]("residente")
    corpo = {
        "nome": "Colecistectomia videolaparoscópica",
        "data_realizacao": (date.today() - timedelta(days=1)).isoformat(),
        "participacao": "cirurgiao_principal",
        **extra,
    }
    return amb["cliente"].post("/api/v1/procedimentos", json=corpo)


def test_residente_registra_pendente(amb):
    r = _registrar(amb)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pendente"
    assert r.json()["hash_integridade"] is None


def test_data_futura_recusada(amb):
    r = _registrar(amb, data_realizacao=(date.today() + timedelta(days=2)).isoformat())
    assert r.status_code == 422


def test_participacao_invalida(amb):
    assert _registrar(amb, participacao="plateia").status_code == 422


def test_preceptor_nao_registra(amb):
    amb["como"]("preceptor")
    r = amb["cliente"].post("/api/v1/procedimentos", json={
        "nome": "X", "data_realizacao": date.today().isoformat(), "participacao": "primeiro_auxiliar",
    })
    assert r.status_code == 403


def test_preceptor_valida_e_trava(amb):
    pid = _registrar(amb).json()["id"]
    amb["como"]("preceptor")
    assert [p["id"] for p in amb["cliente"].get("/api/v1/procedimentos/pendentes").json()] == [pid]

    r = amb["cliente"].post(f"/api/v1/procedimentos/{pid}/decidir", json={"aprovado": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "validado"
    assert len(r.json()["hash_integridade"]) == 64

    again = amb["cliente"].post(f"/api/v1/procedimentos/{pid}/decidir", json={"aprovado": False, "motivo_recusa": "x"})
    assert again.status_code == 423
    assert amb["cliente"].get("/api/v1/procedimentos/pendentes").json() == []


def test_recusa_exige_motivo(amb):
    pid = _registrar(amb).json()["id"]
    amb["como"]("preceptor")
    r = amb["cliente"].post(f"/api/v1/procedimentos/{pid}/decidir", json={"aprovado": False})
    assert r.status_code == 422
    r = amb["cliente"].post(f"/api/v1/procedimentos/{pid}/decidir",
                            json={"aprovado": False, "motivo_recusa": "Não participou."})
    assert r.json()["status"] == "recusado"
    assert r.json()["motivo_recusa"] == "Não participou."


def test_preceptor_de_outro_programa_nao_valida(amb):
    pid = _registrar(amb).json()["id"]
    amb["como"]("preceptor_fora")
    r = amb["cliente"].post(f"/api/v1/procedimentos/{pid}/decidir", json={"aprovado": True})
    assert r.status_code == 403
    assert amb["cliente"].get("/api/v1/procedimentos/pendentes").json() == []


def test_listagem_respeita_quem_ve(amb):
    _registrar(amb)
    rid = str(amb["residente"].id)

    assert len(amb["cliente"].get("/api/v1/procedimentos").json()) == 1

    amb["como"]("outro_residente")
    assert amb["cliente"].get(f"/api/v1/procedimentos?residente_id={rid}").status_code == 403

    amb["como"]("admin")
    assert len(amb["cliente"].get(f"/api/v1/procedimentos?residente_id={rid}").json()) == 1
    assert amb["cliente"].get(f"/api/v1/procedimentos?residente_id={rid}&status=validado").json() == []
