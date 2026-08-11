import json

usuarios = [

    {
        "id": 1,
        "nome": "Administrador",
        "email": "admin@teste.com",
        "senha": "123456",
        "papel": "ADMIN"
    },

    {
        "id": 2,
        "nome": "Dr. João Silva",
        "email": "joao@teste.com",
        "senha": "123456",
        "papel": "PRECEPTOR"
    },

    {
        "id": 3,
        "nome": "Dra. Maria Souza",
        "email": "maria@teste.com",
        "senha": "123456",
        "papel": "PRECEPTOR"
    },

    {
        "id": 4,
        "nome": "Ana Costa",
        "email": "ana@teste.com",
        "senha": "123456",
        "papel": "RESIDENTE",
        "ano": "R1"
    },

    {
        "id": 5,
        "nome": "Pedro Lima",
        "email": "pedro@teste.com",
        "senha": "123456",
        "papel": "RESIDENTE",
        "ano": "R2"
    },

    {
        "id": 6,
        "nome": "Lucas Ferreira",
        "email": "lucas@teste.com",
        "senha": "123456",
        "papel": "RESIDENTE",
        "ano": "R3"
    },

    {
        "id": 7,
        "nome": "Mariana Alves",
        "email": "mariana@teste.com",
        "senha": "123456",
        "papel": "RESIDENTE",
        "ano": "R4"
    },

    {
        "id": 8,
        "nome": "Felipe Rocha",
        "email": "felipe@teste.com",
        "senha": "123456",
        "papel": "RESIDENTE",
        "ano": "R5"
    }

]

with open("usuarios.json", "w", encoding="utf-8") as f:
    json.dump(usuarios, f, indent=4, ensure_ascii=False)

print("Usuários de teste criados com sucesso!")