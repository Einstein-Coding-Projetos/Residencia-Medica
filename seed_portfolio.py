"""Dados FICTÍCIOS para demonstrar o portfólio (tarefa 3).

Cria, para a residente de teste Ana Souza (do seed.py), um histórico de
avaliações confirmadas ao longo de ~6 meses e procedimentos validados,
pendentes e recusados — assim a tela e o PDF têm o que mostrar.

    python seed.py            # contas e programa
    python seed_portfolio.py  # histórico da Ana

Pode rodar de novo: se a Ana já tiver avaliações, não duplica nada.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

import seed
from app.core.instrumentos import calcular_resultado, obter_instrumento, resultado_zwisch
from app.db.models import Avaliacao, Procedimento, Usuario
from app.db.session import SessionLocal
from app.utils.hash_utils import gerar_hash_registro

HOJE = datetime.now(timezone.utc).replace(hour=13, minute=0, second=0, microsecond=0)


class _Item:
    def __init__(self, dominio: str, nota: int):
        self.dominio, self.nota = dominio, nota


def _distribuir(codigo: str, total: int) -> list[_Item]:
    """Espalha um total entre os domínios do instrumento (para a demo)."""
    inst = obter_instrumento(codigo)
    n = len(inst.dominios)
    base, resto = divmod(total, n)
    notas = [base + (1 if i < resto else 0) for i in range(n)]
    return [_Item(d.codigo, max(inst.escala_min, min(inst.escala_max, v)))
            for d, v in zip(inst.dominios, notas)]


def _confirmar(db, a: Avaliacao, quando: datetime) -> None:
    inst = obter_instrumento(a.instrumento)
    a.declaracao_observacao = inst.texto_confirmacao
    a.hash_integridade = gerar_hash_registro({
        "id": str(a.id), "residente_id": str(a.residente_id), "avaliador_id": str(a.avaliador_id),
        "instrumento": a.instrumento, "itens": a.itens, "observacoes": a.observacoes,
        "nota": a.nota, "faixa_rotulo": a.faixa_rotulo,
        "declaracao_observacao": a.declaracao_observacao,
    })
    a.confirmado = True
    a.criado_em = quando - timedelta(minutes=20)
    a.confirmado_em = quando


def _avaliacao(db, residente, avaliador, codigo, total, dias_atras, obs=""):
    inst = obter_instrumento(codigo)
    itens = _distribuir(codigo, total)
    r = calcular_resultado(inst, itens)
    a = Avaliacao(
        residente_id=residente.id, avaliador_id=avaliador.id, instrumento=codigo,
        itens=json.dumps([{"dominio": i.dominio, "nota": i.nota} for i in itens]),
        observacoes=obs, nota=r.valor, faixa_rotulo=r.faixa_rotulo,
    )
    db.add(a)
    db.flush()
    _confirmar(db, a, HOJE - timedelta(days=dias_atras))


def _zwisch(db, residente, avaliador, etapa, nivel, dias_atras, obs=""):
    inst = obter_instrumento("zwisch")
    r = resultado_zwisch(inst, nivel)
    a = Avaliacao(
        residente_id=residente.id, avaliador_id=avaliador.id, instrumento="zwisch",
        itens="[]", observacoes=obs, etapa_cirurgica=etapa, nota=r.valor, faixa_rotulo=r.faixa_rotulo,
    )
    db.add(a)
    db.flush()
    _confirmar(db, a, HOJE - timedelta(days=dias_atras))


def main() -> None:
    seed.main()
    db = SessionLocal()
    try:
        ana = db.scalar(select(Usuario).where(Usuario.email == "ana@hospital.br"))
        bruno = db.scalar(select(Usuario).where(Usuario.email == "bruno@hospital.br"))
        clara = db.scalar(select(Usuario).where(Usuario.email == "clara@hospital.br"))

        if db.scalar(select(Avaliacao).where(Avaliacao.residente_id == ana.id)):
            print("A Ana já tem histórico — nada a fazer.")
            return

        osats = [
            (15, 170, bruno, "Manuseio de tecidos ainda brusco na dissecção. Rever tração."),
            (18, 140, clara, "Melhor fluxo operatório; ainda hesita na troca de instrumentos."),
            (21, 110, bruno, ""),
            (24, 75, bruno, "Boa hemostasia. Orientar melhor o auxiliar."),
            (27, 40, clara, "Antecipou etapas com segurança. Evolução clara."),
            (30, 10, bruno, "Conduziu a colecistectomia com autonomia supervisionada."),
        ]
        for total, dias, quem, obs in osats:
            _avaliacao(db, ana, quem, "osats", total, dias, obs)

        for total, dias, obs in [
            (24, 160, "Anamnese incompleta para fatores de risco."),
            (29, 120, ""),
            (33, 85, "Raciocínio clínico bem estruturado; documentar melhor."),
            (37, 50, "Comunicou o diagnóstico com clareza à família."),
            (39, 18, ""),
        ]:
            _avaliacao(db, ana, bruno, "mini_cex", total, dias, obs)

        for total, dias in [(9, 130), (11, 70), (13, 25)]:
            _avaliacao(db, ana, bruno, "notss", total, dias)

        for etapa, nivel, dias in [
            ("Acesso e posicionamento de trocartes", 1, 150),
            ("Acesso e posicionamento de trocartes", 2, 90),
            ("Acesso e posicionamento de trocartes", 3, 30),
            ("Dissecção do triângulo de Calot", 1, 120),
            ("Dissecção do triângulo de Calot", 2, 45),
            ("Fechamento da parede abdominal", 3, 100),
            ("Fechamento da parede abdominal", 4, 20),
        ]:
            _zwisch(db, ana, bruno, etapa, nivel, dias)

        procedimentos = [
            ("Colecistectomia videolaparoscópica", "primeiro_auxiliar", 160, "validado"),
            ("Colecistectomia videolaparoscópica", "primeiro_auxiliar", 130, "validado"),
            ("Colecistectomia videolaparoscópica", "cirurgiao_principal", 60, "validado"),
            ("Colecistectomia videolaparoscópica", "cirurgiao_principal", 12, "validado"),
            ("Herniorrafia inguinal", "cirurgiao_principal", 140, "validado"),
            ("Herniorrafia inguinal", "cirurgiao_principal", 95, "validado"),
            ("Herniorrafia inguinal", "primeiro_auxiliar", 44, "validado"),
            ("Apendicectomia", "cirurgiao_principal", 115, "validado"),
            ("Apendicectomia", "cirurgiao_principal", 33, "validado"),
            ("Laparotomia exploradora", "segundo_auxiliar", 88, "validado"),
            ("Tireoidectomia total", "segundo_auxiliar", 55, "validado"),
            ("Drenagem de abscesso", "cirurgiao_principal", 21, "validado"),
            ("Colecistectomia videolaparoscópica", "cirurgiao_principal", 3, "pendente"),
            ("Herniorrafia umbilical", "cirurgiao_principal", 2, "pendente"),
            ("Apendicectomia", "cirurgiao_principal", 70, "recusado"),
        ]
        for nome, participacao, dias, status in procedimentos:
            p = Procedimento(
                residente_id=ana.id, nome=nome, participacao=participacao,
                data_realizacao=date.today() - timedelta(days=dias), status=status,
            )
            if status != "pendente":
                p.validador_id = bruno.id
                p.validado_em = HOJE - timedelta(days=max(dias - 2, 0))
                p.confirmado = True
                p.motivo_recusa = "Registro duplicado." if status == "recusado" else None
                p.hash_integridade = gerar_hash_registro({"nome": nome, "dias": dias, "status": status})
            db.add(p)

        db.commit()
        print("Histórico fictício criado para ana@hospital.br.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
