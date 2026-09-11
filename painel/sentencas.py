# -*- coding: utf-8 -*-
"""Aba "Sentenças" — êxito por carteira.

Êxito = Improcedente + Extinção (sem mérito ou da execução).
Taxa   = êxito ÷ sentenças com tipo informado (a homologação de acordo entra no
         denominador; "sem tipo" fica de fora e aparece em coluna própria).

Cada caso (`dossie.dossie`) conta uma vez, pelo mês de `data_sentenca`.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple

from .config import (
    APELIDOS_SENTENCAS,
    CLIENTES_SENTENCAS,
    MIN_SENTENCAS_PROJETO,
    SANTANDER_GROUP_ID,
    SEM_CLIENTE,
    SEM_PROJETO,
    TIPO_EXTINCAO_EXECUCAO,
    TIPO_EXTINCAO_SEM_MERITO,
    TIPO_HOMOLOGACAO_ACORDO,
    TIPO_IMPROCEDENTE,
    TIPO_PARCIALMENTE_PROCEDENTE,
    TIPO_PROCEDENTE,
)
from .odoo import Odoo
from .util import (com_chave_de_ano_string, id_de, matriz, nome_curto_projeto, nome_de,
                   parse_ano_mes, soma_em)

MODELO = "dossie.dossie"

# Ordem dos slots no vetor mensal consumido pelo JavaScript da página.
SLOTS = ("improcedente", "extincao", "parcial", "procedente", "acordo", "sem_tipo")
SLOT_SEM_TIPO = 5
TIPO_PARA_SLOT = {
    TIPO_IMPROCEDENTE: 0,
    TIPO_EXTINCAO_SEM_MERITO: 1,
    TIPO_EXTINCAO_EXECUCAO: 1,
    TIPO_PARCIALMENTE_PROCEDENTE: 2,
    TIPO_PROCEDENTE: 3,
    TIPO_HOMOLOGACAO_ACORDO: 4,
}


class Linha(NamedTuple):
    """Uma célula do agrupamento: quantos casos de um tipo, num mês, num recorte."""
    escopo: str          # "cliente" ou "projeto"
    nome: str
    ano: int
    mes: int             # 1-12
    tipo_id: str         # id de tipo.sentenca, "" quando não informado
    quantidade: int


# --------------------------------------------------------------------------
# Extração
# --------------------------------------------------------------------------

def buscar(odoo: Odoo, data_inicio: str, data_fim: str) -> list[Linha]:
    """Duas chamadas ao servidor: por cliente e por projeto do Santander."""
    dominio = [("data_sentenca", ">=", data_inicio), ("data_sentenca", "<", data_fim)]
    linhas: list[Linha] = []

    grupos = odoo.read_group(
        MODELO, dominio,
        fields=["grupo_id", "data_sentenca", "tipo_sentenca_id"],
        groupby=["grupo_id", "data_sentenca:month", "tipo_sentenca_id"],
    )
    linhas += _converter(grupos, "cliente", "grupo_id", "data_sentenca:month", SEM_CLIENTE)

    grupos = odoo.read_group(
        MODELO, dominio + [("grupo_id", "=", SANTANDER_GROUP_ID)],
        fields=["projeto_id", "data_sentenca", "tipo_sentenca_id"],
        groupby=["projeto_id", "data_sentenca:month", "tipo_sentenca_id"],
    )
    linhas += _converter(grupos, "projeto", "projeto_id", "data_sentenca:month", SEM_PROJETO)
    return linhas


def _converter(grupos, escopo, campo_chave, campo_mes, padrao) -> list[Linha]:
    saida = []
    for g in grupos:
        ano, mes = parse_ano_mes(g.get(campo_mes), g.get("__domain"))
        saida.append(Linha(
            escopo=escopo,
            nome=nome_de(g.get(campo_chave), padrao),
            ano=ano,
            mes=mes,
            tipo_id=id_de(g.get("tipo_sentenca_id")),
            quantidade=int(g.get("__count") or 0),
        ))
    return saida


# --------------------------------------------------------------------------
# Transformação (função pura — é o que os testes exercitam)
# --------------------------------------------------------------------------

def montar(linhas: Iterable[Linha], as_of: str, ultimo_mes_fechado: int,
           anos: tuple[int, ...] = (2025, 2026)) -> dict:
    """Devolve o dicionário que vira o bloco `e-data` da página."""
    clientes: dict[str, dict] = {}
    projetos: dict[str, dict] = {}

    for linha in linhas:
        if linha.ano not in anos:
            continue
        destino = clientes if linha.escopo == "cliente" else projetos
        balde = destino.setdefault(linha.nome, matriz(anos, len(SLOTS)))
        slot = TIPO_PARA_SLOT.get(linha.tipo_id, SLOT_SEM_TIPO)
        balde[linha.ano][linha.mes - 1][slot] += linha.quantidade

    ano_corrente = max(anos)

    def volume(balde) -> int:
        return sum(sum(mes) for mes in balde[ano_corrente])

    # --- clientes: nomes fixos na frente, o resto somado em "Outros" ---
    saida_clientes, outros, membros = [], matriz(anos, len(SLOTS)), []
    for nome, balde in sorted(clientes.items(), key=lambda kv: -volume(kv[1])):
        if nome in CLIENTES_SENTENCAS:
            saida_clientes.append({
                "name": APELIDOS_SENTENCAS.get(nome, nome),
                "y": com_chave_de_ano_string(balde),
            })
        else:
            membros.append(nome)
            for ano in anos:
                soma_em(outros[ano], balde[ano])
    saida_clientes.append({
        "name": "Outros",
        "y": com_chave_de_ano_string(outros),
        "members": sorted(membros),
    })

    # --- projetos do Santander: linha própria só acima do piso de volume ---
    saida_projetos, outros_proj = [], matriz(anos, len(SLOTS))
    for nome, balde in sorted(projetos.items(), key=lambda kv: -volume(kv[1])):
        curto = nome_curto_projeto(nome)
        if volume(balde) >= MIN_SENTENCAS_PROJETO:
            saida_projetos.append({"name": curto, "y": com_chave_de_ano_string(balde)})
        else:
            for ano in anos:
                soma_em(outros_proj[ano], balde[ano])
    saida_projetos.append({"name": "Outros projetos", "y": com_chave_de_ano_string(outros_proj)})

    return {
        "asOf": as_of,
        "lastFullMonth": ultimo_mes_fechado,
        "clients": saida_clientes,
        "projects": saida_projetos,
    }


# --------------------------------------------------------------------------
# Conferência
# --------------------------------------------------------------------------

def conferir(odoo: Odoo, dados: dict, ano: int = 2026) -> list[tuple[str, int, int]]:
    """Compara totais do JSON com `search_count` no servidor.

    Devolve uma lista de (descrição, valor_no_json, valor_no_servidor).
    """
    total_json = sum(
        sum(sum(mes) for mes in cliente["y"][str(ano)]) for cliente in dados["clients"]
    )
    total_servidor = odoo.search_count(MODELO, [
        ("data_sentenca", ">=", f"{ano}-01-01"), ("data_sentenca", "<", f"{ano + 1}-01-01"),
    ])
    santander = next((c for c in dados["clients"] if c["name"] == "Santander"), None)
    improc_json = sum(mes[0] for mes in santander["y"][str(ano)]) if santander else 0
    improc_servidor = odoo.search_count(MODELO, [
        ("grupo_id", "=", SANTANDER_GROUP_ID),
        ("data_sentenca", ">=", f"{ano}-01-01"), ("data_sentenca", "<", f"{ano + 1}-01-01"),
        ("tipo_sentenca_id", "=", int(TIPO_IMPROCEDENTE)),
    ])
    return [
        (f"sentenças de {ano} (todos os clientes)", total_json, total_servidor),
        (f"improcedentes do Santander em {ano}", improc_json, improc_servidor),
    ]
