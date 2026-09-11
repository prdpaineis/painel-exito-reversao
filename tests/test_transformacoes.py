# -*- coding: utf-8 -*-
"""Testes das transformações (sem rede — dados sintéticos).

    pytest -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from painel import reversao, sentencas  # noqa: E402
from painel.util import parse_ano_mes  # noqa: E402


# --------------------------------------------------------------------------
# Leitura do mês devolvido pelo Odoo
# --------------------------------------------------------------------------

def test_mes_em_ingles():
    assert parse_ano_mes("August 2026") == (2026, 8)


def test_mes_em_portugues():
    assert parse_ano_mes("agosto 2026") == (2026, 8)


def test_mes_pelo_dominio_quando_rotulo_e_estranho():
    dominio = [["data_acordao", ">=", "2026-03-01"], ["data_acordao", "<", "2026-04-01"]]
    assert parse_ano_mes("rótulo inesperado", dominio) == (2026, 3)


# --------------------------------------------------------------------------
# Sentenças
# --------------------------------------------------------------------------

def _linha_s(nome, mes, tipo, n, escopo="cliente", ano=2026):
    return sentencas.Linha(escopo=escopo, nome=nome, ano=ano, mes=mes, tipo_id=tipo, quantidade=n)


def test_sentencas_soma_extincoes_no_mesmo_slot():
    dados = sentencas.montar([
        _linha_s("Santander", 1, "1", 10),   # improcedente
        _linha_s("Santander", 1, "3", 4),    # extinção sem mérito
        _linha_s("Santander", 1, "7", 1),    # extinção da execução -> mesmo slot
        _linha_s("Santander", 1, "2", 5),    # procedente
    ], as_of="01/01/2027", ultimo_mes_fechado=1)
    santander = next(c for c in dados["clients"] if c["name"] == "Santander")
    janeiro = santander["y"]["2026"][0]
    assert janeiro[0] == 10          # improcedentes
    assert janeiro[1] == 5           # extinções somadas
    assert janeiro[3] == 5           # procedentes


def test_sentencas_tipo_desconhecido_vai_para_sem_tipo():
    dados = sentencas.montar([_linha_s("Santander", 2, "", 7)],
                             as_of="01/01/2027", ultimo_mes_fechado=2)
    santander = next(c for c in dados["clients"] if c["name"] == "Santander")
    assert santander["y"]["2026"][1][sentencas.SLOT_SEM_TIPO] == 7


def test_sentencas_cliente_fora_da_lista_cai_em_outros():
    dados = sentencas.montar([
        _linha_s("Santander", 1, "1", 3),
        _linha_s("Banco Que Ninguém Conhece", 1, "1", 2),
    ], as_of="01/01/2027", ultimo_mes_fechado=1)
    outros = next(c for c in dados["clients"] if c["name"] == "Outros")
    assert outros["y"]["2026"][0][0] == 2
    assert outros["members"] == ["Banco Que Ninguém Conhece"]


def test_sentencas_projeto_pequeno_vira_outros_projetos():
    linhas = [_linha_s("Santander - Consignado", 1, "1", 100, escopo="projeto"),
              _linha_s("Santander - Coisa Rara", 1, "1", 3, escopo="projeto")]
    dados = sentencas.montar(linhas, as_of="01/01/2027", ultimo_mes_fechado=1)
    nomes = [p["name"] for p in dados["projects"]]
    assert nomes == ["Consignado", "Outros projetos"]  # prefixo "Santander - " removido
    assert dados["projects"][-1]["y"]["2026"][0][0] == 3


# --------------------------------------------------------------------------
# Reversão recursal
# --------------------------------------------------------------------------

def test_classificacao_das_transicoes():
    s = reversao.slot_da_transicao
    assert reversao.SLOTS[s("1", "1")] == "FF"   # improcedente mantida
    assert reversao.SLOTS[s("1", "2")] == "FD"   # virou procedente: perdemos
    assert reversao.SLOTS[s("2", "1")] == "DF"   # condenação virou improcedência: reversão
    assert reversao.SLOTS[s("4", "2")] == "DD"   # parcial -> procedente: mesma classe, manteve
    assert reversao.SLOTS[s("2", "5")] == "X"    # homologação de acordo: fora da conta
    assert reversao.SLOTS[s("", "1")] == "X"     # sem sentença original registrada


def _linha_r(nome, mes, recurso, tipo, mod, n, escopo="cliente", ano=2026):
    return reversao.Linha(escopo=escopo, nome=nome, ano=ano, mes=mes, recurso=recurso,
                          tipo_id=tipo, modificada_id=mod, quantidade=n)


def test_reversao_separa_recurso_nosso_do_adversario():
    linhas = [
        _linha_r("Santander", 1, "representada", "2", "1", 3),   # nosso, reverteu a favor
        _linha_r("Santander", 1, "ambos", "2", "2", 7),          # nosso, manteve condenação
        _linha_r("Santander", 1, "contraria", "1", "2", 5),      # do adversário, perdemos
        _linha_r("Santander", 1, "", "1", "1", 11),              # sem registro de quem recorreu
    ]
    dados = reversao.montar(linhas, as_of="01/01/2027", ultimo_mes_fechado=1)
    santander = next(c for c in dados["clients"] if c["name"] == "Santander")
    nos = santander["nos"]["2026"][0]
    tot = santander["tot"]["2026"][0]

    assert nos[2] == 3 and nos[3] == 7      # só os recursos nossos
    assert nos[1] == 0 and nos[0] == 0      # o resto não contamina "nos"
    assert tot[1] == 5 and tot[0] == 11     # mas continua em "tot"
    # reversão recursal = DF / (DF + DD)
    assert nos[2] / (nos[2] + nos[3]) == 0.3


def test_reversao_repassa_cobertura():
    cobertura = [{"ano": "2026", "com": 10, "sem": 2}]
    dados = reversao.montar([], as_of="01/01/2027", ultimo_mes_fechado=1, cobertura=cobertura)
    assert dados["cobertura"] == cobertura


def test_reversao_ignora_anos_fora_da_janela():
    linhas = [_linha_r("Santander", 1, "representada", "2", "1", 9, ano=2019)]
    dados = reversao.montar(linhas, as_of="01/01/2027", ultimo_mes_fechado=1)
    total = sum(sum(m) for c in dados["clients"] for m in c["tot"]["2026"])
    assert total == 0


# --------------------------------------------------------------------------
# Onde atuar (volumetria × desempenho)
# --------------------------------------------------------------------------

from painel import atuacao  # noqa: E402


def _sent(dim, chave, cliente, tipo, n, uf='', projeto=''):
    return atuacao.LinhaSentenca(dimensao=dim, chave=chave, uf=uf, cliente=cliente,
                                 tipo_id=tipo, quantidade=n, projeto=projeto)


def _acor(dim, chave, cliente, recurso, tipo, mod, n, uf='', projeto=''):
    return atuacao.LinhaAcordao(dimensao=dim, chave=chave, uf=uf, cliente=cliente,
                                recurso=recurso, tipo_id=tipo, modificada_id=mod,
                                quantidade=n, projeto=projeto)


def _proj(dim, chave, projeto, recurso, tipo, mod, n, uf=''):
    """Linha do recorte por projeto: o cliente é sempre o Santander."""
    return _acor(dim, chave, 'Santander', recurso, tipo, mod, n, uf=uf, projeto=projeto)


def test_atuacao_uf_ganha_nome_por_extenso():
    d = atuacao.montar([_sent('uf', 'PE', 'Santander', '1', 4, uf='PE')], [], '01/01/2027', 'jan/2027')
    item = d['dims']['uf']['itens'][0]
    assert item['k'] == 'PE' and item['n'] == 'Pernambuco'


def test_atuacao_comarca_carrega_a_uf():
    d = atuacao.montar([_sent('comarca', 'Recife', 'Santander', '1', 4, uf='PE')], [],
                       '01/01/2027', 'jan/2027')
    item = d['dims']['comarca']['itens'][0]
    assert item['k'] == 'Recife' and item['uf'] == 'PE'


def test_atuacao_separa_recurso_nosso_por_recorte():
    linhas = [
        _acor('uf', 'SP', 'Santander', 'representada', '2', '1', 3, uf='SP'),   # nosso, reverteu
        _acor('uf', 'SP', 'Santander', 'representada', '2', '2', 7, uf='SP'),   # nosso, manteve
        _acor('uf', 'SP', 'Santander', 'contraria', '1', '2', 5, uf='SP'),      # do adversário
    ]
    d = atuacao.montar([], linhas, '01/01/2027', 'jan/2027')
    cel = d['dims']['uf']['itens'][0]['c'][0]
    _cli, _s, tot, nos = cel
    assert nos[2] == 3 and nos[3] == 7      # DF e DD só dos recursos nossos
    assert tot[1] == 5                      # FD do adversário fica só em "tot"
    assert nos[1] == 0


def test_atuacao_cliente_desconhecido_vai_para_outros():
    d = atuacao.montar([_sent('uf', 'SP', 'Banco Ignoto', '1', 9, uf='SP')], [],
                       '01/01/2027', 'jan/2027')
    indice = d['clientes'].index('Outros')
    assert d['dims']['uf']['itens'][0]['c'][0][0] == indice


def test_atuacao_vetor_zerado_vira_zero():
    """Compactação: célula só com sentenças não carrega os vetores de acórdão."""
    d = atuacao.montar([_sent('uf', 'SP', 'Santander', '1', 2, uf='SP')], [],
                       '01/01/2027', 'jan/2027')
    _cli, s, tot, nos = d['dims']['uf']['itens'][0]['c'][0]
    assert s[0] == 2 and tot == 0 and nos == 0


def test_atuacao_ordena_itens_por_volume():
    linhas = [_sent('uf', 'SP', 'Santander', '1', 100, uf='SP'),
              _sent('uf', 'PE', 'Santander', '1', 4, uf='PE')]
    d = atuacao.montar(linhas, [], '01/01/2027', 'jan/2027')
    assert [i['k'] for i in d['dims']['uf']['itens']] == ['SP', 'PE']


# --------------------------------------------------------------------------
# Onde atuar — quebra por projeto do Santander
# --------------------------------------------------------------------------

def test_atuacao_projeto_grande_ganha_chip_e_pequeno_vai_para_outros():
    linhas = [
        _proj('uf', 'SP', 'Consignado', 'representada', '2', '1', 40, uf='SP'),
        _proj('uf', 'SP', 'Coisa Rara', 'representada', '2', '1', 3, uf='SP'),
    ]
    d = atuacao.montar([], linhas, '01/01/2027', 'jan/2027')
    assert d['projetos'] == ['Consignado', 'Outros projetos']
    assert d['clienteComProjeto'] == 'Santander'
    celulas = {c[0]: c for c in d['dims']['uf']['itens'][0]['p']}
    assert celulas[0][3][2] == 40      # Consignado, slot DF
    assert celulas[1][3][2] == 3       # o pequeno somado em "Outros projetos"


def test_atuacao_projetos_somam_a_celula_do_cliente():
    """A quebra por projeto é independente: as duas somas têm de bater."""
    linhas = [
        _acor('uf', 'SP', 'Santander', 'representada', '2', '1', 30, uf='SP'),
        _acor('uf', 'SP', 'Santander', 'representada', '2', '2', 70, uf='SP'),
        _proj('uf', 'SP', 'Consignado', 'representada', '2', '1', 12, uf='SP'),
        _proj('uf', 'SP', 'Consignado', 'representada', '2', '2', 28, uf='SP'),
        _proj('uf', 'SP', 'Revisionais', 'representada', '2', '1', 18, uf='SP'),
        _proj('uf', 'SP', 'Revisionais', 'representada', '2', '2', 42, uf='SP'),
    ]
    d = atuacao.montar([], linhas, '01/01/2027', 'jan/2027')
    item = d['dims']['uf']['itens'][0]
    indice = d['clientes'].index('Santander')
    do_cliente = next(c for c in item['c'] if c[0] == indice)
    assert [do_cliente[3][2], do_cliente[3][3]] == [30, 70]
    soma = [sum(c[3][i] for c in item['p']) for i in (2, 3)]
    assert soma == [30, 70]


def test_atuacao_ordem_dos_projetos_e_por_volume_de_acordaos():
    linhas = [
        _proj('uf', 'SP', 'Pequeno', 'representada', '2', '1', 15, uf='SP'),
        _proj('uf', 'SP', 'Grande', 'representada', '2', '1', 60, uf='SP'),
    ]
    d = atuacao.montar([], linhas, '01/01/2027', 'jan/2027')
    assert d['projetos'] == ['Grande', 'Pequeno', 'Outros projetos']


def test_atuacao_volume_do_projeto_conta_so_a_dimensao_padrao():
    """O mesmo caso reaparece em comarca e tese; se contasse tudo, o piso furava."""
    linhas = [_proj(dim, 'X', 'Repetido', 'representada', '2', '1', 4, uf='SP')
              for dim in ('uf', 'comarca', 'tese')]
    d = atuacao.montar([], linhas, '01/01/2027', 'jan/2027')
    assert d['projetos'] == ['Outros projetos']      # 4 na UF, não 12


def test_atuacao_recorte_sem_santander_nao_ganha_quebra_por_projeto():
    d = atuacao.montar([_sent('uf', 'PE', 'Gol', '1', 9, uf='PE')], [], '01/01/2027', 'jan/2027')
    assert 'p' not in d['dims']['uf']['itens'][0]


class _OdooFalso:
    """Só registra as chamadas e devolve um grupo por consulta — não toca a rede."""

    def __init__(self):
        self.chamadas = []

    def read_group(self, model, domain, fields, groupby, lazy=False):
        self.chamadas.append({"domain": list(domain), "fields": list(fields),
                              "groupby": list(groupby)})
        quebra = groupby[0]
        campo = groupby[1]
        g = {"__count": 1,
             quebra: [1, "Santander - Consignado" if quebra == "projeto_id" else "Santander"],
             campo: [9, "São Paulo" if campo == "estado_id" else "Recife"],
             "tipo_sentenca_id": [2, "Procedente"]}
        if "estado_id" in fields:
            g.setdefault("estado_id", [9, "São Paulo"])
        if "dossie_recurso" in fields:
            g["dossie_recurso"] = "representada"
            g["tipo_sentenca_modificada_id"] = [1, "Improcedente"]
        return [g]


def test_atuacao_buscar_faz_as_doze_consultas_e_marca_o_projeto():
    odoo = _OdooFalso()
    sentencas, acordaos = atuacao.buscar(odoo, "2026-01-01", "2026-09-01")

    assert len(odoo.chamadas) == 12                      # 3 dimensões × 2 quebras × 2 métricas
    assert len(sentencas) == 6 and len(acordaos) == 6

    # todo campo do groupby também vai em fields (Odoo 10 exige)
    for c in odoo.chamadas:
        assert set(c["groupby"]) <= set(c["fields"])

    # as consultas por projeto — e só elas — são restritas ao Santander
    por_projeto = [c for c in odoo.chamadas if "projeto_id" in c["groupby"]]
    por_cliente = [c for c in odoo.chamadas if "grupo_id" in c["groupby"]]
    assert len(por_projeto) == 6 and len(por_cliente) == 6
    assert all(("grupo_id", "=", 215688) in c["domain"] for c in por_projeto)
    assert all(not any(t[0] == "grupo_id" for t in c["domain"]) for c in por_cliente)

    # o prefixo "Santander - " sai do nome do projeto; a linha do cliente não tem projeto
    assert {l.projeto for l in acordaos} == {"", "Consignado"}
    assert all(l.cliente == "Santander" for l in acordaos if l.projeto)
    # a UF vira sigla, e a comarca carrega a UF junto
    ufs = {l.chave for l in acordaos if l.dimensao == "uf"}
    assert ufs == {"SP"}
    comarcas = [l for l in acordaos if l.dimensao == "comarca"]
    assert comarcas and all(l.chave == "Recife" and l.uf == "SP" for l in comarcas)


def test_atuacao_conferencia_restringe_as_duas_pontas_da_transicao():
    """Sem a restrição no resultado após o acórdão, o servidor conta a mais e o gate falha à toa."""
    class _Conta:
        def __init__(self): self.dominio = None
        def search_count(self, model, domain):
            self.dominio = list(domain)
            return 100

    linhas = [
        _acor('uf', 'SP', 'Santander', 'representada', '2', '1', 30, uf='SP'),   # DF
        _acor('uf', 'SP', 'Santander', 'representada', '2', '2', 70, uf='SP'),   # DD
        _acor('uf', 'SP', 'Santander', 'representada', '2', '5', 9, uf='SP'),    # acordo: slot X
        _proj('uf', 'SP', 'Consignado', 'representada', '2', '1', 30, uf='SP'),
        _proj('uf', 'SP', 'Consignado', 'representada', '2', '2', 70, uf='SP'),
    ]
    dados = atuacao.montar([], linhas, '01/01/2027', 'jan/2027')
    odoo = _Conta()
    checagens = atuacao.conferir(odoo, dados, '2026-01-01', '2027-01-01')

    campos = {t[0]: t[2] for t in odoo.dominio if t[0].startswith("tipo_sentenca")}
    assert set(campos["tipo_sentenca_id"]) == {2, 4, 10}                 # origem desfavorável
    assert set(campos["tipo_sentenca_modificada_id"]) == {1, 2, 3, 4, 7, 9, 10}   # destino classificável

    descricoes = {d: (json_, srv) for d, json_, srv in checagens}
    assert len(descricoes) == 2
    servidor = next(v for d, v in descricoes.items() if "por UF" in d)
    assert servidor == (100, 100)          # 30 + 70; o acordo ficou fora, como no servidor
    projetos = next(v for d, v in descricoes.items() if "projetos" in d)
    assert projetos == (100, 100)          # soma dos projetos × célula do Santander


def test_atuacao_linha_de_projeto_nao_entra_na_conta_do_cliente():
    """Senão o Santander apareceria com o dobro dos casos."""
    linhas = [_acor('uf', 'SP', 'Santander', 'representada', '2', '1', 10, uf='SP'),
              _proj('uf', 'SP', 'Consignado', 'representada', '2', '1', 10, uf='SP')]
    d = atuacao.montar([], linhas, '01/01/2027', 'jan/2027')
    item = d['dims']['uf']['itens'][0]
    indice = d['clientes'].index('Santander')
    assert sum(c[3][2] for c in item['c'] if c[0] == indice) == 10
