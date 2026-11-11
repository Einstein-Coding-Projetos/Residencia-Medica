
def registrar_alertas_heuristicas(db: Session, avaliacao_id: uuid.UUID, avaliador_id: uuid.UUID, tempo_segundos: int):
    # Heurística 1: Preenchimento mecanizado/rápido demais (< 15s para formulário longo)
    if tempo_segundos < 15:
        db.add(AlertaAnomalia(
            avaliacao_id=avaliacao_id,
            avaliador_id=avaliador_id,
            tipo_alerta="velocidade_suspeita",
            detalhes={"tempo_segundos": tempo_segundos, "limiar": 15}
        ))
        
    # Heurística 2: Volume atípico / Viés de Leniência extrema pode ser checado
    # com queries de agregação (AVG(nivel_atingido)) no histórico do preceptor.
    
    db.commit()