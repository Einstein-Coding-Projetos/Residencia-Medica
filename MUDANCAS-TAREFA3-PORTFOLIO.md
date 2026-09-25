# Tarefa 3: Portfólio do residente + exportação em PDF

Aqui está tudo o que mudou nesta entrega. Onde havia decisão em aberto, fiz
uma escolha razoável e escrevi o motivo. **Se algo estiver errado, é só ajustar.**

Testes: `130 passed` (77 que já existiam + 53 novos).

---

## 1. O que o portfólio mostra

| Bloco | De onde vem | Regra |
|---|---|---|
| Identificação | `Usuario` + `Programa` + `Especialidade` | — |
| Números-resumo | calculado | avaliações, instrumentos, procedimentos validados, EPAs no nível |
| **Mapa das EPAs** | catálogo do documento das EPAs + tarefa 1, por um adaptador (§3) | nível atual × nível esperado para o ano do residente, com a trajetória R1→R2→R3 |
| **Desempenho por instrumento** | `Avaliacao` (OSATS, Mini-CEX, NOTSS) | evolução no tempo, média por domínio e distribuição por faixa |
| **Autonomia por etapa (Zwisch)** | `Avaliacao` com `instrumento="zwisch"` | nível mais recente por etapa cirúrgica, com o histórico |
| **Procedimentos realizados** | nova tabela `Procedimento` (§2) | **só os validados** entram na conta |
| **Histórico e feedback** | `Avaliacao` | data, avaliador, nota, faixa, observações e hash |

Regras que valem para todos os blocos:

- **Só entram avaliações confirmadas.** Rascunho não é feedback. É a mesma regra do `GET /avaliacoes/{id}`.
- **O SETQ Smart nunca entra.** No SETQ, o residente avalia o preceptor.
  Mostrar essas respostas num portfólio que o preceptor pode abrir quebraria
  o anonimato da regra COI-03.
- **A tela e o PDF leem o mesmo objeto** (`app/core/portfolio.py`), então nunca
  mostram números diferentes.

---

## 2. Novo: procedimentos realizados

Ninguém estava fazendo esta parte, e o portfólio precisa dela. O documento do
projeto diz que *"trabalhos adicionados pelo residente precisam de validação de
um profissional antes de contar na estatística"*.

```
residente registra        ->  status "pendente"
preceptor/R4-R5 decide    ->  "validado" ou "recusado" (o motivo é obrigatório na recusa)
```

- A decisão é **final**: gera o hash SHA-256, trava o registro (423 numa
  segunda tentativa) e fica na trilha de auditoria. Usa o mesmo
  `confirmar_registro` / `bloquear_se_confirmado` das avaliações.
- Só pode validar quem pode avaliar aquele residente (`pode_avaliar`, ou seja, do mesmo programa).
- Participação: `cirurgiao_principal`, `primeiro_auxiliar` ou `segundo_auxiliar`.
- A data não pode estar no futuro.

| Rota | Quem | O que faz |
|---|---|---|
| `POST /api/v1/procedimentos` | residente | registra (fica pendente) |
| `GET /api/v1/procedimentos?residente_id=&status=` | quem vê o portfólio | lista |
| `GET /api/v1/procedimentos/pendentes` | preceptor, R4/R5 | fila de validação |
| `POST /api/v1/procedimentos/{id}/decidir` | preceptor, R4/R5 | `{"aprovado": true}` ou `{"aprovado": false, "motivo_recusa": "..."}` |

> **Para decidir:** a lista de procedimentos está em texto livre. Se a cliente
> quiser uma lista fechada (por exemplo, a do documento das EPAs), dá para
> trocar `nome` por uma chave estrangeira depois.

---

## 3. EPAs: documento + ligação com as tarefas 1 e 2

### 3.1 Catálogo das EPAs, tirado do documento

Arquivo novo: `app/core/catalogo_epas.py`. É só dado, no mesmo estilo do
`instrumentos.py`. Fonte: *Cadernos da Residência Médica — Cirurgia Geral, vol. 1 (2022)*.

- **As 16 EPAs de Cirurgia Geral** e o **nível esperado ao fim de cada ano**
  vêm exatamente do **Quadro 1 (p. 15)**. Um teste confere EPA por EPA.
- O documento diz que as EPAs são **longitudinais**: são as mesmas 16 nos três
  anos, e só muda o nível esperado. Por isso, cada EPA tem **um nível por ano**
  (ex.: EPA 1 = R1: 2, R2: 3, R3: 5), e não um "ano esperado" único.
- **Mínimo para certificar** (item 6b de cada EPA): *"12 vezes no trimestre, em
  contextos de complexidades diversas e sob a observação de diferentes
  supervisores"*. As exceções têm regra própria, e o texto delas também está no catálogo:
  - **EPA 11:** referência do CBC de 5 gastrectomias parciais e 2 totais no R2.
  - **EPA 16:** supervisionada por gestores.
- **Escala de 1 a 5** com a redação do documento (item 7): 1 observa, 2 supervisão direta,
  3 supervisão reativa, 4 sem supervisão, 5 supervisiona iniciantes.
- A decisão de nível é **trimestral, pelo Comitê de Competência Clínica (CCC)**.
  É por isso que o portfólio mostra as observações "no trimestre".

> **Para a tarefa 1:** o catálogo pode servir de seed para o banco. É só
> percorrer `EPAS`. Assim ninguém redigita as 16 EPAs.
>
> **Faltam as 8 EPAs de Cabeça e Pescoço.** O documento é só de Cirurgia Geral
> (R1 a R3). Quando o documento delas chegar, basta acrescentar em `EPAS`.

### 3.2 O que as tarefas 1 e 2 precisam devolver

O que é **fixo** (nome, nível esperado por ano, mínimo) já está no catálogo. O
que é **de cada residente** vem da tarefa 1, pelo arquivo `app/core/epas.py`:

```python
def progresso_do_residente(db: Session, residente_id: uuid.UUID) -> dict:
    return {
        "ano_residente": "R2",                  # ano atual do residente
        "epas": [
            {
                "codigo": "EPA 9",              # aceita "EPA 9", "EPA9", 9…
                "nivel_atual": 2,               # None = ainda sem nível
                "observacoes_trimestre": 7,     # opcional (tarefa 2)
                "atualizado_em": datetime(...), # opcional (última decisão do CCC)
            },
            ...
        ],
    }
```

- Nome, especialidade, níveis esperados e mínimo são **completados pelo catálogo** a partir do código.
- Para uma EPA **fora do catálogo** (as de Cabeça e Pescoço, por enquanto), a
  entrada precisa trazer `nome` e `niveis_esperados` (ex.: `{"R4": 2, "R5": 3}`).
  Sem isso, o sistema mostra um erro que diz o que falta.
- **Enquanto `app/core/epas.py` não existir**, o portfólio mostra as 16 EPAs com
  a trajetória esperada (R1, R2, R3) e o mínimo por trimestre. Quando a tarefa 1
  subir o arquivo, a comparação aparece sozinha, sem mexer no portfólio.

Como a situação de cada EPA é calculada:

| Situação | Quando |
|---|---|
| `atingido` | o nível atual é maior ou igual ao nível esperado **para o ano atual** do residente |
| `abaixo` | o nível atual é menor que o esperado |
| `sem_nivel` | a EPA ainda não tem nível atual |
| `sem_referencia` | tem nível, mas não se sabe o ano do residente (ou a EPA não prevê aquele ano) |

> **Para decidir com a tarefa 1:** o `Usuario` **não guarda o ano do residente**
> (R1, R2…). Sem esse dado, dá para mostrar o nível atual, mas não dá para dizer
> se está no esperado. Por isso ele entra no contrato (`ano_residente`), e a
> tarefa 1 escolhe onde guardar.

## 4. Rotas do portfólio

| Rota | Quem |
|---|---|
| `GET /api/v1/portfolio/meu` | residente (o próprio) |
| `GET /api/v1/portfolio/meu/pdf` | residente (o próprio) |
| `GET /api/v1/portfolio/residentes` | lista de quem você pode abrir (alimenta o seletor da tela) |
| `GET /api/v1/portfolio/{residente_id}` | o próprio residente, preceptor ou R4/R5 do mesmo programa, admin |
| `GET /api/v1/portfolio/{residente_id}/pdf` | idem |

- **Outro residente não vê**, mesmo sendo do mesmo programa.
- Toda exportação em PDF fica registrada na auditoria (`portfolio.exportado_pdf`),
  porque exportar dado pessoal é um evento relevante para a LGPD.
- O nome do arquivo segue o formato `portfolio-ana-souza-2026-09-25.pdf`.

---

## 5. PDF

`app/core/portfolio_pdf.py`, com **ReportLab**. É Python puro, instala com `pip`
em Windows, Mac ou Linux. Não usei o WeasyPrint porque ele exige bibliotecas de
sistema (Cairo/Pango), que costumam dar problema no Windows.

- A4, com a identificação e os números-resumo no topo.
- Mapa das EPAs com barra de nível e o nível esperado marcado.
- Gráfico de evolução por instrumento, com as faixas de corte ao fundo, e barras por domínio.
- Zwisch por etapa, procedimentos por nome e participação, e histórico com o feedback.
- Rodapé com "Página X de Y", data de geração e os primeiros 12 caracteres do
  hash de integridade de cada avaliação.
- O texto digitado pelo usuário é escapado. Um `<` ou `&` na observação não quebra o PDF.

---

## 6. Tela

`frontend/portfolio.html` + `frontend/portfolio.css`. É HTML e JS puro, no mesmo
padrão do `dashboard.html`, com fonte e botões grandes para os usuários mais velhos.

- **Residente:** abre direto o próprio portfólio.
- **Preceptor, R4/R5 e admin:** escolhem o residente num seletor. Também dá para
  abrir direto com `portfolio.html?residente=<id>`.
- O botão **Exportar PDF** baixa o arquivo gerado pelo backend.
- No `dashboard.html`, os cartões "Portfólio", "Meus residentes" e (no caso do
  admin) "Portfólios" agora levam para esta tela.

---

## 7. Arquivos

**Novos**

| Arquivo | O que é |
|---|---|
| `app/core/portfolio.py` | monta o portfólio (a única fonte para a tela e o PDF) |
| `app/core/catalogo_epas.py` | as 16 EPAs do documento: nível esperado por ano e mínimo por trimestre (§3.1) |
| `app/core/portfolio_epas.py` | junta o catálogo com os dados da tarefa 1 (§3.2) |
| `app/core/portfolio_pdf.py` | gera o PDF |
| `app/core/permissoes_portfolio.py` | quem pode ver o portfólio de quem |
| `app/api/routes/portfolio.py` | rotas do portfólio |
| `app/api/routes/procedimentos.py` | rotas de procedimentos |
| `app/schemas/portfolio.py`, `app/schemas/procedimentos.py` | formatos de entrada e saída |
| `frontend/portfolio.html`, `frontend/portfolio.css` | tela |
| `seed_portfolio.py` | dados **fictícios** para a demonstração |
| `tests/test_portfolio.py`, `tests/test_procedimentos.py`, `tests/test_catalogo_epas.py` | 53 testes (o catálogo é conferido contra o Quadro 1) |

**Alterados** (só acréscimos)

| Arquivo | Mudança |
|---|---|
| `app/db/models.py` | classe `Procedimento` no fim do arquivo, mais os imports `date` e `Date` |
| `app/main.py` | registra os 2 routers novos e adiciona `expose_headers=["Content-Disposition"]` no CORS, senão o navegador esconde o nome do PDF |
| `frontend/dashboard.html` | cartões com link para o portfólio |
| `requirements.txt` | `reportlab>=4.0` e `pypdf>=3.0` (este último só para os testes) |

---

## 8. Como rodar

```bash
rm -f dev.db                         # tem tabela nova (procedimentos)
pip install -r requirements.txt
python -m pytest tests/ -q
python seed_portfolio.py             # contas de teste + histórico fictício da Ana
uvicorn app.main:app --reload
cd frontend && python -m http.server 8080
```

Abra `http://localhost:8080/login.html`:
- `ana@hospital.br` para ver o portfólio como residente;
- `bruno@hospital.br` para ver como preceptor.

A senha das duas contas é `Residencia2026`.

---

## 9. Pendências

| # | Item | Quem |
|---|---|---|
| 1 | Criar `app/core/epas.py` com `progresso_do_residente` (§3.2) | tarefa 1 |
| 2 | Guardar o **ano atual do residente** (R1…R5) e devolvê-lo em `ano_residente` | tarefa 1 |
| 3 | Enviar `observacoes_trimestre` por EPA | tarefa 2 |
| 4 | **Documento das 8 EPAs de Cabeça e Pescoço**: não está no caderno de Cirurgia Geral | cliente |
| 5 | Lista de procedimentos: texto livre ou lista fechada? | cliente |
| 6 | Check-in/check-out (frequência) aparece no MVP do documento do projeto, mas não existe no sistema | time |
| 7 | A `Avaliacao` não tem "data da atividade", então o portfólio usa `confirmado_em` como data | time |
