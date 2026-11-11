
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.epa_service import (
    ObservacoesInsuficientesError,
    SaltoInvalidoError,
    _ano_residencia,
    atualizar_progresso,
    calcular_mapa_epas,
    contar_observacoes_trimestre,
)
from app.db.models import (
    EPA,
    Avaliacao,
    Base,
    Especialidade,
    Papel,
    Programa,
    Usuario,
    agora_utc,
)


def _sessao():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def _montar_cenario(db):
    especialidade = Especialidade(nome="Cirurgia Geral")
    db.add(especialidade)
    db.flush()

    programa = Programa(
        nome="Residência em Cirurgia Geral",
        especialidade_id=especialidade.id,
        instituicao="Hospital Teste",
        duracao_anos=3,
    )
    db.add(programa)
    db.flush()

    epa = EPA(
        codigo="EPA01",
        titulo="Admitindo o paciente cirúrgico",
        programa_id=programa.id,
        nivel_r1=2,
        nivel_r2=3,
        nivel_r3=5,
    )
    db.add(epa)
    db.flush()

    residente = Usuario(
        nome="Residente Teste",
        email=f"{uuid.uuid4()}@teste.com",
        senha_hash="x",
        papel=Papel.RESIDENTE,
        programa_id=programa.id,
        criado_em=agora_utc(),
    )
    db.add(residente)
    db.flush()

    return residente, epa


def _criar_epa(db, programa_id, codigo, *, nivel_r1=1, nivel_r2=2, nivel_r3=3):
    epa = EPA(
        codigo=codigo,
        titulo=f"EPA {codigo}",
        programa_id=programa_id,
        nivel_r1=nivel_r1,
        nivel_r2=nivel_r2,
        nivel_r3=nivel_r3,
    )
    db.add(epa)
    db.flush()
    return epa


def _criar_avaliacao_confirmada(
    db, residente, epa, *, instrumento="osats", confirmado_em=None, confirmado=True
):
    avaliacao = Avaliacao(
        residente_id=residente.id,
        avaliador_id=uuid.uuid4(),
        instrumento=instrumento,
        itens="[]",
        epa_id=epa.id if epa else None,
        nota=0.0,
        confirmado=confirmado,
        confirmado_em=confirmado_em or agora_utc(),
    )
    db.add(avaliacao)
    db.flush()
    return avaliacao


def test_mapa_sem_progresso_mostra_nivel_zero():
    db = _sessao()
    try:
        residente, epa = _montar_cenario(db)

        mapa = calcular_mapa_epas(db, residente)

        assert len(mapa) == 1
        assert mapa[0]["epa_id"] == epa.id
        assert mapa[0]["codigo"] == "EPA01"
        assert mapa[0]["nivel_atual"] == 0
        assert mapa[0]["nivel_esperado"] == 2
        assert mapa[0]["dentro_do_esperado"] is False
    finally:
        db.close()


def test_atualizar_progresso_reflete_no_mapa():
    db = _sessao()
    try:
        residente, epa = _montar_cenario(db)

        atualizar_progresso(
            db,
            residente_id=residente.id,
            epa=epa,
            nivel_atual=2,
            atualizado_por=uuid.uuid4(),
        )
        db.commit()

        mapa = calcular_mapa_epas(db, residente)

        assert mapa[0]["nivel_atual"] == 2
        assert mapa[0]["dentro_do_esperado"] is True
    finally:
        db.close()


# --------------------------------------------------------------------------
# Contagem de observações no trimestre
# --------------------------------------------------------------------------
def test_contar_observacoes_trimestre_conta_so_confirmadas_e_do_epa_certo():
    db = _sessao()
    try:
        residente, epa = _montar_cenario(db)
        outra_epa = _criar_epa(db, residente.programa_id, "EPA02")

        _criar_avaliacao_confirmada(db, residente, epa)
        _criar_avaliacao_confirmada(db, residente, epa)
        _criar_avaliacao_confirmada(db, residente, epa, confirmado=False)
        _criar_avaliacao_confirmada(db, residente, outra_epa)
        _criar_avaliacao_confirmada(db, residente, epa, instrumento="setq_smart")
        db.commit()

        total = contar_observacoes_trimestre(
            db, residente_id=residente.id, epa_id=epa.id
        )

        assert total == 2
    finally:
        db.close()


def test_contar_observacoes_trimestre_respeita_janela_do_trimestre():
    db = _sessao()
    try:
        residente, epa = _montar_cenario(db)

        # referencia em 15/ago/2026 -> trimestre = 01/jul a 30/set/2026.
        referencia = datetime(2026, 8, 15, tzinfo=timezone.utc)
        dentro_do_trimestre = datetime(2026, 7, 5, tzinfo=timezone.utc)
        fora_do_trimestre = datetime(2026, 6, 20, tzinfo=timezone.utc)

        _criar_avaliacao_confirmada(db, residente, epa, confirmado_em=dentro_do_trimestre)
        _criar_avaliacao_confirmada(db, residente, epa, confirmado_em=fora_do_trimestre)
        db.commit()

        total = contar_observacoes_trimestre(
            db, residente_id=residente.id, epa_id=epa.id, referencia=referencia,
        )

        assert total == 1
    finally:
        db.close()


# --------------------------------------------------------------------------
# Gate de observações mínimas antes de avançar de nível
# --------------------------------------------------------------------------
def test_atualizar_progresso_bloqueia_avanco_sem_observacoes_suficientes():
    db = _sessao()
    try:
        residente, epa = _montar_cenario(db)  # EPA01 -> minimo_trimestre=12

        atualizar_progresso(
            db, residente_id=residente.id, epa=epa, nivel_atual=1,
            atualizado_por=uuid.uuid4(),
        )
        db.commit()

        for _ in range(11):
            _criar_avaliacao_confirmada(db, residente, epa)
        db.commit()

        with pytest.raises(ObservacoesInsuficientesError):
            atualizar_progresso(
                db, residente_id=residente.id, epa=epa, nivel_atual=2,
                atualizado_por=uuid.uuid4(),
            )
    finally:
        db.close()


def test_atualizar_progresso_permite_avanco_com_observacoes_suficientes():
    db = _sessao()
    try:
        residente, epa = _montar_cenario(db)  # EPA01 -> minimo_trimestre=12

        atualizar_progresso(
            db, residente_id=residente.id, epa=epa, nivel_atual=1,
            atualizado_por=uuid.uuid4(),
        )
        db.commit()

        for _ in range(12):
            _criar_avaliacao_confirmada(db, residente, epa)
        db.commit()

        progresso = atualizar_progresso(
            db, residente_id=residente.id, epa=epa, nivel_atual=2,
            atualizado_por=uuid.uuid4(),
        )
        db.commit()

        assert progresso.nivel_atual == 2
    finally:
        db.close()


def test_atualizar_progresso_pula_gate_para_epa_sem_minimo_catalogado():
    db = _sessao()
    try:
        residente, _ = _montar_cenario(db)
        # EPA11 tem minimo_trimestre=None no catálogo (regra própria do CBC).
        epa11 = _criar_epa(db, residente.programa_id, "EPA11")

        atualizar_progresso(
            db, residente_id=residente.id, epa=epa11, nivel_atual=1,
            atualizado_por=uuid.uuid4(),
        )
        db.commit()

        # Nenhuma observação registrada — mesmo assim o avanço é permitido.
        progresso = atualizar_progresso(
            db, residente_id=residente.id, epa=epa11, nivel_atual=2,
            atualizado_por=uuid.uuid4(),
        )
        db.commit()

        assert progresso.nivel_atual == 2
    finally:
        db.close()


def test_atualizar_progresso_ainda_bloqueia_salto_de_30_dias_apos_gate_de_observacoes():
    db = _sessao()
    try:
        residente, epa = _montar_cenario(db)

        atualizar_progresso(
            db, residente_id=residente.id, epa=epa, nivel_atual=1,
            atualizado_por=uuid.uuid4(),
        )
        db.commit()

        for _ in range(12):
            _criar_avaliacao_confirmada(db, residente, epa)
        db.commit()

        with pytest.raises(SaltoInvalidoError):
            atualizar_progresso(
                db, residente_id=residente.id, epa=epa, nivel_atual=3,
                atualizado_por=uuid.uuid4(),
            )
    finally:
        db.close()


# --------------------------------------------------------------------------
# Ano de residência
# --------------------------------------------------------------------------
def test_ano_residencia_usa_data_inicio_programa_quando_presente():
    db = _sessao()
    try:
        residente, _ = _montar_cenario(db)
        residente.data_inicio_programa = date.today() - timedelta(days=400)

        assert _ano_residencia(residente) == 2
    finally:
        db.close()


def test_ano_residencia_cai_no_fallback_quando_ausente():
    db = _sessao()
    try:
        residente, _ = _montar_cenario(db)
        residente.data_inicio_programa = None
        residente.criado_em = agora_utc()

        assert _ano_residencia(residente) == 1
    finally:
        db.close()
