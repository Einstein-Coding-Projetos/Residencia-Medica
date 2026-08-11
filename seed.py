"""Cria usuários fictícios para testar login e RBAC.

    python seed.py

Os usuários reais são cadastrados pela equipe médica depois da entrega
(conforme o Sprint 1 do cronograma). Isto aqui é só para desenvolvimento.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.auth_service import criar_usuario
from app.db.models import Base, Papel, Programa, Usuario
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
        programa = db.scalar(select(Programa))
        if programa is None:
            programa = Programa(
                nome="Residência em Cirurgia Geral",
                especialidade="Cirurgia Geral",
                instituicao="Hospital Universitário",
                duracao_anos=5,
            )
            db.add(programa)
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
