# Painel Êxito e Reversão — Parada Advogados / MMP

## O que é este projeto

Script Python que conecta no Odoo do MMP via XML-RPC (somente leitura), busca dados de sentenças e acórdãos, e gera um painel HTML interativo com três abas:
- **Sentenças** — taxa de êxito por cliente e projeto
- **Reversão recursal** — recursos interpostos pelo escritório que mudaram a decisão
- **Onde atuar** — recortes por UF, comarca e tipo de ação

## Estrutura

```
CLAUDE.md               este arquivo
atualizar.py            roda main.py com datas automáticas (use este no dia a dia)
main.py                 CLI completo com todas as opções
.env                    credenciais do Odoo (NÃO vai pro git)
.env.example            modelo do .env
painel/
  config.py             constantes do MMP (ids, clientes, classes de sentença)
  odoo.py               cliente XML-RPC somente leitura
  sentencas.py          aba Sentenças: consulta + transformação
  reversao.py           aba Reversão: consulta + transformação
  atuacao.py            aba Onde atuar: recortes UF/comarca/tipo
  build.py              injeta JSONs no template HTML
  util.py               helpers de data e agregação
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
| `__ASOF__` | data do cabeçalho |

## Como adicionar/remover clientes

Em `painel/config.py`, edite as listas:
- `CLIENTES_SENTENCAS` — clientes da aba Sentenças
- `CLIENTES_REVERSAO` — clientes da aba Reversão
- `CLIENTES_ATUACAO` — clientes da aba Onde atuar
- `APELIDOS_SENTENCAS` / `APELIDOS_REVERSAO` / `APELIDOS_ATUACAO` — nomes exibidos na página

O ID do Santander está em `SANTANDER_GROUP_ID = 215688`.

## Testes

```bash
pip install pytest
pytest -q
```

Cobrem transformações de dados, classificação de transições, agrupamentos — sem tocar a rede.

## Observações importantes

- O script usa `read_group` (agregado) — não traz linha a linha, é rápido e leve
- Registros arquivados são incluídos (`active_test: False`) — caso encerrado teve sentença
- Campos de data agrupados por `:month` precisam do contexto `lang: en_US` para vir em inglês
- `dossie_recurso` está vazio em parte dos casos — é a maior fragilidade do indicador de reversão
- Comparativo 2025 na aba Reversão vem desligado por padrão (convenção de registro diferente até ago/25)
