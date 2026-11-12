"""Login institucional (SSO / OpenID Connect) — provedor simulado.

O id_token é assinado de verdade com uma chave RSA gerada no teste; só a
busca do discovery e da chave pública (rede) é substituída.
"""

import time
from urllib.parse import parse_qs, unquote, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.api.routes import auth as rotas_auth
from app.core import sso_service
from app.core.config import settings
from app.core.security import ler_access_token
from app.db.models import LogAuditoria

API = "/api/v1"
ISSUER = "https://login.exemplo.test/tenant/v2.0"
CLIENT_ID = "app-residencia"


@pytest.fixture()
def chave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture()
def sso(monkeypatch, chave):
    for nome, valor in {
        "SSO_HABILITADO": True,
        "SSO_ISSUER": ISSUER,
        "SSO_CLIENT_ID": CLIENT_ID,
        "SSO_CLIENT_SECRET": "segredo",
        "SSO_NOME_PROVEDOR": "Microsoft institucional",
        "SSO_URL_FRONTEND": "http://front.test/login.html",
    }.items():
        monkeypatch.setattr(settings, nome, valor)
    monkeypatch.setattr(
        sso_service,
        "obter_discovery",
        lambda: {
            "issuer": ISSUER,
            "authorization_endpoint": "https://login.exemplo.test/authorize",
            "token_endpoint": "https://login.exemplo.test/token",
            "jwks_uri": "https://login.exemplo.test/keys",
            "id_token_signing_alg_values_supported": ["RS256"],
        },
    )
    monkeypatch.setattr(sso_service, "_chave_de_assinatura", lambda token, uri: chave.public_key())


def _id_token(chave, nonce, **extra):
    agora = int(time.time())
    claims = {"iss": ISSUER, "aud": CLIENT_ID, "iat": agora, "exp": agora + 300, "nonce": nonce, **extra}
    return jwt.encode(claims, chave, algorithm="RS256")


def _iniciar(c):
    r = c.get(f"{API}/auth/sso/iniciar", follow_redirects=False)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    return q["state"][0], q["nonce"][0], q


def _callback(c, monkeypatch, id_token, state):
    monkeypatch.setattr(rotas_auth, "trocar_codigo", lambda code: {"id_token": id_token})
    r = c.get(f"{API}/auth/sso/callback", params={"code": "abc", "state": state}, follow_redirects=False)
    assert r.status_code == 302
    fragmento = parse_qs(urlparse(r.headers["location"]).fragment)
    return {k: unquote(v[0]) for k, v in fragmento.items()}


def _acoes(db):
    return [l.acao for l in db.scalars(select(LogAuditoria))]


def test_desligado_por_padrao(amb_gov):
    r = amb_gov["c"].get(f"{API}/auth/sso/config").json()
    assert r["habilitado"] is False
    assert amb_gov["c"].get(f"{API}/auth/sso/iniciar", follow_redirects=False).status_code == 404


def test_config_e_redirect_para_o_provedor(amb_gov, sso):
    assert amb_gov["c"].get(f"{API}/auth/sso/config").json() == {
        "habilitado": True, "nome_provedor": "Microsoft institucional",
    }
    state, nonce, q = _iniciar(amb_gov["c"])
    assert q["client_id"] == [CLIENT_ID] and q["response_type"] == ["code"]
    assert sso_service.ler_state(state) == nonce


def test_login_sso_de_usuario_cadastrado(amb_gov, sso, chave, monkeypatch):
    ana = amb_gov["residente"]
    state, nonce, _ = _iniciar(amb_gov["c"])
    volta = _callback(amb_gov["c"], monkeypatch, _id_token(chave, nonce, email=ana.email.upper()), state)
    assert "sso" in volta, volta
    dados = ler_access_token(volta["sso"])
    assert dados.usuario_id == ana.id and dados.papel == "residente"
    assert "login.sso_aceito" in _acoes(amb_gov["db"])


def test_email_em_preferred_username(amb_gov, sso, chave, monkeypatch):
    bruno = amb_gov["preceptor"]
    state, nonce, _ = _iniciar(amb_gov["c"])
    volta = _callback(amb_gov["c"], monkeypatch, _id_token(chave, nonce, preferred_username=bruno.email), state)
    assert ler_access_token(volta["sso"]).usuario_id == bruno.id


def test_email_desconhecido_nao_cria_conta(amb_gov, sso, chave, monkeypatch):
    state, nonce, _ = _iniciar(amb_gov["c"])
    volta = _callback(amb_gov["c"], monkeypatch, _id_token(chave, nonce, email="novo@hospital.br"), state)
    assert "sso" not in volta
    assert "não está cadastrada" in volta["sso_erro"]
    assert "login.sso_negado" in _acoes(amb_gov["db"])


def test_usuario_inativo_e_recusado(amb_gov, sso, chave, monkeypatch):
    ana = amb_gov["residente"]
    ana.ativo = False
    amb_gov["db"].commit()
    state, nonce, _ = _iniciar(amb_gov["c"])
    volta = _callback(amb_gov["c"], monkeypatch, _id_token(chave, nonce, email=ana.email), state)
    assert "sso_erro" in volta


def test_state_adulterado_e_recusado(amb_gov, sso, chave, monkeypatch):
    _, nonce, _ = _iniciar(amb_gov["c"])
    volta = _callback(amb_gov["c"], monkeypatch, _id_token(chave, nonce, email=amb_gov["residente"].email), "xyz")
    assert "sso_erro" in volta


def test_state_expirado(sso):
    vencido = jwt.encode(
        {"fin": "sso_state", "nonce": "n", "exp": int(time.time()) - 5},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )
    with pytest.raises(sso_service.ErroSSO, match="demorou"):
        sso_service.ler_state(vencido)


def test_erro_do_provedor_volta_para_o_login(amb_gov, sso):
    r = amb_gov["c"].get(f"{API}/auth/sso/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert "sso_erro=" in r.headers["location"]


@pytest.mark.parametrize(
    "alteracao",
    [
        {"aud": "outro-app"},
        {"iss": "https://atacante.test"},
        {"nonce": "nonce-de-outra-sessao"},
        {"exp": int(time.time()) - 60},
    ],
)
def test_id_token_invalido_e_recusado(sso, chave, alteracao):
    claims = {"email": "a@b.c", **alteracao}
    token = _id_token(chave, claims.pop("nonce", "nonce-certo"), **claims)
    with pytest.raises(sso_service.ErroSSO):
        sso_service.validar_id_token(token, "nonce-certo")


def test_id_token_assinado_por_outra_chave(sso):
    intrusa = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(sso_service.ErroSSO):
        sso_service.validar_id_token(_id_token(intrusa, "n", email="a@b.c"), "n")


def test_id_token_hs256_com_client_secret_e_recusado(sso):
    agora = int(time.time())
    forjado = jwt.encode(
        {"iss": ISSUER, "aud": CLIENT_ID, "iat": agora, "exp": agora + 60, "nonce": "n", "email": "a@b.c"},
        "segredo-hmac-com-32-bytes-ou-mais!!", algorithm="HS256",
    )
    with pytest.raises(sso_service.ErroSSO):
        sso_service.validar_id_token(forjado, "n")


# --------------------------------------------------------------------------
# SETQ: quem o residente pode avaliar
# --------------------------------------------------------------------------


def test_setq_lista_preceptores_do_programa(amb_gov):
    amb_gov["como"]("residente")
    r = amb_gov["c"].get(f"{API}/avaliacoes/setq/preceptores")
    assert r.status_code == 200
    assert sorted(u["nome"] for u in r.json()) == ["Dr. Bruno", "Dra. Clara R4", "Dra. Lia"]


def test_setq_preceptores_so_para_residente(amb_gov):
    amb_gov["como"]("preceptor")
    assert amb_gov["c"].get(f"{API}/avaliacoes/setq/preceptores").status_code == 403
