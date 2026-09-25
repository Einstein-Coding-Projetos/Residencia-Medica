"""Portfólio do residente: agregação, permissões, EPAs (adaptador) e PDF."""

import io
import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import usuario_atual
from app.core import portfolio_epas
from app.core.instrumentos import obter_instrumento
from app.db.models import Base, Especialidade, LogAuditoria, Papel, Programa, Usuario
from app.db.session import get_db
from app.main import app

API = "/api/v1"


@pytest.fixture()
def amb(monkeypatch):
    # Por padrão, simula "tarefa 1 ainda não entregue".
    monkeypatch.setattr(portfolio_epas, "_provedor", lambda: None)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    esp = Especialidade(nome=f"Cirurgia Geral {uuid.uuid4()}")
    db.add(esp)
    db.flush()
    progs = []
    for _ in range(2):
        prog = Programa(nome="Residência em Cirurgia Geral", especialidade_id=esp.id, instituicao="HSPM")
        db.add(prog)
        db.flush()
        progs.append(prog)

    def usuario(papel, nome, programa=progs[0]):
        u = Usuario(nome=nome, email=f"{uuid.uuid4()}@t.br", senha_hash="x", papel=papel,
                    programa_id=programa.id)
        db.add(u)
        db.flush()
        return u

    ctx = {
        "residente": usuario(Papel.RESIDENTE, "Ana Souza"),
        "outro_residente": usuario(Papel.RESIDENTE, "Beto Dias"),
        "residente_fora": usuario(Papel.RESIDENTE, "Caio Fora", progs[1]),
        "preceptor": usuario(Papel.PRECEPTOR, "Dr. Bruno Lima"),
        "preceptor_fora": usuario(Papel.PRECEPTOR, "Dr. Fora", progs[1]),
        "admin": usuario(Papel.ADMINISTRADOR, "Carla Admin"),
        "db": db,
    }
    db.commit()
    estado = {"usuario": ctx["residente"]}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[usuario_atual] = lambda: estado["usuario"]
    ctx["c"] = TestClient(app)
    ctx["como"] = lambda nome: estado.__setitem__("usuario", ctx[nome])
    yield ctx
    app.dependency_overrides.clear()
    db.close()


def _itens(codigo, nota):
    return [{"dominio": d, "nota": nota} for d in obter_instrumento(codigo).codigos_dominios]


def _avaliar(amb, corpo, confirmar=True):
    amb["como"]("preceptor")
    corpo = {"residente_id": str(amb["residente"].id), "observacoes": "", **corpo}
    r = amb["c"].post(f"{API}/avaliacoes", json=corpo)
    assert r.status_code == 201, r.text
    if confirmar:
        r = amb["c"].post(f"{API}/avaliacoes/{r.json()['id']}/confirmar",
                          json={"confirmo_observacao_direta": True})
        assert r.status_code == 200, r.text
    return r.json()


def _procedimento(amb, nome, participacao, aprovado=None):
    amb["como"]("residente")
    r = amb["c"].post(f"{API}/procedimentos", json={
        "nome": nome, "participacao": participacao,
        "data_realizacao": (date.today() - timedelta(days=3)).isoformat(),
    })
    assert r.status_code == 201, r.text
    if aprovado is not None:
        amb["como"]("preceptor")
        corpo = {"aprovado": aprovado} if aprovado else {"aprovado": False, "motivo_recusa": "duplicado"}
        assert amb["c"].post(f"{API}/procedimentos/{r.json()['id']}/decidir", json=corpo).status_code == 200


def _meu(amb):
    amb["como"]("residente")
    r = amb["c"].get(f"{API}/portfolio/meu")
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
def test_portfolio_vazio_funciona(amb):
    p = _meu(amb)
    assert p["residente"]["nome"] == "Ana Souza"
    assert p["residente"]["instituicao"] == "HSPM"
    assert p["resumo"]["total_avaliacoes"] == 0
    assert p["instrumentos"] == [] and p["zwisch"] == [] and p["avaliacoes"] == []
    # Sem a tarefa 1: mostra as 16 EPAs do documento, sem nível atual
    epas = p["epas"]
    assert epas["niveis_do_sistema"] is False and epas["comparavel"] is False
    assert epas["total"] == 16 and epas["anos"] == ["R1", "R2", "R3"]
    assert {e["situacao"] for e in epas["itens"]} == {"sem_nivel"}
    assert epas["itens"][0]["codigo"] == "EPA 1"
    assert epas["itens"][0]["niveis_esperados"] == {"R1": 2, "R2": 3, "R3": 5}
    assert "ainda não estão no sistema" in epas["mensagem"]
    assert p["resumo"]["epas_comparavel"] is False


def test_so_avaliacoes_confirmadas_entram(amb):
    _avaliar(amb, {"instrumento": "osats", "itens": _itens("osats", 3), "observacoes": "Bom fluxo."})
    _avaliar(amb, {"instrumento": "osats", "itens": _itens("osats", 5)}, confirmar=False)  # rascunho

    p = _meu(amb)
    assert p["resumo"]["total_avaliacoes"] == 1
    osats = p["instrumentos"][0]
    assert osats["codigo"] == "osats" and osats["quantidade"] == 1
    assert osats["ultima_nota"] == 21  # soma, não média
    assert osats["ultima_faixa"] == "Assistência ocasional"
    assert {d["media"] for d in osats["media_por_dominio"]} == {3}
    av = p["avaliacoes"][0]
    assert av["avaliador_nome"] == "Dr. Bruno Lima"
    assert av["observacoes"] == "Bom fluxo."
    assert len(av["hash_integridade"]) == 64


def test_evolucao_media_e_faixas(amb):
    _avaliar(amb, {"instrumento": "mini_cex", "itens": _itens("mini_cex", 4)})  # 20
    _avaliar(amb, {"instrumento": "mini_cex", "itens": _itens("mini_cex", 8)})  # 40
    inst = _meu(amb)["instrumentos"][0]
    assert [pt["nota"] for pt in inst["evolucao"]] == [20, 40]
    assert inst["media"] == 30 and inst["melhor"] == 40
    contagem = {f["rotulo"]: f["quantidade"] for f in inst["faixas"]}
    assert contagem == {"insatisfatorio": 0, "em_desenvolvimento": 1, "satisfatorio": 1}


def test_zwisch_agrupa_por_etapa_com_nivel_mais_recente(amb):
    for nivel in (1, 3):
        _avaliar(amb, {"instrumento": "zwisch", "etapa_cirurgica": "Dissecção", "nivel_autonomia": nivel})
    _avaliar(amb, {"instrumento": "zwisch", "etapa_cirurgica": "Fechamento", "nivel_autonomia": 4})
    p = _meu(amb)
    etapas = {e["etapa"]: e for e in p["zwisch"]}
    assert etapas["Dissecção"]["nivel_atual"] == 3
    assert etapas["Dissecção"]["historico"] == [1, 3]
    assert etapas["Fechamento"]["nivel_texto"].startswith("Z4")
    assert p["instrumentos"] == []  # Zwisch não vira gráfico de soma
    assert p["resumo"]["instrumentos_utilizados"] == 1


def test_setq_nunca_aparece_no_portfolio(amb):
    amb["como"]("residente")
    r = amb["c"].post(f"{API}/avaliacoes/setq", json={
        "preceptor_id": str(amb["preceptor"].id), "itens": _itens("setq_smart", 5),
    })
    assert r.status_code == 201
    amb["c"].post(f"{API}/avaliacoes/{r.json()['id']}/confirmar", json={"confirmo_observacao_direta": True})

    assert _meu(amb)["avaliacoes"] == []
    amb["como"]("admin")
    # nem no portfólio do "sujeito" (o preceptor não é residente -> 404)
    assert amb["c"].get(f"{API}/portfolio/{amb['preceptor'].id}").status_code == 404


def test_so_procedimentos_validados_contam(amb):
    _procedimento(amb, "Apendicectomia", "cirurgiao_principal", aprovado=True)
    _procedimento(amb, "Apendicectomia", "primeiro_auxiliar", aprovado=True)
    _procedimento(amb, "Herniorrafia", "segundo_auxiliar", aprovado=True)
    _procedimento(amb, "Herniorrafia", "cirurgiao_principal", aprovado=False)
    _procedimento(amb, "Colecistectomia", "cirurgiao_principal")  # pendente

    proc = _meu(amb)["procedimentos"]
    assert proc["total_validados"] == 3
    assert proc["pendentes"] == 1 and proc["recusados"] == 1
    assert proc["por_nome"][0] == {
        "nome": "Apendicectomia", "total": 2,
        "cirurgiao_principal": 1, "primeiro_auxiliar": 1, "segundo_auxiliar": 0,
    }
    assert {c["participacao"]: c["quantidade"] for c in proc["por_participacao"]}["cirurgiao_principal"] == 1


@pytest.mark.parametrize(
    "quem, esperado",
    [("residente", 200), ("preceptor", 200), ("admin", 200),
     ("outro_residente", 403), ("preceptor_fora", 403)],
)
def test_quem_pode_abrir_o_portfolio(amb, quem, esperado):
    amb["como"](quem)
    assert amb["c"].get(f"{API}/portfolio/{amb['residente'].id}").status_code == esperado
    assert amb["c"].get(f"{API}/portfolio/{amb['residente'].id}/pdf").status_code == esperado


def test_meu_portfolio_so_para_residente(amb):
    amb["como"]("preceptor")
    assert amb["c"].get(f"{API}/portfolio/meu").status_code == 400


def test_lista_de_residentes_visiveis(amb):
    amb["como"]("preceptor")
    nomes = [u["nome"] for u in amb["c"].get(f"{API}/portfolio/residentes").json()]
    assert nomes == ["Ana Souza", "Beto Dias"]
    amb["como"]("admin")
    assert len(amb["c"].get(f"{API}/portfolio/residentes").json()) == 3
    amb["como"]("residente")
    assert [u["nome"] for u in amb["c"].get(f"{API}/portfolio/residentes").json()] == ["Ana Souza"]


def test_epas_entram_quando_a_tarefa_1_existir(amb, monkeypatch):
    def progresso_falso(db, residente_id):
        return {
            "ano_residente": "R2",
            "epas": [
                {"codigo": "EPA9", "nivel_atual": 2, "observacoes_trimestre": 7},   # esperado R2 = 2
                {"codigo": 1, "nivel_atual": 2, "observacoes_trimestre": 13},      # esperado R2 = 3
                {"codigo": "EPA 12", "nivel_atual": None},
                {"codigo": "CCP 1", "nome": "Avaliando nódulo cervical", "nivel_atual": 3,
                 "especialidade": "Cabeça e Pescoço", "niveis_esperados": {"R4": 2, "R5": 3}},
            ],
        }

    monkeypatch.setattr(portfolio_epas, "_provedor", lambda: progresso_falso)
    p = _meu(amb)
    epas = p["epas"]
    assert epas["niveis_do_sistema"] is True and epas["ano_residente"] == "R2"
    assert epas["total"] == 4 and epas["atingidas"] == 1 and epas["abaixo"] == 1
    assert epas["mensagem"] is None and epas["comparavel"] is True
    assert epas["anos"] == ["R1", "R2", "R3", "R4", "R5"]
    por_codigo = {e["codigo"]: e for e in epas["itens"]}

    epa9 = por_codigo["EPA 9"]  # nome e mínimo vêm do catálogo
    assert epa9["nome"] == "Tratando pacientes com colecistopatia"
    assert epa9["situacao"] == "atingido" and epa9["minimo_trimestre"] == 12
    assert epa9["nivel_esperado_rotulo"] == "Supervisão direta"
    assert por_codigo["EPA 1"]["situacao"] == "abaixo" and por_codigo["EPA 1"]["nivel_esperado"] == 3
    assert por_codigo["EPA 12"]["situacao"] == "sem_nivel"
    # EPA fora do catálogo: sem esperado para R2 -> não dá para comparar
    assert por_codigo["CCP 1"]["situacao"] == "sem_referencia"
    assert p["residente"]["ano_residencia"] == "R2"
    assert p["resumo"]["epas_atingidas"] == 1

    amb["como"]("residente")
    pdf = amb["c"].get(f"{API}/portfolio/meu/pdf")
    texto = " ".join("".join(pg.extract_text() for pg in PdfReader(io.BytesIO(pdf.content)).pages).split())
    for trecho in ("Avaliando nódulo cervical", "Sem registro", "colecistopatia", "Ano: R2", "7 / 12"):
        assert trecho in texto, trecho


def test_epas_sem_ano_nao_comparam(amb, monkeypatch):
    monkeypatch.setattr(portfolio_epas, "_provedor",
                        lambda: lambda db, rid: [{"codigo": "EPA 3", "nivel_atual": 4}])
    epas = _meu(amb)["epas"]
    assert epas["itens"][0]["situacao"] == "sem_referencia"
    assert epas["comparavel"] is False and "ano de residência" in epas["mensagem"]


def test_epa_desconhecida_sem_dados_da_erro_claro(amb, monkeypatch):
    monkeypatch.setattr(portfolio_epas, "_provedor",
                        lambda: lambda db, rid: [{"codigo": "XYZ", "nivel_atual": 1}])
    with pytest.raises(portfolio_epas.ProgressoEPAInvalido, match="niveis_esperados"):
        portfolio_epas.progresso_epas(amb["db"], amb["residente"].id)


def test_pdf_exporta_conteudo_e_registra_auditoria(amb):
    _avaliar(amb, {"instrumento": "osats", "itens": _itens("osats", 4), "observacoes": "Ótima <hemostasia> & técnica"})
    _avaliar(amb, {"instrumento": "zwisch", "etapa_cirurgica": "Dissecção", "nivel_autonomia": 2})
    _procedimento(amb, "Apendicectomia", "cirurgiao_principal", aprovado=True)

    amb["como"]("preceptor")
    r = amb["c"].get(f"{API}/portfolio/{amb['residente'].id}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="portfolio-ana-souza-' in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF")

    leitor = PdfReader(io.BytesIO(r.content))
    texto = "".join(pg.extract_text() for pg in leitor.pages)
    for trecho in ("Ana Souza", "OSATS", "Apendicectomia", "Dissecção", "<hemostasia> & técnica",
                   "Tratando pacientes com colecistopatia", "12 vezes / trimestre", f"de {len(leitor.pages)}"):
        assert trecho in texto, trecho

    log = amb["db"].scalar(select(LogAuditoria).where(LogAuditoria.acao == "portfolio.exportado_pdf"))
    assert log is not None and log.usuario_id == amb["preceptor"].id


def test_pdf_com_portfolio_vazio(amb):
    amb["como"]("residente")
    r = amb["c"].get(f"{API}/portfolio/meu/pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
