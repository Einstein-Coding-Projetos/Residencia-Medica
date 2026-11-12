"""Sprint 4 — apoio às telas: listagem de usuários (aba Alocações),
bloqueio de certificação no portfólio/PDF e texto da declaração na ficha."""

import io
from datetime import date

from pypdf import PdfReader

from app.core.engajamento_service import verificar_engajamento
from app.db.models import Alocacao

API = "/api/v1"


def _omissao_em_setembro(amb):
    db = amb["db"]
    for u in (amb["preceptor"], amb["residente"]):
        db.add(Alocacao(usuario_id=u.id, servico_id=amb["enfermaria"].id,
                        data_inicio=date(2026, 9, 1), data_fim=date(2026, 9, 30)))
    db.flush()
    verificar_engajamento(db, date(2026, 10, 1))
    db.commit()


def test_admin_lista_usuarios_com_filtro(amb_gov):
    amb_gov["como"]("admin")
    todos = amb_gov["c"].get(f"{API}/usuarios").json()
    assert {u["nome"] for u in todos} >= {"Ana", "Beto", "Dr. Bruno", "Carla Admin"}
    residentes = amb_gov["c"].get(f"{API}/usuarios", params={"papel": "residente"}).json()
    assert sorted(u["nome"] for u in residentes) == ["Ana", "Beto"]


def test_so_admin_lista_usuarios(amb_gov):
    for quem in ("preceptor", "residente"):
        amb_gov["como"](quem)
        assert amb_gov["c"].get(f"{API}/usuarios").status_code == 403


def test_portfolio_sem_bloqueio(amb_gov):
    amb_gov["como"]("residente")
    p = amb_gov["c"].get(f"{API}/portfolio/meu").json()
    assert p["certificacao"]["bloqueada"] is False


def test_portfolio_e_pdf_mostram_bloqueio(amb_gov):
    _omissao_em_setembro(amb_gov)

    amb_gov["como"]("preceptor")
    p = amb_gov["c"].get(f"{API}/portfolio/{amb_gov['residente'].id}").json()
    assert p["certificacao"]["bloqueada"] is True
    assert "09/2026" in p["certificacao"]["motivo"]

    r = amb_gov["c"].get(f"{API}/portfolio/{amb_gov['residente'].id}/pdf")
    assert r.status_code == 200
    texto = " ".join(pg.extract_text() for pg in PdfReader(io.BytesIO(r.content)).pages)
    assert "CERTIFICAÇÃO BLOQUEADA" in texto
    assert "09/2026" in texto


def test_pdf_sem_bloqueio_nao_tem_aviso(amb_gov):
    amb_gov["como"]("residente")
    r = amb_gov["c"].get(f"{API}/portfolio/meu/pdf")
    texto = " ".join(pg.extract_text() for pg in PdfReader(io.BytesIO(r.content)).pages)
    assert "CERTIFICAÇÃO BLOQUEADA" not in texto


def test_instrumento_expoe_texto_da_declaracao(amb_gov):
    r = amb_gov["c"].get(f"{API}/instrumentos/osats").json()
    assert r["texto_confirmacao"].startswith("Confirmo que observei este residente")
