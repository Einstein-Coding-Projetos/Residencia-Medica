"""Testes do login e das travas de papel.

Rode com:  pytest -q
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import esquema_bearer  # noqa: F401  (garante import do módulo)
from app.core.auth_service import criar_usuario
from app.core.security import criar_access_token, gerar_hash_senha, verificar_senha
from app.db.models import Base, Especialidade, Papel
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
        "residente": criar_usuario(
            db_sessao, nome="Ana Residente", email="ana@hospital.br",
            senha=SENHA_OK, papel=Papel.RESIDENTE,
        ),
        "preceptor": criar_usuario(
            db_sessao, nome="Dr. Bruno", email="bruno@hospital.br",
            senha=SENHA_OK, papel=Papel.PRECEPTOR,
        ),
        "admin": criar_usuario(
            db_sessao, nome="Carla Admin", email="carla@hospital.br",
            senha=SENHA_OK, papel=Papel.ADMINISTRADOR,
        ),
    }
    db_sessao.commit()
    return criados


def logar(cliente, email: str, senha: str = SENHA_OK):
    return cliente.post(f"{PREFIXO}/auth/login", json={"email": email, "senha": senha})


def cabecalho(cliente, email: str) -> dict[str, str]:
    token = logar(cliente, email).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------------ senha ---

def test_senha_nunca_fica_em_texto_puro(db_sessao, usuarios):
    ana = usuarios["residente"]
    assert SENHA_OK not in ana.senha_hash
    assert ana.senha_hash.startswith("$2")  # prefixo do bcrypt


def test_hashes_da_mesma_senha_sao_diferentes():
    """Salt aleatório: duas contas com a mesma senha têm hashes distintos."""
    assert gerar_hash_senha(SENHA_OK) != gerar_hash_senha(SENHA_OK)


def test_verificacao_de_senha():
    h = gerar_hash_senha(SENHA_OK)
    assert verificar_senha(SENHA_OK, h)
    assert not verificar_senha("outra-senha", h)


# ------------------------------------------------------------------ login ---

def test_login_valido_devolve_token_e_usuario(cliente, usuarios):
    r = logar(cliente, "ana@hospital.br")
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["token_type"] == "bearer"
    assert corpo["usuario"]["papel"] == "residente"
    assert "senha_hash" not in str(corpo)


def test_login_com_senha_errada(cliente, usuarios):
    r = logar(cliente, "ana@hospital.br", senha="errada123")
    assert r.status_code == 401


def test_mensagem_de_erro_nao_revela_se_email_existe(cliente, usuarios):
    a = logar(cliente, "ana@hospital.br", senha="errada123").json()["detail"]
    b = logar(cliente, "ninguem@hospital.br", senha="errada123").json()["detail"]
    assert a == b


def test_email_nao_diferencia_maiuscula(cliente, usuarios):
    assert logar(cliente, "ANA@Hospital.BR").status_code == 200


def test_usuario_desativado_nao_loga(cliente, db_sessao, usuarios):
    usuarios["residente"].ativo = False
    db_sessao.commit()
    assert logar(cliente, "ana@hospital.br").status_code == 401


# ------------------------------------------------------------------ token ---

def test_rota_protegida_sem_token(cliente, usuarios):
    assert cliente.get(f"{PREFIXO}/auth/eu").status_code == 401


def test_token_adulterado_e_recusado(cliente, usuarios):
    token = logar(cliente, "ana@hospital.br").json()["access_token"]
    quebrado = token[:-4] + "aaaa"
    r = cliente.get(f"{PREFIXO}/auth/eu", headers={"Authorization": f"Bearer {quebrado}"})
    assert r.status_code == 401


def test_token_expirado_e_recusado(cliente, usuarios):
    token, _ = criar_access_token(
        usuario_id=usuarios["residente"].id,
        papel="residente",
        duracao=timedelta(seconds=-1),
    )
    r = cliente.get(f"{PREFIXO}/auth/eu", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_token_valido_identifica_usuario(cliente, usuarios):
    r = cliente.get(f"{PREFIXO}/auth/eu", headers=cabecalho(cliente, "bruno@hospital.br"))
    assert r.status_code == 200
    assert r.json()["email"] == "bruno@hospital.br"


def test_papel_alterado_invalida_token_antigo(cliente, db_sessao, usuarios):
    cab = cabecalho(cliente, "ana@hospital.br")
    usuarios["residente"].papel = Papel.PRECEPTOR
    db_sessao.commit()
    assert cliente.get(f"{PREFIXO}/auth/eu", headers=cab).status_code == 401


# ------------------------------------------------------------------- RBAC ---

@pytest.fixture()
def especialidade(db_sessao):
    esp = Especialidade(nome="Cirurgia")
    db_sessao.add(esp)
    db_sessao.commit()
    return esp


def _corpo_programa(especialidade_id) -> dict:
    return {
        "nome": "Cirurgia Geral",
        "especialidade_id": str(especialidade_id),
        "instituicao": "Hospital Universitário",
        "duracao_anos": 5,
    }


def test_administrador_cadastra_programa(cliente, usuarios, especialidade):
    r = cliente.post(
        f"{PREFIXO}/programas", json=_corpo_programa(especialidade.id),
        headers=cabecalho(cliente, "carla@hospital.br"),
    )
    assert r.status_code == 201


@pytest.mark.parametrize("email", ["ana@hospital.br", "bruno@hospital.br"])
def test_papel_sem_permissao_recebe_403(cliente, usuarios, especialidade, email):
    r = cliente.post(
        f"{PREFIXO}/programas", json=_corpo_programa(especialidade.id),
        headers=cabecalho(cliente, email),
    )
    assert r.status_code == 403


def test_administrador_nao_e_super_usuario(db_sessao, usuarios):
    """Regra do cronograma: admin é gestão, não acumula função clínica.

    Se alguém um dia colocar um atalho de super-usuário em `exigir_papeis`,
    este teste quebra.
    """
    from app.api.deps import exigir_papeis

    verificar = exigir_papeis(Papel.PRECEPTOR, Papel.AVALIADOR_INTERMEDIARIO)
    with pytest.raises(Exception) as erro:
        verificar(usuarios["admin"])
    assert getattr(erro.value, "status_code", None) == 403


def test_auditoria_registra_login(cliente, db_sessao, usuarios):
    from sqlalchemy import select

    from app.db.models import LogAuditoria

    logar(cliente, "ana@hospital.br")
    logar(cliente, "ana@hospital.br", senha="errada123")
    acoes = db_sessao.scalars(select(LogAuditoria.acao)).all()
    assert "login.aceito" in acoes
    assert "login.negado" in acoes
