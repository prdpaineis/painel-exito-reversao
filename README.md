# Painel "Êxito e Reversão" — MMP

Gera a página HTML do painel (cinco abas: **Sentenças**, **Reversão recursal**,
**Onde atuar**, **Recorri e ganhei** e **Autor recorreu e perdi**) a partir do
Odoo do MMP, via XML-RPC, **somente leitura**.

"Onde atuar" continua usando consultas agregadas (`read_group` — quem soma é o
servidor). As outras quatro abas extraem linha a linha (`search_read` paginado):
a carteira dinâmica de Sentenças, os slots de advogado agressor/contumaz e a
classificação de "quem recorreu" (pelas tarefas do caso) não dão para montar só
com agregados do servidor. O script monta os quatro blocos de dados, injeta no
template e grava `out/painel.html`. Não escreve nada no Odoo.

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
`atuacao.json` / `recursos.json` (os dados, úteis para diff entre execuções).

**Ao virar o mês, suba o `--last-full-month`.** É a única coisa que muda de rotina.

### Conferência automática

Antes de gravar, o script compara os totais do JSON com `search_count` feito no
próprio servidor e imprime o resultado:

```
Conferindo contra o servidor:
  [ok] sentenças extraídas (linha a linha): 53.376 no painel · 53.376 no servidor
  [ok] acórdãos extraídos (linha a linha): 16.036 no painel · 16.036 no servidor
  [ok] recursos nossos com sentença desfavorável (por UF): 2.237 no painel · 2.237 no servidor
  [ok] recursos nossos do Santander: soma dos projetos × total do cliente: 1.197 · 1.197
  [ok] acórdãos extraídos p/ recursos (linha a linha): 6.568 no painel · 6.568 no servidor
```

Sentenças, Reversão e Recursos comparam o total de registros trazidos pelo
`search_read` contra `search_count` no mesmo domínio — o gate mais provável de
pegar erro de paginação ou de domínio numa extração linha a linha. Onde atuar
confere dois totais mais finos: contra o servidor, e a quebra por projeto contra
a quebra por cliente dentro do próprio JSON (duas consultas independentes ao
Odoo; a igualdade garante que os chips de projeto particionam o Santander em vez
de recontá-lo).

> O `search_count` da linha "por UF" repete as **duas** restrições que o painel usa:
> sentença de origem desfavorável **e** resultado após o acórdão também classificável.
> Sem a segunda, o servidor conta a mais (inclui o que virou homologação de acordo)
> e o gate falha à toa.

Se algum total divergir, a saída ainda é gravada mas o processo termina com
código **3** — dá para usar isso como gate no CI.

## O que cada aba mede

**Sentenças.** Êxito = `Improcedente` + `Extinção` (sem mérito ou da execução),
sobre as sentenças com tipo informado — as duas aparecem separadas, porque não
valem o mesmo (extinção em regra deixa o autor livre para ajuizar de novo).
Homologação de acordo entra no denominador; "sem tipo" fica de fora. Mês pelo
`data_sentenca`.

*Carteira dinâmica*, não uma lista fixa: um cliente só ganha chip próprio com
`MIN_SENTENCAS_CARTEIRA` (5) sentenças ou mais nos últimos `MESES_JANELA_CARTEIRA`
(3) meses fechados; de 1 até esse piso vai para "Outros"; zero nesse período =
saiu da carteira, fora de todos os números (inclusive do comparativo com o ano
anterior — compara a mesma carteira nos dois anos). As listas `sairam`/`novos`
alimentam os avisos no topo da aba. `config.py` tem os dois parâmetros.

O bloco `geo` cruza cliente × UF × comarca (só meses fechados do ano corrente) e
alimenta a tabela e a pergunta em linguagem natural da aba — interpretada na
própria página, sem chamar serviço nenhum.

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

Dentro de `FF` e `DF`, o vetor separa o resultado por improcedência × extinção
(e, nas extinções, se o caso tem advogado adverso agressor) — ver a tabela de
formato mais abaixo.

Ressalvas que estão escritas na própria página e valem repetir aqui:

* `dossie_recurso` está **vazio em parte dos casos**, que ficam fora da conta de
  reversão nossa × do adversário (mas entram em `tot`). É a maior fragilidade do
  indicador.
* Até ~ago/2025 o campo `tipo_sentenca_modificada_id` seguia outra convenção
  ("Procedente" indicava *recurso provido*, não o resultado do caso). Por isso o
  comparativo com o ano anterior vem **desligado** nessa aba.
* O campo `tipo_sentenca_modificada_id` tende a registrar "Improcedente" mesmo
  quando o que foi mantido/revertido foi uma extinção — por isso a contagem de
  "para extinção" provavelmente está subestimada (a página cita os números exatos
  de cada rodada no parágrafo de definições).

**Recorri e ganhei / Autor recorreu e perdi.** "Quem recorreu" não está num campo
direto do caso — sai das tarefas do processo (`project.task.tipo_recurso_id`):

* Tarefa de **Apelação**, **Inominado** ou **Preparo** → recurso nosso.
* Tarefa de **Contrarrazões** (de Apelação, de Inominado ou Adesivo) → recurso do
  autor (só se contrarrazoa recurso da outra parte).
* Caso com as duas → vale o sentido da sentença: contra nós → conta como recurso
  nosso; a nosso favor → recurso do autor.
* Caso sem nenhuma dessas tarefas fica de fora das duas abas.
* Especial, Extraordinário, Embargos e Agravos ficam fora (outra instância ou
  incidental).

Ganhei = recurso nosso e a sentença desfavorável virou favorável (`DF`). Perdi =
recurso do autor e a sentença favorável virou desfavorável (`FD`). A lista de
casos é o ano corrente inteiro; a taxa usa só os acórdãos até o fim do último mês
fechado. "Autor recorreu e perdi" tem um filtro extra por Agressor/Contumaz
(`agressor_contumaz`). A aba também mostra, nos parágrafos de definição, a
conferência entre essa classificação por tarefa e o campo antigo `dossie_recurso`.

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
externa além das fontes do Google) com marcadores que `painel/build.py` substitui
a cada rodada — os blocos de dados (JSON) e um conjunto de textos em prosa que
citam período e números específicos (não dá pra deixar isso a cargo do JS sem
duplicar a agregação lá).

| Marcador | Vira |
|---|---|
| `__EDATA__` | JSON da aba Sentenças, dentro de `<script id="e-data">` |
| `__RDATA__` | JSON da aba Reversão, dentro de `<script id="r-data">` |
| `__ADATA__` | JSON da aba Onde atuar, dentro de `<script id="a-data">` |
| `__RLDATA__` | JSON das abas de recursos, dentro de `<script id="rl-data">` |
| `__ASOF__` | a data do cabeçalho, em toda a página |
| `__ANO__` / `__ANO_ANT__` | ano corrente / anterior |
| `__PERIODO__` / `__PERIODO_CURTO__` | `"jan–ago/2026"` / `"jan–ago"` |
| `__PERIODO_TH__` / `__PERIODO_TH_ANT__` | idem, formato de cabeçalho de tabela |
| `__MES_PARCIAL__` / `__MES_PARCIAL_LONGO_CAP__` | mês seguinte ao fechado: `"set"` / `"Setembro"` |
| `__MES_FECHADO_LONGO__` | nome por extenso do último mês fechado: `"agosto"` |
| `__JANELA_CARTEIRA__` | janela da carteira de Sentenças: `"jun–ago/2026"` |
| `__AGR__` / `__EXT__` / `__CONT__` | extinções c/ advogado agressor / total de extinções / c/ agressor-contumaz, no período fechado |
| `__FFEXT__` / `__FFEXTIMPROC__` | vitórias mantidas por extinção / dessas, gravadas como improcedência |
| `__AMBOS__` / `__SEM__` | casos com as duas tarefas de recurso / sem nenhuma |
| `__ESCREP__` / `__ESCCON__` / `__AUTCON__` / `__AUTREP__` | conferência `quem` × `dossie_recurso` (ver `recursos.py`) |

Todos os marcadores de período são resolvidos a partir de `sentencas["ano"]` e
`sentencas["lastFullMonth"]` — mudar só o `--last-full-month` já atualiza a
página inteira; não há texto de período para editar à mão.

> **Limitação conhecida:** os marcadores acima cobrem o texto em prosa. A lógica
> de renderização em JS (gráficos e tabelas das abas Sentenças e Reversão) ainda
> indexa os dados por ano **literal** (`e.y['2026']`, `sumAll('tot','2026')` etc.)
> — um hard-code que já vem da v1 do template, não só desta rodada. Funciona
> normalmente até o fim de 2026; ao entrar 2027, esses acessos por chave
> precisam ser generalizados (trocar o `'2026'` fixo por `String(D.ano)`) antes
> de gerar o painel do novo ano.

Formato dos dados (vetor por mês, 12 posições por ano):

```jsonc
// e-data → asOf, ano, lastFullMonth,
//   clients[].y[ano][mes] = [improc, extinção, parcial, procedente, acordo, sem tipo,
//                             extinção c/ advogado agressor, extinção c/ agressor/contumaz]
//   clients[] só traz quem está na carteira ("Outros" agrega quem tem pouco volume)
//   sairam[] = [{name, ultimo}], novos[] = [{name, desde}]
//   projects[] = mesmo formato de clients, só o Santander, top N projetos + "Outros projetos"
//   geo = {cli: [nomes], ufs: {sigla: nome}, com: [[comarca, uf]],
//          rows: [[índiceCliente, índiceComarca, improc, ext, parcial, proc, acordo, ext_adv_agr, ext_contumaz]]}
//
// r-data → clients[].tot[ano][mes] e .nos[ano][mes] = 13 posições:
//   [FF, FD, DF, DD, X, DF→improc, DF→ext, FF→improc, FF→ext,
//    DF ext c/ adv.agressor, FF ext c/ adv.agressor, DF ext c/ contumaz, FF ext c/ contumaz]
//   .nos = só os acórdãos em que o recurso foi nosso · nota_ext = {ff_ext, ff_ext_como_improc}
//
// a-data → dims[dimensão].itens[].c[] = [índiceDoCliente, sentenças6, tot5, nos5]
//          dims[dimensão].itens[].p[] = o mesmo, por índice de projeto do Santander
//          .clientes e .projetos dão o nome de cada índice
//          sem recorte mensal; 0 no lugar de um vetor todo-zero
//
// rl-data → asOf, conferencia{ambos, semTarefa, escRepresentada, escContraria, autContraria, autRepresentada},
//   ganhei/perdi = {por_cliente: [{cli, lista, num, den, lista_s, num_s, den_s, lista_n, num_n, den_n}],
//                   rows: [[data, processo, cliente, projeto, uf, comarca, sentença, resultado, tipos, agressorContumaz]]}
//   sufixo _s/_n = só os casos com agressor_contumaz "Sim"/"Não"
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
* `search_read` (Sentenças, Reversão, Recursos) pagina sozinho, sem `limit=0` — lê
  em lotes de 1000/2000 e para quando o lote vem menor que o pedido. Ano inteiro
  de sentenças ou acórdãos são dezenas de milhares de registros; o custo é rede,
  não o servidor (mesma restrição de `active_test: False` do `read_group`).

## Testes

```bash
pip install pytest
pytest -q
```

Cobrem: a carteira dinâmica de Sentenças (ativo/"Outros"/saiu, novos, projeto fora
do topo, o bloco `geo`); a classificação das transições de Reversão (incluindo o
vetor de 13 posições e `nota_ext`); "quem recorreu" e as seções ganhei/perdi de
Recursos (com o filtro Agressor/Contumaz e a conferência `quem` × `dossie_recurso`);
e a montagem dos recortes da aba Onde atuar — nome da UF, comarca com a UF junto,
compactação dos vetores zerados, e a quebra por projeto (piso de volume medido só
na dimensão padrão, ordem dos chips, invariante de que a soma dos projetos
reproduz a célula do Santander sem contá-la duas vezes). Não tocam a rede.

## Estrutura

```
main.py                 CLI: busca → monta → confere → grava
painel/config.py        credenciais (env) e constantes do MMP (ids, classes, listas)
painel/odoo.py          cliente XML-RPC só-leitura (search_count, read_group, search_read)
painel/sentencas.py     aba Sentenças: extração linha a linha + carteira dinâmica + geo
painel/reversao.py      aba Reversão: idem, vetor de 13 posições, dossie_recurso
painel/recursos.py      abas "Recorri e ganhei" / "Autor recorreu e perdi": quem recorreu
                         (project.task.tipo_recurso_id) + classificação ganhei/perdi
painel/atuacao.py       aba Onde atuar: recortes por UF/comarca/tese × cliente e projeto
                         (única aba que ainda usa read_group agregado)
painel/build.py         injeta os JSONs e os textos de período/prosa no template
painel/util.py          parsing de mês, helpers de agregação, rótulos de período
templates/painel.html   a página (edite aqui para mudar o visual)
data/cobertura.json     insumo do bloco de auditoria
```
