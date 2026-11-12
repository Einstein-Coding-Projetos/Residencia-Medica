"""Job diário de engajamento (D15/D20/D25 e fechamento do mês).

Rodar uma vez por dia, de madrugada:

    python -m app.jobs.verificar_engajamento            # hoje
    python -m app.jobs.verificar_engajamento 2026-09-25 # simula outro dia

No servidor: cron (`0 6 * * * cd /app && python -m app.jobs.verificar_engajamento`)
ou Agendador de Tarefas no Windows. É idempotente: rodar duas vezes no
mesmo dia não duplica alertas nem omissões.
"""

from __future__ import annotations

import json
import sys
from datetime import date

from app.core.engajamento_service import verificar_engajamento
from app.db.session import SessionLocal


def main(argv: list[str]) -> int:
    hoje = date.fromisoformat(argv[1]) if len(argv) > 1 else date.today()
    db = SessionLocal()
    try:
        resultado = verificar_engajamento(db, hoje)
        db.commit()
    finally:
        db.close()
    print(json.dumps(resultado.como_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
