from __future__ import annotations

from sqlalchemy import select

from app.core.auth_service import criar_usuario
from app.db.models import EPA, Base, Especialidade, Papel, Programa, Servico, Usuario
from app.db.session import SessionLocal, engine

SENHA_PADRAO = "Residencia2026"

CONTAS = [
    ("Ana Souza", "ana@hospital.br", Papel.RESIDENTE),
    ("Dr. Bruno Lima", "bruno@hospital.br", Papel.PRECEPTOR),
    ("Dra. Clara Reis", "clara@hospital.br", Papel.AVALIADOR_INTERMEDIARIO),
    ("Carla Menezes", "carla@hospital.br", Papel.ADMINISTRADOR),
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

        # 16 EPAs de Cirurgia Geral — fonte: Cadernos da Residência Médica,
        # Vol. 1 (Santa Casa de BH, 2022), Quadro 1, revisão 2021.
        epas_cirurgia_geral = [
            (1, "Admitindo o paciente cirúrgico", 2, 3, 5),
            (2, "Cuidando do paciente em pré-operatório", 2, 3, 5),
            (3, "Cuidando do paciente em pós-operatório", 2, 3, 5),
            (4, "Cuidando do paciente cirúrgico crítico", 2, 3, 3),
            (5, "Tratando cirurgicamente o paciente com defeito na parede abdominal", 2, 3, 3),
            (6, "Acessando a cavidade abdominal do paciente cirúrgico", 2, 3, 3),
            (7, "Tratando do paciente com apendicite aguda", 2, 3, 3),
            (8, "Abordando cirurgicamente o paciente para via nutricional alternativa", 2, 3, 3),
            (9, "Tratando pacientes com colecistopatia", 1, 2, 3),
            (10, "Abordando o paciente em urgência cirúrgica", 1, 2, 3),
            (11, "Abordando cirurgicamente o paciente com câncer do aparelho digestivo", 1, 2, 3),
            (12, "Abordando o paciente para cateterizações e sondagens", 3, 4, 5),
            (13, "Abordando o paciente para acesso venoso central/dissecção venosa", 3, 4, 5),
            (14, "Abordando o paciente para pequenos procedimentos cirúrgicos", 3, 4, 5),
            (15, "Abordando cirurgicamente o paciente com obesidade mórbida", 1, 2, 3),
            (16, "Realizando a gestão da excelência do cuidado em cirurgia geral", 2, 3, 4),
        ]
        if db.scalar(select(EPA).where(EPA.especialidade_id == especialidade.id)) is None:
            for numero, nome, r1, r2, r3 in epas_cirurgia_geral:
                db.add(EPA(
                    especialidade_id=especialidade.id,
                    numero=numero,
                    nome=nome,
                    nivel_esperado_r1=r1,
                    nivel_esperado_r2=r2,
                    nivel_esperado_r3=r3,
                ))
            db.flush()

        # 8 EPAs de Cirurgia de Cabeça e Pescoço (CCP) — PLACEHOLDER.
        # Substituir por dados reais assim que o documento de referência
        # da especialidade CCP estiver disponível.
        especialidade_ccp = db.scalar(select(Especialidade).where(Especialidade.nome == "Cirurgia de Cabeça e Pescoço"))
        if especialidade_ccp is None:
            especialidade_ccp = Especialidade(nome="Cirurgia de Cabeça e Pescoço")
            db.add(especialidade_ccp)
            db.flush()

        if db.scalar(select(EPA).where(EPA.especialidade_id == especialidade_ccp.id)) is None:
            for numero in range(1, 9):
                db.add(EPA(
                    especialidade_id=especialidade_ccp.id,
                    numero=numero,
                    nome=f"[PLACEHOLDER] EPA {numero} de Cirurgia de Cabeça e Pescoço",
                    nivel_esperado_r1=2,
                    nivel_esperado_r2=3,
                    nivel_esperado_r3=4,
                ))
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