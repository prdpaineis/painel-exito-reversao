# -*- coding: utf-8 -*-
"""Aba "Onde atuar" — volumetria cruzada com desempenho.

A pergunta que esta aba responde: *dado que a taxa está baixa em vários lugares,
por onde começar?* Taxa baixa num recorte de 4 casos é ruído; a mesma taxa num
recorte de 400 casos é o problema real. A ordenação é por **casos a ganhar**:

    potencial = (taxa dos demais recortes − taxa deste recorte) × volume deste recorte

O benchmark é sempre o *restante* do mesmo corte, nunca a média que inclui o
próprio recorte — sem isso São Paulo, que sozinho é quase metade do volume,
seria comparado consigo mesmo e nunca apareceria como oportunidade.

Diferente das outras duas abas, aqui não há recorte mensal: o período fechado
inteiro entra numa conta só, para dar volume às células menores.

Cada recorte vem quebrado por cliente (`c`) e, no Santander, também por projeto
do caso (`p`) — as duas quebras são independentes e a soma dos projetos reproduz
exatamente a célula do Santander.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple

from .config import (
    APELIDOS_ATUACAO,
    CLASSE_DESFAVORAVEL,
    CLASSE_FAVORAVEL,
    CLIENTES_ATUACAO,
    MIN_ACORDAOS_PROJETO_ATUACAO,
    MIN_SENTENCAS_PROJETO_ATUACAO,
    OUTROS_PROJETOS,
    RECURSO_NOSSO,
    SANTANDER_GROUP_ID,
    SEM_CLIENTE,
    SEM_PROJETO,
    SIGLA_UF,
    TIPO_EXTINCAO_EXECUCAO,
    TIPO_EXTINCAO_SEM_MERITO,
    TIPO_HOMOLOGACAO_ACORDO,
    TIPO_IMPROCEDENTE,
    TIPO_PARCIALMENTE_PROCEDENTE,
    TIPO_PROCEDENTE,
)
from .odoo import Odoo
from .util import id_de, nome_curto_projeto, nome_de

MODELO = "dossie.dossie"

# Dimensões oferecidas na aba: chave interna -> (campo do Odoo, rótulo na página)
DIMENSOES = {
    "uf": ("estado_id", "UF"),
    "comarca": ("comarca_id", "Comarca"),
    "tese": ("tipo_acao_id", "Tipo de ação"),
}
DIMENSAO_PADRAO = "uf"      # é nela que o volume dos projetos é medido

# vetor de sentenças, igual ao da aba de sentenças
SLOT_SENTENCA = {
    TIPO_IMPROCEDENTE: 0,
    TIPO_EXTINCAO_SEM_MERITO: 1,
    TIPO_EXTINCAO_EXECUCAO: 1,
    TIPO_PARCIALMENTE_PROCEDENTE: 2,
    TIPO_PROCEDENTE: 3,
    TIPO_HOMOLOGACAO_ACORDO: 4,
}
SLOT_SEM_TIPO = 5
# vetor de acórdãos, igual ao da aba de reversão
SLOTS_REVERSAO = ("FF", "FD", "DF", "DD", "X")
SLOT_NAO_CLASSIFICAVEL = 4
SLOT_DF = SLOTS_REVERSAO.index("DF")    # reverteu a nosso favor
SLOT_DD = SLOTS_REVERSAO.index("DD")    # manteve a condenação

CLIENTES = [APELIDOS_ATUACAO.get(c, c) for c in CLIENTES_ATUACAO] + ["Outros"]
CLIENTE_COM_PROJETO = "Santander"


class LinhaSentenca(NamedTuple):
    dimensao: str
    chave: str
    uf: str
    cliente: str
    tipo_id: str
    quantidade: int
    projeto: str = ""      # só nas linhas do recorte por projeto do Santander


class LinhaAcordao(NamedTuple):
    dimensao: str
    chave: str
    uf: str
    cliente: str
    recurso: str
    tipo_id: str
    modificada_id: str
    quantidade: int
    projeto: str = ""      # idem

    @property
    def nosso(self) -> bool:
        return self.recurso in RECURSO_NOSSO


def _slot_transicao(tipo_id: str, modificada_id: str) -> int:
    origem = "F" if tipo_id in CLASSE_FAVORAVEL else ("D" if tipo_id in CLASSE_DESFAVORAVEL else None)
    destino = "F" if modificada_id in CLASSE_FAVORAVEL else ("D" if modificada_id in CLASSE_DESFAVORAVEL else None)
    if origem is None or destino is None:
        return SLOT_NAO_CLASSIFICAVEL
    return SLOTS_REVERSAO.index(origem + destino)


def _indice_cliente(nome: str) -> int:
    nome = APELIDOS_ATUACAO.get(nome or SEM_CLIENTE, nome or SEM_CLIENTE)
    return CLIENTES.index(nome) if nome in CLIENTES else CLIENTES.index("Outros")


# --------------------------------------------------------------------------
# Extração — duas consultas por dimensão (cliente) mais duas por dimensão
# (projeto do Santander). Doze read_groups no total.
# --------------------------------------------------------------------------

def buscar(odoo: Odoo, data_inicio: str, data_fim: str) -> tuple[list[LinhaSentenca], list[LinhaAcordao]]:
    sentencas: list[LinhaSentenca] = []
    acordaos: list[LinhaAcordao] = []

    dom_s = [("data_sentenca", ">=", data_inicio), ("data_sentenca", "<", data_fim)]
    dom_a = [("data_acordao", ">=", data_inicio), ("data_acordao", "<", data_fim)]
    so_santander = [("grupo_id", "=", SANTANDER_GROUP_ID)]

    for dim, (campo, _rotulo) in DIMENSOES.items():
        # a comarca leva a UF junto para permitir filtrar comarcas de um estado
        extra = ["estado_id"] if dim == "comarca" else []

        def recorte(g, quebra, padrao):
            """Os campos que todo grupo devolve, já normalizados."""
            chave = nome_de(g.get(campo))
            return chave, {
                "dimensao": dim,
                "chave": _sigla(chave) if dim == "uf" else chave,
                "uf": _sigla(nome_de(g.get("estado_id"))) if dim == "comarca"
                     else (_sigla(chave) if dim == "uf" else ""),
                "cliente": nome_de(g.get("grupo_id"), SEM_CLIENTE) if quebra == "grupo_id" else CLIENTE_COM_PROJETO,
                "projeto": "" if quebra == "grupo_id"
                           else nome_curto_projeto(nome_de(g.get(quebra), padrao), CLIENTE_COM_PROJETO),
                "quantidade": int(g.get("__count") or 0),
            }

        for quebra, dominio_extra, padrao in (("grupo_id", [], SEM_CLIENTE),
                                              ("projeto_id", so_santander, SEM_PROJETO)):
            campos = [quebra, campo] + extra + ["tipo_sentenca_id"]
            for g in odoo.read_group(MODELO, dom_s + dominio_extra, fields=campos, groupby=campos):
                chave, base = recorte(g, quebra, padrao)
                if not chave:
                    continue
                sentencas.append(LinhaSentenca(tipo_id=id_de(g.get("tipo_sentenca_id")), **base))

            campos = ([quebra, campo] + extra
                      + ["dossie_recurso", "tipo_sentenca_id", "tipo_sentenca_modificada_id"])
            for g in odoo.read_group(MODELO, dom_a + dominio_extra, fields=campos, groupby=campos):
                chave, base = recorte(g, quebra, padrao)
                if not chave:
                    continue
                acordaos.append(LinhaAcordao(
                    recurso=g.get("dossie_recurso") or "",
                    tipo_id=id_de(g.get("tipo_sentenca_id")),
                    modificada_id=id_de(g.get("tipo_sentenca_modificada_id")),
                    **base,
                ))

    return sentencas, acordaos


def _sigla(nome_estado: str) -> str:
    return SIGLA_UF.get(nome_estado, nome_estado)


# --------------------------------------------------------------------------
# Transformação (função pura)
# --------------------------------------------------------------------------

def _nova_celula() -> dict:
    return {"s": [0] * 6, "t": [0] * 5, "n": [0] * 5}


def _somar(alvo: dict, linha) -> None:
    """Acrescenta uma linha (sentença ou acórdão) à célula."""
    if isinstance(linha, LinhaSentenca):
        alvo["s"][SLOT_SENTENCA.get(linha.tipo_id, SLOT_SEM_TIPO)] += linha.quantidade
        return
    slot = _slot_transicao(linha.tipo_id, linha.modificada_id)
    alvo["t"][slot] += linha.quantidade
    if linha.nosso:
        alvo["n"][slot] += linha.quantidade


def _lista_de_projetos(volume_acordaos: dict[str, int], volume_sentencas: dict[str, int]) -> list[str]:
    """Projetos com chip próprio, do maior para o menor; o resto vira "Outros projetos".

    O piso existe porque um projeto de três acórdãos não sustenta comparação
    nenhuma — e, somado aos demais pequenos, ainda fecha o total do Santander.
    """
    nomes = [n for n in set(volume_acordaos) | set(volume_sentencas)
             if volume_acordaos.get(n, 0) >= MIN_ACORDAOS_PROJETO_ATUACAO
             or volume_sentencas.get(n, 0) >= MIN_SENTENCAS_PROJETO_ATUACAO]
    nomes.sort(key=lambda n: (-volume_acordaos.get(n, 0), -volume_sentencas.get(n, 0), n))
    return nomes + [OUTROS_PROJETOS]


def montar(sentencas: Iterable[LinhaSentenca], acordaos: Iterable[LinhaAcordao],
           as_of: str, periodo: str) -> dict:
    """Devolve o dicionário que vira o bloco `a-data` da página."""
    sentencas, acordaos = list(sentencas), list(acordaos)

    # 1) que projetos merecem chip próprio — medido só na dimensão padrão,
    #    onde cada caso aparece uma única vez
    vol_a: dict[str, int] = {}
    vol_s: dict[str, int] = {}
    for linha in acordaos:
        if linha.projeto and linha.dimensao == DIMENSAO_PADRAO:
            vol_a[linha.projeto] = vol_a.get(linha.projeto, 0) + linha.quantidade
    for linha in sentencas:
        if linha.projeto and linha.dimensao == DIMENSAO_PADRAO:
            vol_s[linha.projeto] = vol_s.get(linha.projeto, 0) + linha.quantidade
    projetos = _lista_de_projetos(vol_a, vol_s)
    indice_projeto = {nome: i for i, nome in enumerate(projetos)}
    fora = indice_projeto[OUTROS_PROJETOS]

    # 2) celulas[dim][(chave, uf)][indice] = célula, uma estrutura por quebra
    por_cliente: dict = {}
    por_projeto: dict = {}

    def balde(destino, linha, indice):
        chaves = destino.setdefault(linha.dimensao, {}).setdefault((linha.chave, linha.uf), {})
        return chaves.setdefault(indice, _nova_celula())

    for linha in list(sentencas) + list(acordaos):
        if linha.projeto:
            _somar(balde(por_projeto, linha, indice_projeto.get(linha.projeto, fora)), linha)
        else:
            _somar(balde(por_cliente, linha, _indice_cliente(linha.cliente)), linha)

    def compacta(vetor):
        """0 no lugar do vetor todo-zero — corta ~40% do JSON embutido."""
        return vetor if any(vetor) else 0

    def celulas(por_indice: dict) -> list[list]:
        return [[i, compacta(v["s"]), compacta(v["t"]), compacta(v["n"])]
                for i, v in sorted(por_indice.items())
                if any(v["s"]) or any(v["t"])]

    dims = {}
    for dim, (_campo, rotulo) in DIMENSOES.items():
        do_cliente = por_cliente.get(dim, {})
        do_projeto = por_projeto.get(dim, {})
        # a união: um recorte que só apareceu na consulta por projeto ainda entra,
        # em vez de sumir sem aviso
        chaves = list(do_cliente) + [k for k in do_projeto if k not in do_cliente]

        itens = []
        for (chave, uf) in chaves:
            cels = celulas(do_cliente.get((chave, uf), {}))
            cels_projeto = celulas(do_projeto.get((chave, uf), {}))
            if not cels and not cels_projeto:
                continue
            item = {"k": chave, "c": cels}
            if cels_projeto:
                item["p"] = cels_projeto
            if dim == "uf":
                item["n"] = NOME_UF.get(chave, chave)
            elif uf:
                item["uf"] = uf
            itens.append(item)

        def volume(item):
            cels = item["c"] or item.get("p", [])
            return sum(sum(c[1] or [0]) + sum(c[2] or [0]) for c in cels)

        dims[dim] = {"label": rotulo, "itens": sorted(itens, key=volume, reverse=True)}

    return {
        "asOf": as_of,
        "periodo": periodo,
        "clientes": CLIENTES,
        "projetos": projetos,
        "clienteComProjeto": CLIENTE_COM_PROJETO,
        "dims": dims,
    }


NOME_UF = {sigla: nome for nome, sigla in SIGLA_UF.items()}


# --------------------------------------------------------------------------
# Conferência
# --------------------------------------------------------------------------

def _soma_recursos_nossos(itens: Iterable[dict], campo: str) -> int:
    """Denominador da reversão (DF + DD) somado sobre os recortes."""
    total = 0
    for item in itens:
        for celula in item.get(campo, []):
            nossos = celula[3]
            if nossos:
                total += nossos[SLOT_DF] + nossos[SLOT_DD]
    return total


def conferir(odoo: Odoo, dados: dict, data_inicio: str, data_fim: str) -> list[tuple[str, int, int]]:
    """Dois totais que têm de fechar: contra o servidor, e projetos contra cliente."""
    itens = dados["dims"][DIMENSAO_PADRAO]["itens"]

    # O painel só conta a transição quando as duas pontas são classificáveis: a
    # sentença de origem é desfavorável E o resultado após o acórdão também caiu
    # numa das duas classes. Homologação de acordo e campo vazio ficam no slot X,
    # fora da conta — então o search_count precisa das mesmas duas restrições,
    # senão diverge por alguns casos e derruba o gate à toa.
    desfavoraveis = sorted(int(t) for t in CLASSE_DESFAVORAVEL)
    classificaveis = sorted(int(t) for t in (CLASSE_FAVORAVEL | CLASSE_DESFAVORAVEL))
    nossos_servidor = odoo.search_count(MODELO, [
        ("data_acordao", ">=", data_inicio), ("data_acordao", "<", data_fim),
        ("dossie_recurso", "in", sorted(RECURSO_NOSSO)),
        ("tipo_sentenca_id", "in", desfavoraveis),
        ("tipo_sentenca_modificada_id", "in", classificaveis),
    ])

    indice_santander = CLIENTES.index(CLIENTE_COM_PROJETO)
    santander = 0
    for item in itens:
        for celula in item.get("c", []):
            if celula[0] == indice_santander and celula[3]:
                santander += celula[3][SLOT_DF] + celula[3][SLOT_DD]

    return [
        ("recursos nossos com sentença desfavorável (por UF)",
         _soma_recursos_nossos(itens, "c"), nossos_servidor),
        (f"recursos nossos do {CLIENTE_COM_PROJETO}: soma dos projetos × total do cliente",
         _soma_recursos_nossos(itens, "p"), santander),
    ]
