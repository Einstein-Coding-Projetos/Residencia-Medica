import json
import os

AUDIT_LOG = "audit_log.json"


if not os.path.exists(AUDIT_LOG):
    with open(AUDIT_LOG, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=4)


def ler_audit_log():

    try:

        with open(AUDIT_LOG, "r", encoding="utf-8") as f:

            conteudo = f.read().strip()

            if conteudo == "":
                return []

            return json.loads(conteudo)

    except (json.JSONDecodeError, FileNotFoundError):

        return []


def salvar_audit_log(dados):

    with open(AUDIT_LOG, "w", encoding="utf-8") as f:

        json.dump(
            dados,
            f,
            indent=4,
            ensure_ascii=False
        )