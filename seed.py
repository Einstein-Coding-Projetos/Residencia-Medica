from __future__ import annotations

from sqlalchemy import select

from app.core.auth_service import criar_usuario
from app.db.models import (
    Base,
    EPA,
    Especialidade,
    Papel,
    Programa,
    Servico,
    Usuario,
)
from app.db.session import SessionLocal, engine

SENHA_PADRAO = "Residencia2026"

CONTAS = [
    ("Ana Souza", "ana@hospital.br", Papel.RESIDENTE),
    ("Dr. Bruno Lima", "bruno@hospital.br", Papel.PRECEPTOR),
    ("Dra. Clara Reis", "clara@hospital.br", Papel.AVALIADOR_INTERMEDIARIO),
    ("Carla Menezes", "carla@hospital.br", Papel.ADMINISTRADOR),
]

EPAS = [
    (
        "EPA01",
        "ADMITINDO O PACIENTE CIRÚRGICO",
        2,
        3,
        5,
    ),
    (
        "EPA02",
        "CUIDANDO DO PACIENTE EM PRÉ-OPERATÓRIO",
        2,
        3,
        5,
    ),
    (
        "EPA03",
        "CUIDANDO DO PACIENTE EM PÓS-OPERATÓRIO",
        2,
        3,
        5,
    ),
    (
        "EPA04",
        "CUIDANDO DO PACIENTE CIRÚRGICO CRÍTICO",
        2,
        3,
        3,
    ),
    (
        "EPA05",
        "TRATANDO CIRURGICAMENTE O PACIENTE COM DEFEITO NA PAREDE ABDOMINAL",
        2,
        3,
        3,
    ),
    (
        "EPA06",
        "ACESSANDO A CAVIDADE ABDOMINAL DO PACIENTE CIRÚRGICO",
        2,
        3,
        3,
    ),
    (
        "EPA07",
        "TRATANDO DO PACIENTE COM APENDICITE AGUDA",
        2,
        3,
        3,
    ),
    (
        "EPA08",
        "ABORDANDO CIRURGICAMENTE O PACIENTE PARA VIA NUTRICIONAL ALTERNATIVA",
        2,
        3,
        3,
    ),
    (
        "EPA09",
        "TRATANDO PACIENTES COM COLECISTOPATIA",
        1,
        2,
        3,
    ),
    (
        "EPA10",
        "ABORDANDO O PACIENTE EM URGÊNCIA CIRÚRGICA",
        1,
        2,
        3,
    ),
    (
        "EPA11",
        "ABORDANDO CIRURGICAMENTE O PACIENTE COM CÂNCER DO APARELHO DIGESTIVO",
        1,
        2,
        3,
    ),
    (
        "EPA12",
        "ABORDANDO O PACIENTE PARA CATETERIZAÇÕES E SONDAGENS",
        3,
        4,
        5,
    ),
    (
        "EPA13",
        "ABORDANDO O PACIENTE PARA ACESSO VENOSO CENTRAL/DISSECÇÃO VENOSA",
        3,
        4,
        5,
    ),
    (
        "EPA14",
        "ABORDANDO O PACIENTE PARA PEQUENOS PROCEDIMENTOS CIRÚRGICOS",
        3,
        4,
        5,
    ),
    (
        "EPA15",
        "ABORDANDO CIRURGICAMENTE O PACIENTE COM OBESIDADE MÓRBIDA",
        1,
        2,
        3,
    ),
    (
        "EPA16",
        "REALIZANDO A GESTÃO DA EXCELÊNCIA DO CUIDADO EM CIRURGIA GERAL",
        2,
        3,
        4,
    ),
]

def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        especialidade = db.scalar(select(Especialidade))
        if especialidade is None:
            especialidade = Especialidade(nome="Cirurgia Geral")
            db.add(especialidade)
            db.flush()

        programa = db.scalar(select(Programa))
        if programa is None:
            programa = Programa(
                nome="Residência em Cirurgia Geral",
                especialidade_id=especialidade.id,
                instituicao="Hospital Universitário",
                duracao_anos=5,
            )
            db.add(programa)
            db.flush()

        if db.scalar(select(Servico).where(Servico.programa_id == programa.id)) is None:
            db.add(Servico(nome="Enfermaria", programa_id=programa.id))
            db.add(Servico(nome="Ambulatório", programa_id=programa.id))
            db.add(Servico(nome="Centro Cirúrgico", programa_id=programa.id))
            db.flush()
                   
            
        for codigo, titulo, nivel_r1, nivel_r2, nivel_r3 in EPAS:
            existente = db.scalar(
                select(EPA).where(
                    EPA.codigo == codigo,
                    EPA.programa_id == programa.id,
                )
            )

            if existente:
                print(f"  já existe: {codigo}")
                continue

            db.add(
                EPA(
                    codigo=codigo,
                    titulo=titulo,
                    programa_id=programa.id,
                    nivel_r1=nivel_r1,
                    nivel_r2=nivel_r2,
                    nivel_r3=nivel_r3,
                )
            )

        db.flush()

        for nome, email, papel in CONTAS:
            if db.scalar(select(Usuario).where(Usuario.email == email)):
                print(f"  já existe: {email}")
                continue
            criar_usuario(
                db,
                nome=nome,
                email=email,
                senha=SENHA_PADRAO,
                papel=papel,
                programa_id=programa.id,
            )
            print(f"  criado:    {email}  ({papel.value})")

        db.commit()
        print(f"\nSenha de todos: {SENHA_PADRAO}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
