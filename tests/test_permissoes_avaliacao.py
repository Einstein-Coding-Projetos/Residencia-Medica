import uuid

import pytest
from fastapi import HTTPException

from app.core.permissoes_avaliacao import exigir_pode_avaliar, pode_avaliar
from app.db.models import Papel, Usuario


def _usuario(papel: Papel, programa_id=None) -> Usuario:
    return Usuario(
        id=uuid.uuid4(),
        nome="Teste",
        email=f"{uuid.uuid4()}@teste.com",
        senha_hash="x",
        papel=papel,
        programa_id=programa_id,
    )


def test_preceptor_pode_avaliar_residente_mesmo_programa():
    programa_id = uuid.uuid4()
    preceptor = _usuario(Papel.PRECEPTOR, programa_id)
    residente = _usuario(Papel.RESIDENTE, programa_id)
    assert pode_avaliar(preceptor, residente) is True


def test_preceptor_nao_pode_avaliar_residente_de_outro_programa():
    preceptor = _usuario(Papel.PRECEPTOR, uuid.uuid4())
    residente = _usuario(Papel.RESIDENTE, uuid.uuid4())
    assert pode_avaliar(preceptor, residente) is False


def test_administrador_nunca_avalia():
    admin = _usuario(Papel.ADMINISTRADOR)
    residente = _usuario(Papel.RESIDENTE)
    assert pode_avaliar(admin, residente) is False


def test_residente_nao_pode_avaliar_residente():
    residente_a = _usuario(Papel.RESIDENTE)
    residente_b = _usuario(Papel.RESIDENTE)
    assert pode_avaliar(residente_a, residente_b) is False


def test_exigir_pode_avaliar_levanta_403():
    admin = _usuario(Papel.ADMINISTRADOR)
    residente = _usuario(Papel.RESIDENTE)
    with pytest.raises(HTTPException) as exc:
        exigir_pode_avaliar(admin, residente)
    assert exc.value.status_code == 403