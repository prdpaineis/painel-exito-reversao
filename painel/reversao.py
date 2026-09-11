# -*- coding: utf-8 -*-
"""Aba "Reversão recursal".

Reversão recursal = dos casos em que **nós** recorremos de uma sentença
desfavorável, a fração em que o acórdão mudou o resultado a nosso favor.
Recurso da parte contrária não entra nessa conta (isso é defesa, não reversão)
e aparece em bloco separado na página.

Cada caso é classificado pela transição entre a classe da sentença original
(`tipo_sentenca_id`) e a do resultado após o acórdão (`tipo_sentenca_modificada_id`):

    favorável    = Improcedente, Extinção (sem mérito ou da execução), Favorável
    desfavorável = Procedente, Parcialmente Procedente, Desfavorável

Mudança de tipo dentro da mesma classe (Parcial -> Procedente, que o MMP usa
para "condenação mantida") NÃO conta como reversão.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple

from .config import (
    APELIDOS_REVERSAO,
    CLASSE_DESFAVORAVEL,
    CLASSE_FAVORAVEL,
    CLIENTES_REVERSAO,
    MIN_ACORDAOS_PROJETO,
    RECURSO_NOSSO,
    SANTANDER_GROUP_ID,
    SEM_CLIENTE,
    SEM_PROJETO,
)
from .odoo import Odoo
from .util import (com_chave_de_ano_string, id_de, matriz, nome_curto_projeto, nome_de,
                   parse_ano_mes, soma_em)

MODELO = "dossie.dossie"

# Ordem dos slots no vetor mensal consumido pelo JavaScript da página.
# FF = manteve favorável · FD = reverteu contra · DF = reverteu a favor
# DD = manteve desfavorável · X = não classificável (acordo, nulidade, vazio)
SLOTS = ("FF", "FD", "DF", "DD", "X")
SLOT_NAO_CLASSIFICAVEL = 4


class Linha(NamedTuple):
    escopo: str          # "cliente" ou "projeto"
    nome: str
    ano: int
    mes: int             # 1-12
    recurso: str         # dossie_recurso: representada / contraria / ambos / ""
    tipo_id: str         # sentença original
    modificada_id: str   # resultado após o acórdão
    quantidade: int

    @property
    def nosso(self) -> bool:
        return self.recurso in RECURSO_NOSSO


def slot_da_transicao(tipo_id: str, modificada_id: str) -> int:
    """Índice do vetor para a transição sentença -> acórdão."""
    origem = _classe(tipo_id)
    destino = _classe(modificada_id)
    if origem is None or destino is None:
        return SLOT_NAO_CLASSIFICAVEL
    return SLOTS.index(origem + destino)


def _classe(tipo_id: str) -> str | None:
    if tipo_id in CLASSE_FAVORAVEL:
        return "F"
    if tipo_id in CLASSE_DESFAVORAVEL:
        return "D"
    return None


# --------------------------------------------------------------------------
# Extração
# --------------------------------------------------------------------------

def buscar(odoo: Odoo, data_inicio: str, data_fim: str) -> list[Linha]:
    """Duas chamadas: por cliente e por projeto do Santander.

    `dossie_recurso` entra como dimensão do agrupamento — é o que permite separar
    recurso nosso de recurso do adversário sem uma segunda consulta.
    """
    dominio = [("data_acordao", ">=", data_inicio), ("data_acordao", "<", data_fim)]
    campos_comuns = ["data_acordao", "dossie_recurso", "tipo_sentenca_id", "tipo_sentenca_modificada_id"]
    grupos_comuns = ["data_acordao:month", "dossie_recurso", "tipo_sentenca_id", "tipo_sentenca_modificada_id"]
    linhas: list[Linha] = []

    grupos = odoo.read_group(
        MODELO, dominio,
        fields=["grupo_id"] + campos_comuns,
        groupby=["grupo_id"] + grupos_comuns,
    )
    linhas += _converter(grupos, "cliente", "grupo_id", SEM_CLIENTE)

    grupos = odoo.read_group(
        MODELO, dominio + [("grupo_id", "=", SANTANDER_GROUP_ID)],
        fields=["projeto_id"] + campos_comuns,
        groupby=["projeto_id"] + grupos_comuns,
    )
    linhas += _converter(grupos, "projeto", "projeto_id", SEM_PROJETO)
    return linhas


def _converter(grupos, escopo, campo_chave, padrao) -> list[Linha]:
    saida = []
    for g in grupos:
        ano, mes = parse_ano_mes(g.get("data_acordao:month"), g.get("__domain"))
        saida.append(Linha(
            escopo=escopo,
            nome=nome_de(g.get(campo_chave), padrao),
            ano=ano,
            mes=mes,
            recurso=g.get("dossie_recurso") or "",
            tipo_id=id_de(g.get("tipo_sentenca_id")),
            modificada_id=id_de(g.get("tipo_sentenca_modificada_id")),
            quantidade=int(g.get("__count") or 0),
        ))
    return saida


# --------------------------------------------------------------------------
# Transformação (função pura — é o que os testes exercitam)
# --------------------------------------------------------------------------

def montar(linhas: Iterable[Linha], as_of: str, ultimo_mes_fechado: int,
           cobertura: list[dict] | None = None,
           anos: tuple[int, ...] = (2025, 2026)) -> dict:
    """Devolve o dicionário que vira o bloco `r-data` da página.

    `cobertura` é o bloco "quanto disto dá para auditar" (acórdãos com inteiro
    teor gravado, por ano). Vem de uma auditoria separada, não desta pipeline;
    o valor é repassado como recebido.
    """
    clientes: dict[str, dict] = {}
    projetos: dict[str, dict] = {}

    for linha in linhas:
        if linha.ano not in anos:
            continue
        destino = clientes if linha.escopo == "cliente" else projetos
        balde = destino.setdefault(linha.nome, {
            "tot": matriz(anos, len(SLOTS)),
            "nos": matriz(anos, len(SLOTS)),
        })
        slot = slot_da_transicao(linha.tipo_id, linha.modificada_id)
        balde["tot"][linha.ano][linha.mes - 1][slot] += linha.quantidade
        if linha.nosso:
            balde["nos"][linha.ano][linha.mes - 1][slot] += linha.quantidade

    ano_corrente = max(anos)

    def volume(balde) -> int:
        return sum(sum(mes) for mes in balde["tot"][ano_corrente])

    def empacotar(balde) -> dict:
        return {
            "tot": com_chave_de_ano_string(balde["tot"]),
            "nos": com_chave_de_ano_string(balde["nos"]),
        }

    def acumular(destino, origem) -> None:
        for parte in ("tot", "nos"):
            for ano in anos:
                soma_em(destino[parte][ano], origem[parte][ano])

    def balde_vazio() -> dict:
        return {"tot": matriz(anos, len(SLOTS)), "nos": matriz(anos, len(SLOTS))}

    # --- clientes ---
    saida_clientes, outros, membros = [], balde_vazio(), []
    for nome, balde in sorted(clientes.items(), key=lambda kv: -volume(kv[1])):
        if nome in CLIENTES_REVERSAO:
            saida_clientes.append({"name": APELIDOS_REVERSAO.get(nome, nome), **empacotar(balde)})
        else:
            membros.append(nome)
            acumular(outros, balde)
    saida_clientes.append({"name": "Outros", **empacotar(outros), "members": sorted(membros)})

    # --- projetos do Santander ---
    saida_projetos, outros_proj, membros_proj = [], balde_vazio(), []
    for nome, balde in sorted(projetos.items(), key=lambda kv: -volume(kv[1])):
        curto = nome_curto_projeto(nome)
        if volume(balde) >= MIN_ACORDAOS_PROJETO:
            saida_projetos.append({"name": curto, **empacotar(balde)})
        else:
            membros_proj.append(curto)
            acumular(outros_proj, balde)
    saida_projetos.append({
        "name": "Outros projetos", **empacotar(outros_proj), "members": sorted(membros_proj),
    })

    return {
        "asOf": as_of,
        "lastFullMonth": ultimo_mes_fechado,
        "clients": saida_clientes,
        "projects": saida_projetos,
        "cobertura": cobertura or [],
    }


# --------------------------------------------------------------------------
# Conferência
# --------------------------------------------------------------------------

def conferir(odoo: Odoo, dados: dict, ano: int = 2026) -> list[tuple[str, int, int]]:
    """Compara totais do JSON com `search_count` no servidor."""
    ultimo = dados["lastFullMonth"]
    fim_fechado = f"{ano}-{ultimo + 1:02d}-01" if ultimo < 12 else f"{ano + 1}-01-01"

    total_json = sum(
        sum(sum(mes) for mes in c["tot"][str(ano)]) for c in dados["clients"]
    )
    total_servidor = odoo.search_count(MODELO, [
        ("data_acordao", ">=", f"{ano}-01-01"), ("data_acordao", "<", f"{ano + 1}-01-01"),
    ])

    nossos_json = sum(
        sum(sum(c["nos"][str(ano)][m]) for m in range(ultimo)) for c in dados["clients"]
    )
    nossos_servidor = odoo.search_count(MODELO, [
        ("data_acordao", ">=", f"{ano}-01-01"), ("data_acordao", "<", fim_fechado),
        ("dossie_recurso", "in", sorted(RECURSO_NOSSO)),
    ])
    return [
        (f"acórdãos de {ano} (todos os clientes)", total_json, total_servidor),
        (f"recursos nossos jan–mês {ultimo}/{ano}", nossos_json, nossos_servidor),
    ]
