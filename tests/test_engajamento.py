"""Sprint 4: engajamento obrigatório D15/D20/D25, escalada e omissão."""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.engajamento_service import bloqueios_certificacao, verificar_engajamento
from app.db.models import (
    AlertaEngajamento,
    Alocacao,
    Avaliacao,
    Notificacao,
    OmissaoAvaliacao,
)

API = "/api/v1"
SET_INICIO = date(2026, 9, 1)
SET_FIM = date(2026, 9, 30)


def _alocar(db, usuario, servico, inicio=SET_INICIO, fim=SET_FIM):
    db.add(Alocacao(usuario_id=usuario.id, servico_id=servico.id, data_inicio=inicio, data_fim=fim))
    db.flush()


def _avaliacao(db, avaliador, residente, dia, instrumento="osats"):
    db.add(
        Avaliacao(
            residente_id=residente.id,
            avaliador_id=avaliador.id,
            instrumento=instrumento,
            itens="[]",
            nota=20,
            confirmado=True,
            data_atividade=dia,
            confirmado_em=datetime.combine(dia, datetime.min.time(), tzinfo=timezone.utc),
        )
    )
    db.flush()


def _notificacoes(db, usuario, tipo=None):
    q = select(Notificacao).where(Notificacao.usuario_id == usuario.id)
    if tipo:
        q = q.where(Notificacao.tipo == tipo)
    return list(db.scalars(q))


def _par_padrao(amb):
    _alocar(amb["db"], amb["preceptor"], amb["enfermaria"])
    _alocar(amb["db"], amb["residente"], amb["enfermaria"])


def test_nada_antes_do_dia_15(amb_gov):
    _par_padrao(amb_gov)
    r = verificar_engajamento(amb_gov["db"], date(2026, 9, 14))
    assert r.alertas_criados == []
    assert _notificacoes(amb_gov["db"], amb_gov["preceptor"]) == []


def test_d15_alerta_preceptor_e_e_idempotente(amb_gov):
    db = amb_gov["db"]
    _par_padrao(amb_gov)

    r = verificar_engajamento(db, date(2026, 9, 15))
    assert len(r.alertas_criados) == 1
    assert r.alertas_criados[0]["marco"] == "D15"
    assert len(_notificacoes(db, amb_gov["preceptor"], "engajamento_d15")) == 1

    r = verificar_engajamento(db, date(2026, 9, 15))
    assert r.alertas_criados == []
    assert len(_notificacoes(db, amb_gov["preceptor"])) == 1


def test_job_atrasado_grava_marcos_mas_notifica_so_o_mais_recente(amb_gov):
    db = amb_gov["db"]
    _par_padrao(amb_gov)
    verificar_engajamento(db, date(2026, 9, 22))
    marcos = set(db.scalars(select(AlertaEngajamento.marco)))
    assert marcos == {"D15", "D20"}
    tipos = [n.tipo for n in _notificacoes(db, amb_gov["preceptor"])]
    assert tipos == ["engajamento_d20"]


def test_d25_escala_ao_administrador(amb_gov):
    db = amb_gov["db"]
    _par_padrao(amb_gov)
    verificar_engajamento(db, date(2026, 9, 15))
    verificar_engajamento(db, date(2026, 9, 20))
    r = verificar_engajamento(db, date(2026, 9, 25))
    assert r.escaladas == 1
    assert len(_notificacoes(db, amb_gov["admin"], "engajamento_escalada")) == 1
    assert len(_notificacoes(db, amb_gov["preceptor"])) == 3


def test_par_avaliado_no_mes_nao_gera_alerta(amb_gov):
    db = amb_gov["db"]
    _par_padrao(amb_gov)
    _avaliacao(db, amb_gov["preceptor"], amb_gov["residente"], date(2026, 9, 3))
    assert verificar_engajamento(db, date(2026, 9, 25)).alertas_criados == []


def test_setq_nao_conta_como_avaliacao_do_preceptor(amb_gov):
    db = amb_gov["db"]
    _par_padrao(amb_gov)
    # SETQ: residente avalia preceptor; não cumpre a obrigação do preceptor.
    _avaliacao(db, amb_gov["preceptor"], amb_gov["residente"], date(2026, 9, 3), "setq_smart")
    assert len(verificar_engajamento(db, date(2026, 9, 15)).alertas_criados) == 1


def test_servicos_diferentes_ou_periodos_que_nao_se_cruzam(amb_gov):
    db = amb_gov["db"]
    _alocar(db, amb_gov["preceptor"], amb_gov["enfermaria"], SET_INICIO, date(2026, 9, 10))
    _alocar(db, amb_gov["residente"], amb_gov["enfermaria"], date(2026, 9, 11), SET_FIM)
    _alocar(db, amb_gov["outro_residente"], amb_gov["ambulatorio"])
    assert verificar_engajamento(db, date(2026, 9, 25)).alertas_criados == []


def test_r4_nao_tem_engajamento_obrigatorio(amb_gov):
    db = amb_gov["db"]
    _alocar(db, amb_gov["r4"], amb_gov["enfermaria"])
    _alocar(db, amb_gov["residente"], amb_gov["enfermaria"])
    assert verificar_engajamento(db, date(2026, 9, 25)).alertas_criados == []


def test_mes_fechado_sem_avaliacao_bloqueia_certificacao_ate_lancamento_tardio(amb_gov):
    db = amb_gov["db"]
    _par_padrao(amb_gov)

    r = verificar_engajamento(db, date(2026, 10, 1))
    assert len(r.omissoes_registradas) == 1
    assert len(_notificacoes(db, amb_gov["admin"], "engajamento_omissao")) == 1
    assert [o.competencia for o in bloqueios_certificacao(db, amb_gov["residente"].id)] == [SET_INICIO]

    # Idempotente no dia seguinte.
    assert verificar_engajamento(db, date(2026, 10, 2)).omissoes_registradas == []
    assert len(list(db.scalars(select(OmissaoAvaliacao)))) == 1

    # Lançamento tardio com a data real da atividade em setembro.
    _avaliacao(db, amb_gov["preceptor"], amb_gov["residente"], date(2026, 9, 28))
    assert bloqueios_certificacao(db, amb_gov["residente"].id) == []
    # O registro da omissão continua existindo como histórico.
    assert len(list(db.scalars(select(OmissaoAvaliacao)))) == 1


# --------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------


def _par_hoje(amb):
    hoje = date.today()
    for u in (amb["preceptor"], amb["residente"]):
        _alocar(amb["db"], u, amb["enfermaria"], hoje - timedelta(days=60), hoje + timedelta(days=60))
    amb["db"].commit()


def test_api_pendencias_por_papel(amb_gov):
    _par_hoje(amb_gov)

    amb_gov["como"]("preceptor")
    r = amb_gov["c"].get(f"{API}/engajamento/pendencias")
    assert r.status_code == 200
    assert [p["residente_nome"] for p in r.json()] == ["Ana"]

    amb_gov["como"]("outro_preceptor")
    assert amb_gov["c"].get(f"{API}/engajamento/pendencias").json() == []

    amb_gov["como"]("admin")
    assert len(amb_gov["c"].get(f"{API}/engajamento/pendencias").json()) == 1

    amb_gov["como"]("residente")
    assert amb_gov["c"].get(f"{API}/engajamento/pendencias").status_code == 403


def test_api_verificar_somente_admin(amb_gov):
    _par_padrao(amb_gov)
    amb_gov["db"].commit()

    amb_gov["como"]("preceptor")
    assert amb_gov["c"].post(f"{API}/engajamento/verificar").status_code == 403

    amb_gov["como"]("admin")
    r = amb_gov["c"].post(f"{API}/engajamento/verificar", params={"data": "2026-10-01"})
    assert r.status_code == 200, r.text
    assert len(r.json()["omissoes_registradas"]) == 1

    r = amb_gov["c"].get(f"{API}/engajamento/omissoes")
    assert [o["ativa"] for o in r.json()] == [True]


def test_api_certificacao(amb_gov):
    _par_padrao(amb_gov)
    verificar_engajamento(amb_gov["db"], date(2026, 10, 1))
    amb_gov["db"].commit()

    amb_gov["como"]("residente")
    r = amb_gov["c"].get(f"{API}/engajamento/certificacao/{amb_gov['residente'].id}")
    assert r.status_code == 200
    assert r.json()["bloqueada"] is True
    assert "09/2026" in r.json()["motivo"]

    amb_gov["como"]("outro_residente")
    r = amb_gov["c"].get(f"{API}/engajamento/certificacao/{amb_gov['residente'].id}")
    assert r.status_code == 403
