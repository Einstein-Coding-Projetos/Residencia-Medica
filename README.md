# Sprint 1 — Autenticação e RBAC

As três coisas pedidas na tarefa, e onde cada uma mora:

| O que faz | Arquivo |
|---|---|
| Confere a senha sem nunca guardar texto puro | `app/core/security.py` → `verificar_senha` |
| Emite o "crachá digital" (token JWT) | `app/core/security.py` → `criar_access_token` |
| Lê o crachá a cada requisição protegida | `app/api/deps.py` → `usuario_atual` |
| Barra quem não tem o papel certo | `app/api/deps.py` → `exigir_papeis` |
| Tela de login (email + senha) | `frontend/Login.jsx` |

## Rodar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # gere a SECRET_KEY conforme o comentário
python seed.py                # cria 4 usuários, um de cada papel
uvicorn app.main:app --reload
```

Swagger em `http://localhost:8000/docs`. O botão **Authorize** aceita o
`access_token` devolvido pelo `/auth/login`.

```bash
pytest -q     # 18 testes
```

## Endpoints

| Método | Rota | Quem pode |
|---|---|---|
| POST | `/api/v1/auth/login` | qualquer um |
| GET | `/api/v1/auth/eu` | autenticado |
| POST | `/api/v1/programas` | **só administrador** |
| GET | `/api/v1/programas` | autenticado |

## Como proteger uma rota nova

```python
from app.api.deps import SomenteAdministrador, SomenteAvaliador, UsuarioAtual

def cadastrar_programa(admin: SomenteAdministrador): ...   # só admin
def aplicar_ficha(avaliador: SomenteAvaliador): ...        # preceptor e R4/R5
def ver_portfolio(usuario: UsuarioAtual): ...              # qualquer logado
```

Para uma combinação nova: `Annotated[Usuario, Depends(exigir_papeis(Papel.X, Papel.Y))]`.

## Decisões que valem revisar no PR

**Administrador não é super-usuário.** O cronograma fecha que administrador é
papel de gestão e não acumula função clínica. Por isso `exigir_papeis` não tem
atalho de admin: `exigir_papeis(Papel.PRECEPTOR)` bloqueia o administrador, de
propósito. Tem um teste (`test_administrador_nao_e_super_usuario`) que quebra se
alguém adicionar esse atalho depois.

**O papel dentro do token é só para o front desenhar a tela.** A autorização
reconfere o papel no banco a cada requisição. Se o admin rebaixar alguém, o
crachá antigo para de valer na hora, sem esperar as 8h de expiração.

**Erro de login é sempre a mesma mensagem.** "Email ou senha incorretos" para os
dois casos, e um bcrypt de mentira roda quando o email não existe, para igualar o
tempo de resposta. Sem isso dá para descobrir quem tem conta no sistema
cronometrando as respostas — o que é exatamente o tipo de vazamento que a
premissa de LGPD do projeto quer evitar.

**Login entra na trilha de auditoria**, aceito e negado, com hash SHA-256 do
registro. Encaixa no requisito de imutabilidade do Sprint 1. O encadeamento de
hashes (cada linha carregando o hash da anterior) fica para o Sprint 4.

**Senha limitada a 72 bytes.** O bcrypt ignora silenciosamente o que passa
disso — sem a validação, duas senhas longas diferentes logariam a mesma conta.

**Token fica em memória no front, não em `localStorage`.** Está comentado no
`Login.jsx`. O passo seguinte é refresh token em cookie `httpOnly`.

## O que ficou de fora (e por quê)

- **Alembic.** As tabelas são criadas na subida da app, o que serve para
  desenvolver mas não versiona schema. Vale abrir uma issue para o Sprint 2.
- **Logout de verdade.** JWT é stateless: o token vale até expirar. O campo
  `jti` já vai no payload para quando entrar uma denylist.
- **Rate limit no `/login`.** Hoje dá para tentar senha sem limite. Sugestão:
  bloqueio progressivo por email + IP.
- **SSO institucional.** O cronograma cita "login institucional/SSO". Esta
  entrega cobre o login por senha; a lógica está em `auth_service.py` justamente
  para o SSO entrar depois sem reescrever as rotas.
- **Verificação de contexto** (avaliador e residente alocados no mesmo serviço)
  é Sprint 4 e depende do modelo de alocação.

## Perguntas para o time

1. O front é React? A tela está em `.jsx`, mas o CSS é puro e migra fácil.
2. 8 horas de sessão está bom, ou a cliente quer algo mais curto?
3. Política de senha: por ora só mínimo de 8 caracteres. Define regra ou parte
   para SSO direto?
