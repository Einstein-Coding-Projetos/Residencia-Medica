import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.epa_service import atualizar_progresso, calcular_mapa_epas
from app.db.models import EPA, Base, Especialidade, Papel, Programa, Usuario, agora_utc


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
        especialidade_id=especialidade.id,
        numero=1,
        nome="Admitindo o paciente cirúrgico",
        nivel_esperado_r1=2,
        nivel_esperado_r2=3,
        nivel_esperado_r3=5,
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


def test_mapa_sem_progresso_mostra_nivel_zero():
    db = _sessao()
    residente, epa = _montar_cenario(db)

    mapa = calcular_mapa_epas(db, residente)

    assert len(mapa) == 1
    assert mapa[0]["nivel_atual"] == 0
    assert mapa[0]["dentro_do_esperado"] is False


def test_atualizar_progresso_reflete_no_mapa():
    db = _sessao()
    residente, epa = _montar_cenario(db)

    atualizar_progresso(
        db,
        residente_id=residente.id,
        epa_id=epa.id,
        nivel_atual=2,
        atualizado_por=uuid.uuid4(),
    )
    db.commit()

    mapa = calcular_mapa_epas(db, residente)
    assert mapa[0]["nivel_atual"] == 2
    assert mapa[0]["dentro_do_esperado"] is True