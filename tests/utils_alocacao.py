"""Helper de testes: aloca usuários num mesmo serviço.

Desde o Sprint 4 a confirmação de avaliação exige que avaliador e
residente estejam alocados no mesmo serviço na data da atividade.
"""

from datetime import date, timedelta

from app.db.models import Alocacao, Servico


def alocar_no_mesmo_servico(db, programa, *usuarios, nome="Enfermaria", dias=400):
    servico = Servico(nome=nome, programa_id=programa.id)
    db.add(servico)
    db.flush()
    hoje = date.today()
    for usuario in usuarios:
        db.add(
            Alocacao(
                usuario_id=usuario.id,
                servico_id=servico.id,
                data_inicio=hoje - timedelta(days=dias),
                data_fim=hoje + timedelta(days=dias),
            )
        )
    db.flush()
    return servico
