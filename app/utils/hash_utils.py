import hashlib
import json


def gerar_hash_registro(dados: dict) -> str:
    canonico = json.dumps(dados, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()