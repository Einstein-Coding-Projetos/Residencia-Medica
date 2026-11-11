"""Sprint 4: verificação de contexto (alocação), rotas de alocação e
alertas estatísticos de anomalia."""

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import usuario_atual
from app.core import anomalias_service
from app.core.instrumentos import obter_instrumento
from app.db.models import (
    AlertaAnomalia,
    Alocacao,
    Avaliacao,
    Base,
    Especialidade,
    Papel,
    Programa,
    Servico,
    Usuario,
    agora_utc,
)
from app.db.session import get_db
from app.main import app
from tests.utils_alocacao import alocar_no_mesmo_servico

API = "/api/v1"


@pytest.fixture()
def amb():
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

    def usuario(papel):
        u = Usuario(
            nome=f"Teste {papel.value}",
            email=f"{uuid.uuid4()}@t.br",
            senha_hash="x",
            papel=papel,
            programa_id=prog.id,
        )
        db.add(u)
        db.flush()
        return u

    ctx = {
        "db": db,
        "programa": prog,
        "preceptor": usuario(Papel.PRECEPTOR),
        "outro_preceptor": usuario(Papel.PRECEPTOR),
        "residente": usuario(Papel.RESIDENTE),
        "admin": usuario(Papel.ADMINISTRADOR),
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


def _itens(codigo, nota):
    return [{"dominio": d, "nota": nota} for d in obter_instrumento(codigo).codigos_dominios]


def _criar(amb, nota=4, **extra):
    amb["como"]("preceptor")
    r = amb["c"].post(
        f"{API}/avaliacoes",
        json={
            "residente_id": str(amb["residente"].id),
            "instrumento": "osats",
            "itens": _itens("osats", nota),
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _confirmar(amb, avaliacao_id, **extra):
    amb["como"]("preceptor")
    return amb["c"].post(
        f"{API}/avaliacoes/{avaliacao_id}/confirmar",
        json={"confirmo_observacao_direta": True, **extra},
    )


# --------------------------------------------------------------------------
# Verificação de contexto
# --------------------------------------------------------------------------


def test_confirmacao_bloqueada_sem_alocacao(amb):
    criada = _criar(amb)
    r = _confirmar(amb, criada["id"])
    assert r.status_code == 400
    assert "mesmo serviço" in r.json()["detail"]


def test_confirmacao_bloqueada_em_servicos_diferentes(amb):
    alocar_no_mesmo_servico(amb["db"], amb["programa"], amb["preceptor"], nome="Ambulatório")
    alocar_no_mesmo_servico(amb["db"], amb["programa"], amb["residente"], nome="Enfermaria")
    amb["db"].commit()
    r = _confirmar(amb, _criar(amb)["id"])
    assert r.status_code == 400


def test_confirmacao_aceita_no_mesmo_servico(amb):
    alocar_no_mesmo_servico(amb["db"], amb["programa"], amb["preceptor"], amb["residente"])
    amb["db"].commit()
    criada = _criar(amb)
    assert criada["data_atividade"] == date.today().isoformat()
    r = _confirmar(amb, criada["id"])
    assert r.status_code == 200, r.text
    assert r.json()["confirmado"] is True


def test_data_atividade_fora_do_periodo_da_alocacao(amb):
    servico = Servico(nome="Centro Cirúrgico", programa_id=amb["programa"].id)
    amb["db"].add(servico)
    amb["db"].flush()
    hoje = date.today()
    for u in (amb["preceptor"], amb["residente"]):
        amb["db"].add(
            Alocacao(
                usuario_id=u.id,
                servico_id=servico.id,
                data_inicio=hoje - timedelta(days=10),
                data_fim=hoje,
            )
        )
    amb["db"].commit()

    antiga = _criar(amb, data_atividade=(hoje - timedelta(days=30)).isoformat())
    assert _confirmar(amb, antiga["id"]).status_code == 400

    dentro = _criar(amb, data_atividade=(hoje - timedelta(days=5)).isoformat())
    assert _confirmar(amb, dentro["id"]).status_code == 200


def test_data_atividade_no_futuro_rejeitada(amb):
    amb["como"]("preceptor")
    r = amb["c"].post(
        f"{API}/avaliacoes",
        json={
            "residente_id": str(amb["residente"].id),
            "instrumento": "osats",
            "itens": _itens("osats", 4),
            "data_atividade": (date.today() + timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------
# Rotas de alocação
# --------------------------------------------------------------------------


def _servico(amb):
    s = Servico(nome="Enfermaria", programa_id=amb["programa"].id)
    amb["db"].add(s)
    amb["db"].commit()
    return s


def _corpo_alocacao(usuario, servico, inicio=None, fim=None):
    hoje = date.today()
    return {
        "usuario_id": str(usuario.id),
        "servico_id": str(servico.id),
        "data_inicio": (inicio or hoje - timedelta(days=30)).isoformat(),
        "data_fim": (fim or hoje + timedelta(days=30)).isoformat(),
    }


def test_admin_cria_alocacao(amb):
    servico = _servico(amb)
    amb["como"]("admin")
    r = amb["c"].post(f"{API}/alocacoes", json=_corpo_alocacao(amb["residente"], servico))
    assert r.status_code == 201, r.text
    assert amb["db"].scalar(select(Alocacao)).usuario_id == amb["residente"].id


def test_preceptor_nao_cria_alocacao(amb):
    servico = _servico(amb)
    amb["como"]("preceptor")
    r = amb["c"].post(f"{API}/alocacoes", json=_corpo_alocacao(amb["preceptor"], servico))
    assert r.status_code == 403


def test_admin_nao_e_alocado(amb):
    servico = _servico(amb)
    amb["como"]("admin")
    r = amb["c"].post(f"{API}/alocacoes", json=_corpo_alocacao(amb["admin"], servico))
    assert r.status_code == 400


def test_alocacao_com_datas_invertidas(amb):
    servico = _servico(amb)
    amb["como"]("admin")
    hoje = date.today()
    r = amb["c"].post(
        f"{API}/alocacoes",
        json=_corpo_alocacao(amb["residente"], servico, inicio=hoje, fim=hoje - timedelta(days=1)),
    )
    assert r.status_code == 422


def test_nao_admin_so_lista_as_proprias(amb):
    alocar_no_mesmo_servico(amb["db"], amb["programa"], amb["preceptor"], amb["residente"])
    amb["db"].commit()

    amb["como"]("residente")
    r = amb["c"].get(f"{API}/alocacoes")
    assert r.status_code == 200
    assert {a["usuario_id"] for a in r.json()} == {str(amb["residente"].id)}

    r = amb["c"].get(f"{API}/alocacoes", params={"usuario_id": str(amb["preceptor"].id)})
    assert r.status_code == 403

    amb["como"]("admin")
    assert len(amb["c"].get(f"{API}/alocacoes").json()) == 2


# --------------------------------------------------------------------------
# Alertas de anomalia
# --------------------------------------------------------------------------


def test_alerta_de_preenchimento_rapido(amb):
    alocar_no_mesmo_servico(amb["db"], amb["programa"], amb["preceptor"], amb["residente"])
    amb["db"].commit()

    r = _confirmar(amb, _criar(amb)["id"], tempo_preenchimento_segundos=5)
    assert r.status_code == 200, r.text
    r = _confirmar(amb, _criar(amb)["id"], tempo_preenchimento_segundos=120)
    assert r.status_code == 200

    amb["como"]("admin")
    alertas = amb["c"].get(f"{API}/alertas-anomalia").json()
    assert [a["tipo_alerta"] for a in alertas] == ["velocidade_suspeita"]
    assert alertas[0]["detalhes"]["tempo_segundos"] == 5


def test_so_admin_lista_alertas(amb):
    amb["como"]("preceptor")
    assert amb["c"].get(f"{API}/alertas-anomalia").status_code == 403


def test_alerta_de_notas_uniformes_dispara_uma_vez(amb):
    alocar_no_mesmo_servico(amb["db"], amb["programa"], amb["preceptor"], amb["residente"])
    amb["db"].commit()

    for _ in range(anomalias_service.JANELA_UNIFORMIDADE + 2):
        assert _confirmar(amb, _criar(amb, nota=5)["id"]).status_code == 200

    tipos = list(amb["db"].scalars(select(AlertaAnomalia.tipo_alerta)))
    assert tipos.count("notas_uniformes") == 1
    # 12 confirmações no mesmo dia também passam do limiar de volume.
    assert tipos.count("volume_atipico") == 1


def _avaliacao_confirmada(db, avaliador, residente, nota):
    a = Avaliacao(
        residente_id=residente.id,
        avaliador_id=avaliador.id,
        instrumento="osats",
        itens="[]",
        nota=nota,
        confirmado=True,
        confirmado_em=agora_utc() - timedelta(days=2),
    )
    db.add(a)
    db.flush()
    return a


def test_alerta_de_leniencia(amb):
    db = amb["db"]
    # 30+ notas dos demais avaliadores, variando em torno do meio da escala.
    for i in range(anomalias_service.AMOSTRA_MIN_DEMAIS):
        _avaliacao_confirmada(db, amb["outro_preceptor"], amb["residente"], 18 + (i % 5))
    # O preceptor avaliado dá nota máxima sempre (mas em dias variados,
    # para não confundir com volume).
    for _ in range(anomalias_service.AMOSTRA_MIN_AVALIADOR - 1):
        _avaliacao_confirmada(db, amb["preceptor"], amb["residente"], 35)
    ultima = _avaliacao_confirmada(db, amb["preceptor"], amb["residente"], 34)

    alertas = anomalias_service.analisar_avaliacao(db, ultima)
    assert "leniencia" in [a.tipo_alerta for a in alertas]


def test_leniencia_nao_dispara_sem_amostra_suficiente(amb):
    db = amb["db"]
    for _ in range(5):
        _avaliacao_confirmada(db, amb["outro_preceptor"], amb["residente"], 20)
    for _ in range(anomalias_service.AMOSTRA_MIN_AVALIADOR):
        ultima = _avaliacao_confirmada(db, amb["preceptor"], amb["residente"], 35)
    tipos = [a.tipo_alerta for a in anomalias_service.analisar_avaliacao(db, ultima)]
    assert "leniencia" not in tipos
