# Sprint 2 — Frente A (OSATS e Mini-CEX) + camada compartilhada

Este documento lista **tudo** que foi alterado, incluindo mudanças em arquivos
que pertencem às frentes B e C. Nada aqui é definitivo — o que estiver errado
é só ajustar.

---

## 1. Merge das três branches

As branches `mudancas-models.py`, `mudancas-main.py` e `app/db/models.py` eram
idênticas entre si, exceto por um arquivo cada:

| Branch | Única diferença |
|---|---|
| `app/db/models.py` | base, sem `Avaliacao` e sem router registrado |
| `mudancas-models.py` | base + classe `Avaliacao` em `app/db/models.py` |
| `mudancas-main.py` | base + `include_router(avaliacoes.router)` em `app/main.py` |

Esta entrega já é o merge das três. Não houve conflito real.

---

## 2. Dois bugs que já existiam nas branches (corrigidos)

### 2.1 `LogAuditoria.calcular_hash` estava dentro da classe errada

A classe `Avaliacao` foi colada em `models.py` **entre** os campos de
`LogAuditoria` e o método `calcular_hash`. O método acabou pertencendo a
`Avaliacao`, e `LogAuditoria` ficou sem ele.

Efeito: **toda chamada de `registrar_auditoria` quebrava com
`AttributeError`.** Ou seja, criar ou confirmar qualquer avaliação retornava
500. O teste `tests/test_immutability.py::test_confirmar_gera_hash_e_trava`
já falhava na branch por causa disso.

Corrigido: método devolvido para `LogAuditoria`, classes separadas.

### 2.2 `avaliacao_id` tipado como `str` contra uma PK `Uuid`

Nas rotas `GET /avaliacoes/{id}` e `POST /avaliacoes/{id}/confirmar` o
parâmetro era `str` e ia direto para `db.get(Avaliacao, avaliacao_id)`.
O SQLAlchemy 2 estourava `AttributeError: 'str' object has no attribute 'hex'`.

Efeito: as duas rotas estavam quebradas.

Corrigido: parâmetro tipado como `uuid.UUID`.

---

## 3. Novo: `app/core/instrumentos.py` — contrato compartilhado

Antes, escala e instrumentos estavam escritos na mão em dois lugares
(`schemas/avaliacoes.py` e `routes/avaliacoes.py`), com dois problemas:

- `Instrumento = Literal["zwisch", "setq_smart"]` — sem `osats` e sem `mini_cex`
- `nota: int = Field(ge=1, le=5)` — escala fixa 1–5, que **barra o Mini-CEX
  (1–9) com erro 422** e aceita silenciosamente nota 5 no NOTSS (que vai até 4)

Agora existe um registro único. Cada instrumento declara escala, domínios,
forma de agregação e faixas de corte. Rota, validação e cálculo leem dele.

**Para adicionar ou ajustar um instrumento, edite só o dicionário
`INSTRUMENTOS`.** Nenhum arquivo de rota precisa ser tocado.

| Instrumento | Escala | Domínios | Agregação | Estado |
|---|---|---|---|---|
| `osats` | 1–5 | 7 | soma (7–35) | completo |
| `mini_cex` | 1–9 | 5 | soma (5–45) | completo |
| `notss` | 1–4 | 4 | soma | escala e domínios prontos; descritores e faixas pendentes (**frente B**) |
| `zwisch` | 1–4 | livre | não se aplica | provisório (**frente B**, ver §5) |
| `setq_smart` | 1–5 | 5 | média | escala e domínios prontos; anonimização pendente (**frente C**) |

---

## 4. Cálculo de nota: era média, virou soma com faixa

O código anterior devolvia a **média** dos itens. O documento técnico
(Parte VI) especifica **soma com faixas de corte**:

**OSATS — total 7 a 35**

| Faixa | Rótulo | Leitura |
|---|---|---|
| 7–17 | `supervisao_direta` | Supervisão direta obrigatória |
| 18–27 | `assistencia_ocasional` | Assistência ocasional |
| 28–35 | `autonomia_supervisionada` | Autonomia supervisionada |

**Mini-CEX — total 5 a 45**, corte de referência do documento: ≥ 35 satisfatório.

| Faixa | Rótulo |
|---|---|
| 5–19 | `insatisfatorio` |
| 20–34 | `em_desenvolvimento` |
| 35–45 | `satisfatorio` |

A faixa é persistida em `Avaliacao.faixa_rotulo` e entra no hash de integridade.

> As faixas do Mini-CEX abaixo de 35 (o corte entre `insatisfatorio` e
> `em_desenvolvimento`) **não estão no documento** — foram propostas para dar
> uma leitura útil. Precisa de validação com a cliente.

---

## 5. Zwisch não cabe no modelo de soma de domínios

A Zwisch **não produz score somado**. Ela registra um *nível de autonomia por
etapa cirúrgica* (Z1 show and tell → Z4 supervision only). O modelo atual
(`instrumento` + lista de domínios + nota somada) não representa isso.

Ela está registrada como `agregacao="nao_aplicavel"` e `dominios_fixos=False`,
aceitando itens livres, **só para não quebrar o que já existia**. A modelagem
correta (campo de etapa cirúrgica, sem soma) é decisão da frente B.

## 5b. SETQ Smart inverte o sentido da avaliação

No SETQ o **residente avalia o preceptor**. A rota atual assume
avaliador → residente e exige papel de avaliador (`SomenteAvaliador`), então
não atende esse fluxo. Hoje `POST /avaliacoes` **recusa `setq_smart` com 400**
e uma mensagem explicando. Precisa de rota própria com anonimização e
agregação mínima de 3 residentes (regra COI-03) — frente C.

---

## 6. Confirmação de envio agora exige a declaração (INT-04)

Antes, `POST /avaliacoes/{id}/confirmar` marcava `confirmado=True` e gerava o
hash, mas **não registrava a declaração de observação direta** que a regra
INT-04 exige.

Agora o endpoint recebe um corpo:

```json
{ "confirmo_observacao_direta": true }
```

- Se vier `false` → **422**, com a frase exigida na mensagem de erro
- Se vier `true` → grava em `Avaliacao.declaracao_observacao` o texto
  *"Confirmo que observei este residente pessoalmente nesta atividade na data
  informada."*, inclui essa frase no hash SHA-256 e registra no log de auditoria

Isso é escopo da frente C. Foi implementado aqui porque exigia mudança de
modelo e de rota que a frente A também precisa usar — **ajuste à vontade.**

---

## 7. Mudanças no modelo `Avaliacao`

Duas colunas novas:

| Coluna | Tipo | Para quê |
|---|---|---|
| `faixa_rotulo` | `String(50)`, nullable | Faixa de corte calculada |
| `declaracao_observacao` | `Text`, nullable | Texto da declaração INT-04 |

> **Não existe Alembic no projeto** (apesar do README prometer). O schema nasce
> de `Base.metadata.create_all()` no startup. Como há colunas novas, **apague o
> `dev.db` antes de rodar**, senão dá erro de coluna inexistente.
>
> ```bash
> rm -f dev.db
> ```

---

## 8. Formato dos itens mudou

Antes: `{"item": "texto livre", "nota": 3}`
Agora: `{"dominio": "codigo_do_dominio", "nota": 3}`

O código do domínio é validado contra o instrumento. Para instrumentos com
`dominios_fixos=True`, a ficha **precisa vir completa** — OSATS com os 7
domínios, Mini-CEX com os 5. Isso é o que garante que a soma 7–35 signifique
alguma coisa.

Erros retornados: domínio faltando, domínio repetido, domínio de outro
instrumento, nota fora da escala.

---

## 9. Nova rota: `GET /api/v1/instrumentos`

Devolve os metadados das fichas (domínios, escala, âncoras, faixas). Serve para
montar o formulário a partir da mesma fonte que o backend usa para validar, em
vez de reescrever a ficha no frontend depois.

- `GET /api/v1/instrumentos` — lista os cinco
- `GET /api/v1/instrumentos/{codigo}` — detalha um

---

## 10. Regra de visibilidade acrescentada

`GET /avaliacoes/{id}`: o residente **não vê** a avaliação enquanto ela não for
confirmada pelo avaliador (rascunho não é feedback). Antes ele via.

---

## 11. Testes

`42 passed`.

- `tests/test_instrumentos.py` — escala, domínios, soma e faixas dos cinco
  instrumentos. Inclui regressão para "usa soma e não média" e "Mini-CEX aceita
  nota 9".
- `tests/test_avaliacoes_api.py` — ponta a ponta: criação, recusa de ficha
  incompleta, declaração obrigatória, imutabilidade (423 na segunda
  confirmação), avaliador errado (403), visibilidade do residente, metadados.
- Testes anteriores preservados e passando.

```bash
rm -f dev.db
pip install -r requirements.txt
python -m pytest tests/ -q
uvicorn app.main:app --reload   # docs em /docs
```

---

## 12. Pendências e decisões em aberto

| # | Item | Quem |
|---|---|---|
| 1 | Faixas de corte do Mini-CEX abaixo de 35 não vêm do documento — validar com a cliente | time / cliente |
| 2 | NOTSS: descritores comportamentais e faixas de corte | frente B |
| 3 | Zwisch: modelagem por etapa cirúrgica (não é soma) | frente B |
| 4 | SETQ: rota própria residente→preceptor, anonimização, mínimo de 3 residentes | frente C |
| 5 | `itens` é `Text` com JSON serializado à mão, não JSONB — perde consulta por dentro do campo; o Sprint 0 previa JSONB | time |
| 6 | Não há Alembic; schema por `create_all` e default SQLite. Migrar antes da entrega | time |
| 7 | Verificação de contexto (avaliador e residente no mesmo serviço na data) é Sprint 4 — não está aqui | — |
| 8 | Prazo individual de residência (nota só dentro do período) ainda não implementado | time |
