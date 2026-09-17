# -*- coding: utf-8 -*-
"""Abas "Recorri e ganhei" e "Autor recorreu e perdi" (rl-data).

Diferente de Sentenças e Reversão, "quem recorreu" não está num campo direto do
caso — sai das tarefas do processo (`project.task.tipo_recurso_id`):

    recurso nosso  = tarefa de Apelação, Inominado ou Preparo
    recurso do autor = tarefa de Contrarrazões (só se contrarrazoa recurso alheio)

Caso com os dois: vale o sentido da sentença (contra nós → conta como recurso
nosso; a nosso favor → recurso do autor). Caso sem nenhuma dessas tarefas fica
de fora das duas abas.

    Ganhei = recurso nosso e a sentença desfavorável virou favorável (D → F)
    Perdi  = recurso do autor e a sentença favorável virou desfavorável (F → D)

A taxa usa só os acórdãos até o fim do último mês fechado; a lista de casos é
o ano corrente inteiro.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple

from .config import (
    ALIAS_CLIENTE,
    CLASSE_DESFAVORAVEL,
    CLASSE_FAVORAVEL,
    CLIENTES_PADRAO,
    RECURSO_TIPO_AUTOR,
    RECURSO_TIPO_NOSSO,
    SEM_CLIENTE,
)
from .odoo import Odoo
from .util import id_de, nome_curto_projeto, nome_de

MODELO = "dossie.dossie"
MODELO_TAREFA = "project.task"
OUTROS = "Outros"

CAMPOS = ["processo", "data_acordao", "tipo_sentenca_id", "tipo_sentenca_modificada_id",
          "grupo_id", "projeto_id", "estado_id", "comarca_id", "dossie_recurso", "agressor_contumaz"]

NOS_QUEM = {"escritorio", "ambos"}
AUT_QUEM = {"autor", "ambos"}
_ROT_AGR = {"s": "Sim", "n": "Não"}
_TAREFAS_CITAVEIS = RECURSO_TIPO_NOSSO | RECURSO_TIPO_AUTOR


class Registro(NamedTuple):
    """Um acórdão de 2026, já com a classificação de quem recorreu."""
    processo: str
    data: str              # ISO "YYYY-MM-DD"
    cliente: str
    projeto: str            # nome completo do projeto (o prefixo do cliente sai na exibição)
    uf: str
    comarca: str
    sentenca: str           # nome do tipo_sentenca_id
    resultado: str          # nome do tipo_sentenca_modificada_id
    tr: str                 # transição de 2 letras: FF / FD / DF / DD / e combinações com X
    quem: str                # escritorio / autor / ambos / sem_tarefa (pelas tarefas)
    campo: str                # dossie_recurso, ou "vazio": pra conferir contra `quem`
    tipos: tuple[str, ...]   # tarefas de recurso citadas (nosso ∪ autor)
    agressor_contumaz: str | None   # "s" / "n" / None


def _classe(tipo_id: str) -> str:
    if tipo_id in CLASSE_FAVORAVEL:
        return "F"
    if tipo_id in CLASSE_DESFAVORAVEL:
        return "D"
    return "X"


def _quem(tipos: set[str]) -> str:
    nosso = bool(tipos & RECURSO_TIPO_NOSSO)
    autor = bool(tipos & RECURSO_TIPO_AUTOR)
    if nosso and autor:
        return "ambos"
    if nosso:
        return "escritorio"
    if autor:
        return "autor"
    return "sem_tarefa"


def _nome_cliente(valor) -> str:
    nome = nome_de(valor, SEM_CLIENTE)
    return ALIAS_CLIENTE.get(nome, nome)


# --------------------------------------------------------------------------
# Extração
# --------------------------------------------------------------------------

def buscar(odoo: Odoo, data_inicio: str, data_fim: str) -> list[Registro]:
    """Duas consultas: os acórdãos do período e as tarefas de recurso desses casos."""
    dossies = odoo.search_read(
        MODELO, [("data_acordao", ">=", data_inicio), ("data_acordao", "<", data_fim)],
        ["id"] + CAMPOS,
    )
    ids = [d["id"] for d in dossies]
    tipos_por_dossie: dict[int, set[str]] = {}
    if ids:
        tarefas = odoo.search_read(
            MODELO_TAREFA,
            [("dossie_id", "in", ids), ("tipo_recurso_id", "!=", False)],
            ["dossie_id", "tipo_recurso_id"],
            page_size=2000,
        )
        for t in tarefas:
            dossie_id = id_de(t.get("dossie_id"))
            if not dossie_id:
                continue
            tipos_por_dossie.setdefault(int(dossie_id), set()).add(nome_de(t.get("tipo_recurso_id")))
    return [_registro(d, tipos_por_dossie.get(d["id"], set())) for d in dossies]


def _registro(d: dict, tipos: set[str]) -> Registro:
    tr = _classe(id_de(d.get("tipo_sentenca_id"))) + _classe(id_de(d.get("tipo_sentenca_modificada_id")))
    citados = tuple(sorted(tipos & _TAREFAS_CITAVEIS))
    return Registro(
        processo=d.get("processo") or "",
        data=d["data_acordao"],
        cliente=_nome_cliente(d.get("grupo_id")),
        projeto=nome_de(d.get("projeto_id"), ""),
        uf=nome_de(d.get("estado_id")),
        comarca=nome_de(d.get("comarca_id")),
        sentenca=nome_de(d.get("tipo_sentenca_id")),
        resultado=nome_de(d.get("tipo_sentenca_modificada_id")),
        tr=tr,
        quem=_quem(tipos),
        campo=d.get("dossie_recurso") or "vazio",
        tipos=citados,
        agressor_contumaz=d.get("agressor_contumaz") or None,
    )


# --------------------------------------------------------------------------
# Transformação (função pura — é o que os testes exercitam)
# --------------------------------------------------------------------------

def _cliente_exibido(r: Registro) -> str:
    return r.cliente if r.cliente in CLIENTES_PADRAO else OUTROS


def _campos_zerados() -> dict:
    return {f + s: 0 for f in ("lista", "num", "den") for s in ("", "_s", "_n")}


def _grupo_agressor(r: Registro) -> str | None:
    return "_" + r.agressor_contumaz if r.agressor_contumaz in ("s", "n") else None


def _secao(registros: list[Registro], recorrente: set[str], lista_tr: str,
           base_tr: tuple[str, ...], data_fim_fechado: str) -> dict:
    """`recorrente`: quem tem de ter recorrido. `lista_tr`: transição que entra na lista.
    `base_tr`: as transições do denominador da taxa (meses fechados, por isso `data_fim_fechado`)."""
    lista = [r for r in registros if r.quem in recorrente and r.tr == lista_tr]
    base = [r for r in registros if r.quem in recorrente and r.tr in base_tr and r.data < data_fim_fechado]

    por_cliente = {c: {"cli": c, **_campos_zerados()} for c in CLIENTES_PADRAO + [OUTROS]}
    for r in lista:
        e = por_cliente[_cliente_exibido(r)]
        e["lista"] += 1
        g = _grupo_agressor(r)
        if g:
            e["lista" + g] += 1
    for r in base:
        e = por_cliente[_cliente_exibido(r)]
        acertou = int(r.tr == lista_tr)
        e["den"] += 1
        e["num"] += acertou
        g = _grupo_agressor(r)
        if g:
            e["den" + g] += 1
            e["num" + g] += acertou

    com_movimento = [v for v in por_cliente.values() if v["lista"] or v["den"]]
    ordenado = (sorted((v for v in com_movimento if v["cli"] != OUTROS), key=lambda v: -v["lista"])
                + [v for v in com_movimento if v["cli"] == OUTROS])

    lista_ordenada = sorted(lista, key=lambda r: r.data, reverse=True)
    linhas = [[r.data, r.processo, _cliente_exibido(r), nome_curto_projeto(r.projeto), r.uf, r.comarca,
               r.sentenca, r.resultado, ", ".join(r.tipos), _ROT_AGR.get(r.agressor_contumaz, "—")]
              for r in lista_ordenada]
    return {"por_cliente": ordenado, "rows": linhas}


def _conferencia_quem_x_campo(registros: list[Registro]) -> dict:
    """Cruza a classificação por tarefa (`quem`) com o campo antigo `dossie_recurso`
    (`campo`) — é o texto que mostra o quanto os dois concordam, na aba."""
    conta = {}
    for r in registros:
        conta[(r.quem, r.campo)] = conta.get((r.quem, r.campo), 0) + 1
    return {
        "ambos": sum(1 for r in registros if r.quem == "ambos"),
        "semTarefa": sum(1 for r in registros if r.quem == "sem_tarefa"),
        "escRepresentada": conta.get(("escritorio", "representada"), 0),
        "escContraria": conta.get(("escritorio", "contraria"), 0),
        "autContraria": conta.get(("autor", "contraria"), 0),
        "autRepresentada": conta.get(("autor", "representada"), 0),
    }


def montar(registros: Iterable[Registro], as_of: str, data_fim_fechado: str) -> dict:
    """Devolve o dicionário que vira o bloco `rl-data` da página."""
    registros = list(registros)
    return {
        "asOf": as_of,
        "ganhei": _secao(registros, NOS_QUEM, "DF", ("DF", "DD"), data_fim_fechado),
        "perdi": _secao(registros, AUT_QUEM, "FD", ("FF", "FD"), data_fim_fechado),
        "conferencia": _conferencia_quem_x_campo(registros),
    }


# --------------------------------------------------------------------------
# Conferência
# --------------------------------------------------------------------------

def conferir(odoo: Odoo, registros: list[Registro], data_inicio: str, data_fim: str) -> list[tuple[str, int, int]]:
    """Compara o total extraído (linha a linha) com `search_count` no servidor."""
    total_servidor = odoo.search_count(MODELO, [
        ("data_acordao", ">=", data_inicio), ("data_acordao", "<", data_fim),
    ])
    return [("acórdãos extraídos p/ recursos (linha a linha)", len(registros), total_servidor)]
