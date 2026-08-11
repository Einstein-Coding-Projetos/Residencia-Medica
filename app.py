from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json
import os

app = Flask(__name__, static_folder="static")
CORS(app)

# ==============================
# ARQUIVOS JSON
# ==============================

PROGRAMAS = "programas.json"
ESPECIALIDADES = "especialidades.json"
SERVICOS = "servicos.json"


# ==============================
# CRIA OS JSON CASO NÃO EXISTAM
# ==============================

for arquivo in [PROGRAMAS, ESPECIALIDADES, SERVICOS]:

    if not os.path.exists(arquivo):

        with open(arquivo, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=4)


# ==============================
# FUNÇÕES PARA LER E SALVAR JSON
# ==============================

def ler_json(arquivo):

    try:

        with open(arquivo, "r", encoding="utf-8") as f:

            conteudo = f.read().strip()

            if conteudo == "":
                return []

            return json.loads(conteudo)

    except (json.JSONDecodeError, FileNotFoundError):

        return []


def salvar_json(arquivo, dados):

    with open(arquivo, "w", encoding="utf-8") as f:

        json.dump(
            dados,
            f,
            indent=4,
            ensure_ascii=False
        )


# ==============================
# PÁGINA PRINCIPAL
# ==============================

@app.route("/")
def home():

    return send_from_directory(
        "static",
        "index.html"
    )


# ============================================================
# PROGRAMAS
# ============================================================

# LISTAR PROGRAMAS

@app.route("/programas", methods=["GET"])
def listar_programas():

    return jsonify(
        ler_json(PROGRAMAS)
    )


# CRIAR PROGRAMA

@app.route("/programas", methods=["POST"])
def criar_programa():

    dados = request.json

    nome = str(
        dados.get("nome", "")
    ).strip()

    descricao = str(
        dados.get("descricao", "")
    ).strip()

    if not nome:

        return jsonify({
            "erro": "Nome obrigatório"
        }), 400

    lista = ler_json(PROGRAMAS)

    # Evita nomes repetidos

    for programa in lista:

        if programa["nome"].lower() == nome.lower():

            return jsonify({
                "erro": "Programa já cadastrado"
            }), 409

    # Cria ID novo

    if lista:

        novo_id = max(
            item["id"] for item in lista
        ) + 1

    else:

        novo_id = 1

    novo = {

        "id": novo_id,
        "nome": nome,
        "descricao": descricao

    }

    lista.append(novo)

    salvar_json(
        PROGRAMAS,
        lista
    )

    return jsonify(novo), 201


# EDITAR PROGRAMA

@app.route("/programas/<int:id>", methods=["PUT"])
def editar_programa(id):

    dados = request.json

    nome = str(
        dados.get("nome", "")
    ).strip()

    descricao = str(
        dados.get("descricao", "")
    ).strip()

    if not nome:

        return jsonify({
            "erro": "Nome obrigatório"
        }), 400

    lista = ler_json(PROGRAMAS)

    for programa in lista:

        if programa["id"] == id:

            programa["nome"] = nome
            programa["descricao"] = descricao

            salvar_json(
                PROGRAMAS,
                lista
            )

            return jsonify(programa), 200

    return jsonify({
        "erro": "Programa não encontrado"
    }), 404


# APAGAR PROGRAMA

@app.route("/programas/<int:id>", methods=["DELETE"])
def excluir_programa(id):

    lista = ler_json(PROGRAMAS)

    nova_lista = [
        programa
        for programa in lista
        if programa["id"] != id
    ]

    if len(nova_lista) == len(lista):

        return jsonify({
            "erro": "Programa não encontrado"
        }), 404

    salvar_json(
        PROGRAMAS,
        nova_lista
    )

    return jsonify({
        "mensagem": "Programa removido"
    }), 200


# ============================================================
# ESPECIALIDADES
# ============================================================

# LISTAR

@app.route("/especialidades", methods=["GET"])
def listar_especialidades():

    return jsonify(
        ler_json(ESPECIALIDADES)
    )


# CRIAR

@app.route("/especialidades", methods=["POST"])
def criar_especialidade():

    dados = request.json

    nome = str(
        dados.get("nome", "")
    ).strip()

    descricao = str(
        dados.get("descricao", "")
    ).strip()

    if not nome:

        return jsonify({
            "erro": "Nome obrigatório"
        }), 400

    lista = ler_json(ESPECIALIDADES)

    for especialidade in lista:

        if especialidade["nome"].lower() == nome.lower():

            return jsonify({
                "erro": "Especialidade já cadastrada"
            }), 409

    if lista:

        novo_id = max(
            item["id"] for item in lista
        ) + 1

    else:

        novo_id = 1

    novo = {

        "id": novo_id,
        "nome": nome,
        "descricao": descricao

    }

    lista.append(novo)

    salvar_json(
        ESPECIALIDADES,
        lista
    )

    return jsonify(novo), 201


# EDITAR

@app.route("/especialidades/<int:id>", methods=["PUT"])
def editar_especialidade(id):

    dados = request.json

    nome = str(
        dados.get("nome", "")
    ).strip()

    descricao = str(
        dados.get("descricao", "")
    ).strip()

    if not nome:

        return jsonify({
            "erro": "Nome obrigatório"
        }), 400

    lista = ler_json(ESPECIALIDADES)

    for especialidade in lista:

        if especialidade["id"] == id:

            especialidade["nome"] = nome
            especialidade["descricao"] = descricao

            salvar_json(
                ESPECIALIDADES,
                lista
            )

            return jsonify(especialidade), 200

    return jsonify({
        "erro": "Especialidade não encontrada"
    }), 404


# APAGAR

@app.route("/especialidades/<int:id>", methods=["DELETE"])
def excluir_especialidade(id):

    lista = ler_json(ESPECIALIDADES)

    nova_lista = [
        especialidade
        for especialidade in lista
        if especialidade["id"] != id
    ]

    if len(nova_lista) == len(lista):

        return jsonify({
            "erro": "Especialidade não encontrada"
        }), 404

    salvar_json(
        ESPECIALIDADES,
        nova_lista
    )

    return jsonify({
        "mensagem": "Especialidade removida"
    }), 200


# ============================================================
# SERVIÇOS
# ============================================================

# LISTAR

@app.route("/servicos", methods=["GET"])
def listar_servicos():

    return jsonify(
        ler_json(SERVICOS)
    )


# CRIAR

@app.route("/servicos", methods=["POST"])
def criar_servico():

    dados = request.json

    nome = str(
        dados.get("nome", "")
    ).strip()

    descricao = str(
        dados.get("descricao", "")
    ).strip()

    if not nome:

        return jsonify({
            "erro": "Nome obrigatório"
        }), 400

    lista = ler_json(SERVICOS)

    for servico in lista:

        if servico["nome"].lower() == nome.lower():

            return jsonify({
                "erro": "Serviço já cadastrado"
            }), 409

    if lista:

        novo_id = max(
            item["id"] for item in lista
        ) + 1

    else:

        novo_id = 1

    novo = {

        "id": novo_id,
        "nome": nome,
        "descricao": descricao

    }

    lista.append(novo)

    salvar_json(
        SERVICOS,
        lista
    )

    return jsonify(novo), 201


# EDITAR

@app.route("/servicos/<int:id>", methods=["PUT"])
def editar_servico(id):

    dados = request.json

    nome = str(
        dados.get("nome", "")
    ).strip()

    descricao = str(
        dados.get("descricao", "")
    ).strip()

    if not nome:

        return jsonify({
            "erro": "Nome obrigatório"
        }), 400

    lista = ler_json(SERVICOS)

    for servico in lista:

        if servico["id"] == id:

            servico["nome"] = nome
            servico["descricao"] = descricao

            salvar_json(
                SERVICOS,
                lista
            )

            return jsonify(servico), 200

    return jsonify({
        "erro": "Serviço não encontrado"
    }), 404


# APAGAR

@app.route("/servicos/<int:id>", methods=["DELETE"])
def excluir_servico(id):

    lista = ler_json(SERVICOS)

    nova_lista = [
        servico
        for servico in lista
        if servico["id"] != id
    ]

    if len(nova_lista) == len(lista):

        return jsonify({
            "erro": "Serviço não encontrado"
        }), 404

    salvar_json(
        SERVICOS,
        nova_lista
    )

    return jsonify({
        "mensagem": "Serviço removido"
    }), 200


# ==============================
# INICIAR SERVIDOR
# ==============================

if __name__ == "__main__":

    print("Servidor iniciado!")

    app.run(
        debug=True,
        port=5001
    )