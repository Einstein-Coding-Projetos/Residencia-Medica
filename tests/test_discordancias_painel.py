"""Sprint 4: notificações, discordância formal (7 dias) e painéis por perfil."""

import uuid
from datetime import timedelta

from sqlalchemy import select

from app.core.instrumentos import obter_instrumento
from app.db.models import Avaliacao, Notificacao, agora_utc
from tests.utils_alocacao import alocar_no_mesmo_servico

API = "/api/v1"
MOTIVO = "A nota não reflete o procedimento: conduzi todas as etapas principais."


def _itens(codigo, nota):
    return [{"dominio": d, "nota": nota} for d in obter_instrumento(codigo).codigos_dominios]


def _avaliacao_confirmada(amb, avaliador="preceptor", residente="residente"):
    amb["como"](avaliador)
    r = amb["c"].post(
        f"{API}/avaliacoes",
        json={"residente_id": str(amb[residente].id), "instrumento": "osats", "itens": _itens("osats", 3)},
    )
    assert r.status_code == 201, r.text
    r = amb["c"].post(f"{API}/avaliacoes/{r.json()['id']}/confirmar", json={"confirmo_observacao_direta": True})
    assert r.status_code == 200, r.text
    return r.json()


def _preparar(amb):
    alocar_no_mesmo_servico(
        amb["db"], amb["programa"], amb["preceptor"], amb["outro_preceptor"], amb["residente"], amb["outro_residente"]
    )
    amb["db"].commit()


def _discordar(amb, avaliacao_id, quem="residente", motivo=MOTIVO):
    amb["como"](quem)
    return amb["c"].post(f"{API}/avaliacoes/{avaliacao_id}/discordancia", json={"motivo": motivo})


# --------------------------------------------------------------------------
# Notificações
# --------------------------------------------------------------------------


def test_residente_e_notificado_ao_receber_avaliacao_e_marca_como_lida(amb_gov):
    _preparar(amb_gov)
    _avaliacao_confirmada(amb_gov)

    amb_gov["como"]("residente")
    lista = amb_gov["c"].get(f"{API}/notificacoes", params={"nao_lidas": True}).json()
    assert [n["tipo"] for n in lista] == ["avaliacao_recebida"]
    assert "7 dias" in lista[0]["mensagem"]

    r = amb_gov["c"].post(f"{API}/notificacoes/{lista[0]['id']}/lida")
    assert r.status_code == 200
    assert r.json()["lida_em"] is not None
    assert amb_gov["c"].get(f"{API}/notificacoes", params={"nao_lidas": True}).json() == []


def test_nao_marca_notificacao_de_outro_usuario(amb_gov):
    _preparar(amb_gov)
    _avaliacao_confirmada(amb_gov)
    amb_gov["como"]("residente")
    nid = amb_gov["c"].get(f"{API}/notificacoes").json()[0]["id"]
    amb_gov["como"]("outro_residente")
    assert amb_gov["c"].post(f"{API}/notificacoes/{nid}/lida").status_code == 404


# --------------------------------------------------------------------------
# Discordância formal
# --------------------------------------------------------------------------


def test_fluxo_completo_de_discordancia(amb_gov):
    db = amb_gov["db"]
    _preparar(amb_gov)
    avaliacao = _avaliacao_confirmada(amb_gov)

    r = _discordar(amb_gov, avaliacao["id"])
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["status"] == "aberta" and len(d["hash_integridade"]) == 64

    tipos = lambda u: [n.tipo for n in db.scalars(select(Notificacao).where(Notificacao.usuario_id == amb_gov[u].id))]
    assert "discordancia_aberta" in tipos("preceptor")
    assert "discordancia_aberta" in tipos("admin")

    # Avaliação original intacta.
    original = db.get(Avaliacao, uuid.UUID(avaliacao["id"]))
    assert original.hash_integridade == avaliacao["hash_integridade"]
    assert original.nota == avaliacao["nota"]

    amb_gov["como"]("outro_preceptor")
    resp = {"resposta": "Mantenho a nota: a etapa de hemostasia precisou de intervenção."}
    assert amb_gov["c"].post(f"{API}/discordancias/{d['id']}/resposta", json=resp).status_code == 403

    amb_gov["como"]("preceptor")
    r = amb_gov["c"].post(f"{API}/discordancias/{d['id']}/resposta", json=resp)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "respondida" and len(r.json()["hash_resposta"]) == 64
    assert amb_gov["c"].post(f"{API}/discordancias/{d['id']}/resposta", json=resp).status_code == 423
    assert "discordancia_respondida" in tipos("residente")


def test_regras_de_abertura(amb_gov):
    _preparar(amb_gov)
    avaliacao = _avaliacao_confirmada(amb_gov)

    assert _discordar(amb_gov, avaliacao["id"], motivo="curto").status_code == 422
    assert _discordar(amb_gov, avaliacao["id"], quem="outro_residente").status_code == 404
    assert _discordar(amb_gov, avaliacao["id"], quem="preceptor").status_code == 403
    assert _discordar(amb_gov, avaliacao["id"]).status_code == 201
    assert _discordar(amb_gov, avaliacao["id"]).status_code == 409


def test_nao_discorda_de_rascunho(amb_gov):
    _preparar(amb_gov)
    amb_gov["como"]("preceptor")
    r = amb_gov["c"].post(
        f"{API}/avaliacoes",
        json={"residente_id": str(amb_gov["residente"].id), "instrumento": "osats", "itens": _itens("osats", 3)},
    )
    assert _discordar(amb_gov, r.json()["id"]).status_code == 400


def test_prazo_de_7_dias(amb_gov):
    db = amb_gov["db"]
    _preparar(amb_gov)
    avaliacao = _avaliacao_confirmada(amb_gov)
    registro = db.get(Avaliacao, uuid.UUID(avaliacao["id"]))
    registro.confirmado_em = agora_utc() - timedelta(days=7, minutes=1)
    db.commit()
    r = _discordar(amb_gov, avaliacao["id"])
    assert r.status_code == 400
    assert "7 dias" in r.json()["detail"]


def test_listagem_respeita_papel(amb_gov):
    _preparar(amb_gov)
    a1 = _avaliacao_confirmada(amb_gov)
    a2 = _avaliacao_confirmada(amb_gov, avaliador="outro_preceptor", residente="outro_residente")
    _discordar(amb_gov, a1["id"])
    _discordar(amb_gov, a2["id"], quem="outro_residente")

    def ver(quem, **params):
        amb_gov["como"](quem)
        return [d["avaliacao_id"] for d in amb_gov["c"].get(f"{API}/discordancias", params=params).json()]

    assert ver("residente") == [a1["id"]]
    assert ver("preceptor") == [a1["id"]]
    assert sorted(ver("admin")) == sorted([a1["id"], a2["id"]])
    assert ver("admin", status_filtro="respondida") == []


# --------------------------------------------------------------------------
# Painéis
# --------------------------------------------------------------------------


def test_painel_residente(amb_gov):
    _preparar(amb_gov)
    a = _avaliacao_confirmada(amb_gov)
    amb_gov["como"]("residente")
    p = amb_gov["c"].get(f"{API}/dashboard").json()
    assert p["papel"] == "residente"
    assert p["avaliacoes_recebidas"] == 1 and p["avaliacoes_no_mes"] == 1
    assert p["ultimas_avaliacoes"][0]["id"] == a["id"]
    assert p["ultimas_avaliacoes"][0]["avaliador_nome"] == "Dr. Bruno"
    assert p["ultimas_avaliacoes"][0]["pode_discordar_ate"] is not None
    assert p["certificacao"]["bloqueada"] is False
    assert p["notificacoes_nao_lidas"] == 1

    _discordar(amb_gov, a["id"])
    amb_gov["como"]("residente")
    p = amb_gov["c"].get(f"{API}/dashboard").json()
    assert p["ultimas_avaliacoes"][0]["pode_discordar_ate"] is None
    assert p["discordancias"] == {"abertas": 1, "respondidas": 0}


def test_painel_preceptor(amb_gov):
    _preparar(amb_gov)
    a = _avaliacao_confirmada(amb_gov)
    _discordar(amb_gov, a["id"])
    amb_gov["como"]("preceptor")
    p = amb_gov["c"].get(f"{API}/dashboard").json()
    assert p["papel"] == "preceptor"
    assert {r["nome"] for r in p["residentes_alocados_hoje"]} == {"Ana", "Beto"}
    assert p["avaliacoes_confirmadas_no_mes"] == 1
    assert [x["residente_nome"] for x in p["pendencias_do_mes"]] == ["Beto"]
    assert len(p["discordancias_aguardando_resposta"]) == 1


def test_painel_r4_sem_pendencias_obrigatorias(amb_gov):
    amb_gov["como"]("r4")
    p = amb_gov["c"].get(f"{API}/dashboard").json()
    assert p["papel"] == "avaliador_intermediario"
    assert "pendencias_do_mes" not in p


def test_painel_admin(amb_gov):
    _preparar(amb_gov)
    a = _avaliacao_confirmada(amb_gov)
    _discordar(amb_gov, a["id"])
    amb_gov["como"]("admin")
    p = amb_gov["c"].get(f"{API}/dashboard").json()
    assert p["papel"] == "administrador"
    assert p["usuarios_por_papel"]["residente"] == 2
    assert p["avaliacoes_confirmadas_no_mes"] == 1
    # Ana avaliada por Bruno; faltam Bruno->Beto, Lia->Ana, Lia->Beto.
    assert p["pendencias_do_mes"] == 3
    assert p["discordancias_abertas"] == 1
    assert p["residentes_com_certificacao_bloqueada"] == 0
