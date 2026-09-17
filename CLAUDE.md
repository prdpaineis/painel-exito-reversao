# Painel Êxito e Reversão — Parada Advogados / MMP

## O que é este projeto

Script Python que conecta no Odoo do MMP via XML-RPC (somente leitura), busca dados de sentenças e acórdãos, e gera um painel HTML interativo com cinco abas:
- **Sentenças** — taxa de êxito por carteira (dinâmica, por volume recente), com recorte por UF/comarca
- **Reversão recursal** — recursos interpostos pelo escritório que mudaram a decisão
- **Onde atuar** — recortes por UF, comarca e tipo de ação (única aba com extração agregada, `read_group`)
- **Recorri e ganhei** — recursos nossos contra sentença desfavorável que reverteram a decisão
- **Autor recorreu e perdi** — recursos do autor contra sentença favorável que reverteram a decisão

Sentenças, Reversão e as duas abas de recursos extraem **linha a linha** (`search_read`
paginado) — a carteira dinâmica, os slots de advogado agressor/contumaz e a
classificação de "quem recorreu" (pelas tarefas do caso) não dão para montar só
com agregados do servidor. `main.py`/`painel/build.py` continuam sendo a única
fonte de verdade: a Action diária roda esse pipeline, não scripts avulsos.

## Estrutura

```
CLAUDE.md               este arquivo
atualizar.py            roda main.py com datas automáticas (use este no dia a dia)
main.py                 CLI completo com todas as opções
.env                    credenciais do Odoo (NÃO vai pro git)
.env.example            modelo do .env
painel/
  config.py             constantes do MMP (ids, clientes, classes de sentença)
  odoo.py               cliente XML-RPC somente leitura (search_count, read_group, search_read)
  sentencas.py          aba Sentenças: extração linha a linha + carteira dinâmica + geo
  reversao.py           aba Reversão: extração linha a linha, vetor de 13 posições
  recursos.py           abas Recorri e ganhei / Autor recorreu e perdi: quem recorreu
  atuacao.py            aba Onde atuar: recortes UF/comarca/tipo (read_group agregado)
  build.py              injeta JSONs e textos de período no template HTML
  util.py               helpers de data, agregação e rótulos de período
templates/painel.html   template HTML completo (edite aqui para mudar o visual)
data/cobertura.json     bloco de auditoria de acórdãos (insumo externo)
out/                    saída gerada (ignorada pelo git)
.github/workflows/
  atualizar-painel.yml  GitHub Actions: roda todo dia às 7h (BRT)
```

## Credenciais (.env)

Copie `.env.example` para `.env` e preencha. O `.env` está no `.gitignore` e nunca vai para o git.

```
ODOO_URL=https://SEU-HOST-ODOO
ODOO_DB=SEU_BANCO
ODOO_LOGIN=usuario.integracao
ODOO_PASSWORD=SUA_SENHA
```

## Como rodar localmente

```bash
python atualizar.py
```

Calcula a data de hoje e o mês fechado automaticamente. Saída em `out/painel.html`.

Para controle manual:
```bash
python main.py --as-of 16/09/2026 --last-full-month 8
```

### Opções do main.py

| Opção | Descrição |
|---|---|
| `--as-of` | data exibida na página (dd/mm/aaaa) |
| `--last-full-month` | último mês fechado 1–12 (gráficos param nele) |
| `--year` | ano corrente do painel |
| `--out` | diretório de saída (padrão: ./out) |
| `--no-check` | pula conferência contra o servidor |

**Ao virar o mês:** só muda o `--last-full-month`. O `atualizar.py` faz isso automaticamente.

## GitHub Actions (automação diária)

- Roda todo dia às **07:00 BRT** (seg–sex) e manualmente via "Run workflow"
- Gera `out/painel.html` e commita como `painel-exito-reversao.html` na raiz do repo
- Exit code 3 (divergência leve de 1–2 registros em trânsito no Odoo) é tratado como aviso, não erro — o painel é gerado normalmente

Secrets necessários no GitHub (Settings → Secrets → Actions):
- `ODOO_URL`, `ODOO_DB`, `ODOO_LOGIN`, `ODOO_PASSWORD`

## Link público do painel

```
https://prdpaineis.github.io/painel-exito-reversao/painel-exito-reversao.html
```

Atualiza automaticamente toda manhã após o Actions rodar.

## Repositório

```
https://github.com/prdpaineis/painel-exito-reversao
```

## Como mudar o visual

Edite `templates/painel.html`. Os módulos Python não geram HTML — todo o CSS e JS está no template. Os marcadores que o build substitui são:

| Marcador | Conteúdo |
|---|---|
| `__EDATA__` | JSON da aba Sentenças |
| `__RDATA__` | JSON da aba Reversão |
| `__ADATA__` | JSON da aba Onde atuar |
| `__RLDATA__` | JSON das abas Recorri e ganhei / Autor recorreu e perdi |
| `__ASOF__` | data do cabeçalho (toda a página) |
| `__ANO__`, `__ANO_ANT__`, `__PERIODO__`, `__PERIODO_CURTO__`, `__PERIODO_TH__`/`__PERIODO_TH_ANT__`, `__MES_PARCIAL__`, `__MES_PARCIAL_LONGO_CAP__`, `__MES_FECHADO_LONGO__`, `__JANELA_CARTEIRA__` | período/ano exibidos em prosa — todos derivados de `sentencas["ano"]`/`["lastFullMonth"]`, sem nada pra editar à mão ao virar o mês |
| `__AGR__`/`__EXT__`/`__CONT__`, `__FFEXT__`/`__FFEXTIMPROC__`, `__AMBOS__`/`__SEM__`/`__ESCREP__`/`__ESCCON__`/`__AUTCON__`/`__AUTREP__` | números citados nos parágrafos "como os números são calculados" das abas Sentenças/Reversão/Recursos |

Ver a tabela completa (com o que cada marcador vira) em `README.md` → "Como o template funciona".

## Como adicionar/remover clientes

Em `painel/config.py`, edite:
- `CLIENTES_PADRAO` — carteira das abas Reversão, Recorri e ganhei e Autor recorreu e perdi (o resto vira "Outros")
- `CLIENTES_ATUACAO` / `APELIDOS_ATUACAO` — clientes da aba Onde atuar
- `ALIAS_CLIENTE` — apelido usado em toda a página (hoje só o CCB, nome longo → "CCB Brasil")

A aba **Sentenças não usa lista fixa**: a carteira é dinâmica, por volume recente
(`MIN_SENTENCAS_CARTEIRA` / `MESES_JANELA_CARTEIRA` em `config.py`; lógica em
`sentencas.py`).

O ID do Santander está em `SANTANDER_GROUP_ID = 215688`.

## Testes

```bash
pip install pytest
pytest -q
```

Cobrem transformações de dados, classificação de transições, carteira dinâmica,
"quem recorreu", agrupamentos — sem tocar a rede.

## Observações importantes

- Onde atuar usa `read_group` (agregado) — não traz linha a linha, é rápido e leve.
  Sentenças, Reversão e Recursos extraem **linha a linha** (`search_read` paginado):
  a carteira dinâmica, os slots de advogado agressor/contumaz e a classificação de
  "quem recorreu" por tarefa não davam para montar só com agregado do servidor.
- Registros arquivados são incluídos (`active_test: False`) — caso encerrado teve sentença
- Campos de data agrupados por `:month` (só em Onde atuar) precisam do contexto `lang: en_US` para vir em inglês
- `dossie_recurso` está vazio em parte dos casos — é a maior fragilidade do indicador de reversão pelo campo antigo; por isso as abas Recorri e ganhei/Autor recorreu e perdi usam as tarefas do caso (`project.task.tipo_recurso_id`) em vez desse campo
- Comparativo com o ano anterior na aba Reversão vem desligado por padrão (convenção de registro diferente até ago/25)
- **Limitação conhecida:** a renderização em JS de Sentenças e Reversão indexa os
  dados por ano **literal** (`e.y['2026']`, `sumAll('tot','2026')` etc. — hard-code
  que já vem da v1 do template). Funciona até o fim de 2026; ao entrar 2027, esses
  acessos por chave precisam virar `String(D.ano)`/`String(D.ano-1)` antes de gerar
  o painel do novo ano. Os textos em prosa (marcadores acima) já são dinâmicos.
