import hashlib
import json


def gerar_hash_registro(dados: dict) -> str:
    """
    Recebe os campos de um registro de avaliação já confirmado,
    serializa os dados sempre na mesma ordem (chaves em ordem
    alfabética) e calcula o hash SHA-256 sobre esse texto.

    Essa função deve ser chamada SOMENTE no momento da confirmação
    final da avaliação — nunca enquanto o registro ainda é rascunho.

    O resultado deve ser salvo num campo do banco que nunca mais
    será escrito de novo (write-once), servindo como prova de que
    o registro não foi alterado desde a criação.
    """
    texto_ordenado = json.dumps(dados, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(texto_ordenado.encode("utf-8")).hexdigest()