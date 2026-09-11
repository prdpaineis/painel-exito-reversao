# Painel "Êxito e Reversão" — MMP

Gera a página HTML do painel (três abas: **Sentenças**, **Reversão recursal** e
**Onde atuar**) a partir do Odoo do MMP, via XML-RPC, **somente leitura**.

O script faz dezesseis consultas agregadas (`read_group` — quem soma é o servidor,
não trazemos linha a linha), monta os três blocos de dados, injeta no template e
grava `out/painel.html`. Roda em um ou dois minutos e não escreve nada no Odoo.

> **Use repositório privado.** Não há credenciais aqui, mas o template carrega os
> textos, as definições e a estrutura do painel do escritório, e `data/cobertura.json`
> traz contagens de acórdãos por ano.

## Requisitos

* Python 3.8+ — **sem dependências de runtime** (só a biblioteca padrão).
* Rede até o servidor Odoo (o script não passa por proxy nem VPN por conta própria).
* Um usuário do Odoo com permissão de leitura em `dossie.dossie`.

## Configuração

```bash
cp .env.example .env      # preencha ODOO_URL, ODOO_DB, ODOO_LOGIN, ODOO_PASSWORD
```

O `.env` está no `.gitignore` e nunca deve ser commitado. Em CI, use os *secrets*
do repositório — variáveis de ambiente têm precedência sobre o arquivo.

Prefira um **usuário de integração só-leitura** em vez da conta de uma pessoa: o
MMP tem regras de visibilidade por empresa, então o recorte que o script enxerga
depende de quem está logado, e os números mudam se o login mudar.

## Uso

```bash
python main.py --as-of 09/09/2026 --last-full-month 8
```

| Opção | Para que serve |
|---|---|
| `--as-of` | data que aparece na página (`dd/mm/aaaa`). Padrão: hoje. |
| `--last-full-month` | último mês **fechado** (1–12). Gráficos e acumulados param nele; o mês seguinte aparece como parcial. Padrão: mês anterior ao de hoje. |
| `--year` | ano corrente do painel; o anterior entra como comparativo. Padrão: ano de hoje. |
| `--out` | diretório de saída. Padrão: `./out`. |
| `--no-check` | pula a conferência contra o servidor (não recomendado). |

Saída em `out/`: `painel.html` (a página) e `sentencas.json` / `reversao.json` /
`atuacao.json` (os dados, úteis para diff entre execuções).

**Ao virar o mês, suba o `--last-full-month`.** É a única coisa que muda de rotina.

### Conferência automática

Antes de gravar, o script compara os totais do JSON com `search_count` feito no
próprio servidor e imprime o resultado:

```
Conferindo contra o servidor:
  [ok] sentenças de 2026 (todos os clientes): 18.449 no painel · 18.449 no servidor
  [ok] recursos nossos jan–mês 8/2026: 2.268 no painel · 2.268 no servidor
  [ok] recursos nossos com sentença desfavorável (por UF): 2.237 no painel · 2.237 no servidor
  [ok] recursos nossos do Santander: soma dos projetos × total do cliente: 1.195 · 1.195
```

A última linha não vai ao servidor: confere a quebra por projeto contra a quebra
por cliente dentro do próprio JSON. São duas consultas independentes ao Odoo, e é
essa igualdade que garante que os chips de projeto particionam o Santander em vez
de recontá-lo.

> O `search_count` da terceira linha repete as **duas** restrições que o painel usa:
> sentença de origem desfavorável **e** resultado após o acórdão também classificável.
> Sem a segunda, o servidor devolve 2.238 (um acórdão que virou homologação de acordo)
> e o gate falha à toa.

Se algum total divergir, a saída ainda é gravada mas o processo termina com
código **3** — dá para usar isso como gate no CI.

## O que cada aba mede

**Sentenças.** Êxito = `Improcedente` + `Extinção` (sem mérito ou da execução),
sobre as sentenças com tipo informado. Homologação de acordo entra no denominador;
"sem tipo" fica de fora e aparece em coluna própria. Mês pelo `data_sentenca`.

**Reversão recursal.** Dos casos em que **nós** recorremos de uma sentença
desfavorável, a fração em que o acórdão mudou o resultado a nosso favor. Recurso
da parte contrária não entra (isso é defesa, não reversão) e aparece em bloco
separado na página. Cada acórdão é classificado pela transição entre a classe da
sentença original e a do resultado após o acórdão:

| | favorável | desfavorável |
|---|---|---|
| **favorável** | `FF` manteve | `FD` reverteu contra |
| **desfavorável** | `DF` **reverteu a favor** | `DD` manteve |

`favorável` = Improcedente, Extinção, Favorável · `desfavorável` = Procedente,
Parcialmente Procedente, Desfavorável. Mudança de tipo dentro da mesma classe
(`Parcial → Procedente`, que o MMP usa para "condenação mantida") **não** é reversão.

Duas ressalvas que estão escritas na própria página e valem repetir aqui:

* `dossie_recurso` está **vazio em parte dos casos**, que ficam fora da conta de
  reversão. É a maior fragilidade do indicador.
* Até ~ago/2025 o campo `tipo_sentenca_modificada_id` seguia outra convenção
  ("Procedente" indicava *recurso provido*, não o resultado do caso). Por isso o
  comparativo com 2025 vem **desligado** nessa aba.

**Onde atuar.** Responde "por onde começar" quando a taxa está baixa em vários
lugares. Para cada recorte — UF, comarca ou tipo de ação, cruzado com o cliente —
compara a taxa dele com a do **restante** daquele mesmo corte e calcula quantos
casos estariam em jogo:

```
potencial = (taxa dos demais recortes − taxa deste recorte) × volume deste recorte
```

O benchmark é sempre o *resto*, nunca a média que inclui o próprio recorte: São
Paulo sozinho é quase metade dos recursos, e comparado consigo mesmo nunca
apareceria como oportunidade. É isso que separa "taxa ruim" de "problema grande":
com os dados de setembro/2026, Paraná reverte 8,0% e São Paulo 12,0%, mas o Paraná
tem 75 recursos (5 casos a recuperar) e São Paulo tem 974 (35 casos).

A página também mostra o intervalo de confiança de Wilson a 95% de cada taxa e
marca como *amostra pequena* os recortes com menos de 10 casos no denominador —
com 3 ou 4 casos a faixa passa de 40 pontos percentuais, e ali não há conclusão
possível, só ruído.

Escolhido o **Santander**, aparece uma segunda linha de filtros com os projetos do
caso (`projeto_id`) — Consignado, Revisionais, Indenizatórias, Escritório externo e
os demais. Vêm de duas consultas próprias, com o mesmo recorte, filtradas pelo
`grupo_id` do Santander; a quebra por projeto e a quebra por cliente são
independentes, e a soma dos projetos reproduz exatamente a célula do Santander (é o
que a última linha da conferência verifica). Projeto com menos de 10 acórdãos e
menos de 50 sentenças no ano não ganha chip próprio: entra somado em *Outros
projetos*, porque com esse volume não há comparação possível, só ruído. O piso é
medido **na dimensão UF**, onde cada caso aparece uma vez — em comarca e tipo de
ação o mesmo caso reaparece e triplicaria a contagem.

Com um projeto selecionado, tudo passa a ser calculado dentro dele: a taxa, o
benchmark (os demais recortes *do mesmo projeto*) e o potencial.

Diferente das outras abas, esta não tem recorte mensal: o período fechado inteiro
entra numa conta só, para dar volume às células menores. A caixa de pergunta em
linguagem natural é interpretada **na própria página**, sem chamar serviço nenhum:
reconhece os nomes de cliente, projeto, UF, comarca e tipo de ação que existem nos
dados e ajusta os filtros. Citar um projeto ("como está a reversão no consignado?")
já troca o cliente para Santander e aplica o filtro; citar o cliente sem citar
projeto limpa um filtro de projeto que tenha ficado da pergunta anterior. O ditado
por voz usa o reconhecimento do próprio navegador (Chrome e Edge) e o botão só
aparece onde ele existe.

> Uma capacidade da plataforma permitiria usar o Claude para interpretar a
> pergunta, mas ela é incompatível com artifact compartilhado por link — e o
> painel existe para ser compartilhado. Por isso a interpretação é local.

## Como o template funciona

`templates/painel.html` é a página completa (HTML + CSS + JS, sem dependência
externa além das fontes do Google) com três marcadores que o build substitui:

| Marcador | Vira |
|---|---|
| `__EDATA__` | JSON da aba Sentenças, dentro de `<script id="e-data">` |
| `__RDATA__` | JSON da aba Reversão, dentro de `<script id="r-data">` |
| `__ADATA__` | JSON da aba Onde atuar, dentro de `<script id="a-data">` |
| `__ASOF__` | a data do cabeçalho |

Formato dos dados (vetor por mês, 12 posições por ano):

```jsonc
// e-data → clients[].y[ano][mes] = [improc, extinção, parcial, procedente, acordo, sem tipo]
// r-data → clients[].tot[ano][mes] e .nos[ano][mes] = [FF, FD, DF, DD, X]
//          .nos = só os acórdãos em que o recurso foi nosso
// a-data → dims[dimensão].itens[].c[] = [índiceDoCliente, sentenças6, tot5, nos5]
//          dims[dimensão].itens[].p[] = o mesmo, por índice de projeto do Santander
//          .clientes e .projetos dão o nome de cada índice
//          sem recorte mensal; 0 no lugar de um vetor todo-zero
```

Para mexer no visual, edite o template — os módulos Python não geram HTML.

### `data/cobertura.json`

Alimenta o bloco "Quanto disto dá para auditar" (acórdãos com inteiro teor
gravado, por ano). **Vem de uma auditoria separada, não desta pipeline** — o
script apenas repassa o arquivo. Se ele não existir, a página sai sem esse bloco.

## Armadilhas do Odoo 10 (já custaram tempo)

* `execute_kw(db, uid, pw, model, method, args, kwargs)` — `args[0]` é o domínio,
  **sem envelope extra**. Errar isso devolve traceback de Python 2 apontando para
  módulos customizados, não "domínio inválido".
* Todo campo usado em `groupby` precisa aparecer **também** em `fields`, inclusive
  o campo de data que leva o sufixo `:month`.
* `limit=0` significa *sem limite* neste servidor. Nunca passe zero em tabela grande.
* Registros arquivados só aparecem com `active_test: False` no contexto — o painel
  os inclui (é o comportamento correto: caso encerrado teve sentença).
* O rótulo de `:month` vem traduzido conforme o idioma do usuário. Fixamos
  `lang: en_US` no contexto e, por garantia, há fallback que lê a data do
  `__domain` do grupo.
* Filtrar por caminho relacionado (`task_id.campo`) em tabelas grandes estoura o
  tempo. Nada aqui faz isso, mas vale lembrar ao estender.

## Testes

```bash
pip install pytest
pytest -q
```

Cobrem a classificação das transições, a separação recurso nosso × adversário, o
agrupamento em "Outros", a leitura do mês em inglês, português e pelo `__domain`,
e a montagem dos recortes da aba Onde atuar: nome da UF, comarca com a UF junto,
compactação dos vetores zerados, e a quebra por projeto — piso de volume medido
só na dimensão padrão, ordem dos chips, e a invariante de que a soma dos projetos
reproduz a célula do Santander sem contá-la duas vezes. Não tocam a rede.

## Estrutura

```
main.py                 CLI: busca → monta → confere → grava
painel/config.py        credenciais (env) e constantes do MMP (ids, classes, listas)
painel/odoo.py          cliente XML-RPC só-leitura (search_count, read_group)
painel/sentencas.py     aba Sentenças: consulta + transformação + conferência
painel/reversao.py      aba Reversão: idem, com a dimensão dossie_recurso
painel/atuacao.py       aba Onde atuar: recortes por UF/comarca/tese × cliente e projeto
painel/build.py         injeta os JSONs no template
painel/util.py          parsing de mês, helpers de agregação
templates/painel.html   a página (edite aqui para mudar o visual)
data/cobertura.json     insumo do bloco de auditoria
```
