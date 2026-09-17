# -*- coding: utf-8 -*-
"""Aba "Reversão recursal" (v2).

Reversão recursal = dos casos em que **nós** recorremos de uma sentença
desfavorável, a fração em que o acórdão mudou o resultado a nosso favor.
Recurso da parte contrária não entra nessa conta (isso é defesa, não reversão).

Cada caso é classificado pela transição entre a classe da sentença original
(`tipo_sentenca_id`) e a do resultado após o acórdão (`tipo_sentenca_modificada_id`):

    favorável    = Improcedente, Extinção (sem mérito ou da execução), Favorável
    desfavorável = Procedente, Parcialmente Procedente, Desfavorável

Mudança de tipo dentro da mesma classe (Parcial -> Procedente, que o MMP usa
para "condenação mantida") NÃO conta como reversão.

Como em Sentenças, a extração é linha a linha (`search_read`): o vetor mensal
de 13 posições separa, dentro de FF (vitória mantida) e DF (reversão a favor),
o resultado por improcedência × extinção e a marca de advogado agressor /
agressor-contumaz — informação que só está no registro, não num agregado.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple

from .config import (
    ALIAS_CLIENTE,
    CLASSE_DESFAVORAVEL,
    CLASSE_FAVORAVEL,
    CLIENTES_PADRAO,
    OUTROS_PROJETOS,
    RECURSO_NOSSO,
    SEM_CLIENTE,
    SEM_PROJETO,
    TIPO_EXTINCAO_EXECUCAO,
    TIPO_EXTINCAO_SEM_MERITO,
    TIPO_IMPROCEDENTE,
    TOP_PROJETOS_REVERSAO,
)
from .odoo import Odoo
from .util import com_chave_de_ano_string, id_de, matriz, nome_curto_projeto, nome_de, soma_em

MODELO = "dossie.dossie"
OUTROS = "Outros"

CAMPOS = ["data_acordao", "tipo_sentenca_id", "tipo_sentenca_modificada_id", "grupo_id",
          "projeto_id", "dossie_recurso", "has_advogado_adverso_agressor", "agressor_contumaz"]

# Ordem dos slots no vetor mensal consumido pelo JavaScript da página.
# 0-4  : FF (manteve favorável) · FD (reverteu contra) · DF (reverteu a favor) ·
#        DD (manteve desfavorável) · X (não classificável)
# 5-8  : dentro de DF e de FF, o resultado por improcedência × extinção
# 9-12 : dentro dessas extinções, quantas têm advogado agressor / agressor-contumaz
SLOTS = ("FF", "FD", "DF", "DD", "X",
         "DF_improc", "DF_ext", "FF_improc", "FF_ext",
         "DF_ext_adv_agressor", "FF_ext_adv_agressor", "DF_ext_contumaz", "FF_ext_contumaz")
SLOT_NAO_CLASSIFICAVEL = 4
_IDX_TRANSICAO = {("F", "F"): 0, ("F", "D"): 1, ("D", "F"): 2, ("D", "D"): 3}
_TIPOS_EXTINCAO = {TIPO_EXTINCAO_SEM_MERITO, TIPO_EXTINCAO_EXECUCAO}


class Registro(NamedTuple):
    """Um acórdão — a unidade que a extração devolve, um por linha."""
    cliente: str
    projeto: str          # só quando cliente == "Santander"; "" nos demais
    ano: int
    mes: int              # 1-12
    recurso: str          # dossie_recurso: representada / contraria / ambos / ""
    tipo_id: str           # sentença original
    modificada_id: str    # resultado após o acórdão
    agressor: bool         # has_advogado_adverso_agressor
    contumaz: bool         # agressor_contumaz == "s"

    @property
    def nosso(self) -> bool:
        return self.recurso in RECURSO_NOSSO


def _classe(tipo_id: str) -> str:
    if tipo_id in CLASSE_FAVORAVEL:
        return "F"
    if tipo_id in CLASSE_DESFAVORAVEL:
        return "D"
    return "X"


def slot_da_transicao(tipo_id: str, modificada_id: str) -> int:
    """Índice do vetor (0-3) para a transição sentença -> acórdão, ou 4 se não classificável."""
    return _IDX_TRANSICAO.get((_classe(tipo_id), _classe(modificada_id)), SLOT_NAO_CLASSIFICAVEL)


# --------------------------------------------------------------------------
# Extração
# --------------------------------------------------------------------------

def buscar(odoo: Odoo, data_inicio: str, data_fim: str) -> list[Registro]:
    dominio = [("data_acordao", ">=", data_inicio), ("data_acordao", "<", data_fim)]
    return [_registro(r) for r in odoo.search_read(MODELO, dominio, CAMPOS)]


def _registro(r: dict) -> Registro:
    ano, mes = int(r["data_acordao"][:4]), int(r["data_acordao"][5:7])
    cliente = _nome_cliente(r.get("grupo_id"))
    projeto = nome_curto_projeto(nome_de(r.get("projeto_id"), SEM_PROJETO)) if cliente == "Santander" else ""
    return Registro(
        cliente=cliente,
        projeto=projeto,
        ano=ano,
        mes=mes,
        recurso=r.get("dossie_recurso") or "",
        tipo_id=id_de(r.get("tipo_sentenca_id")),
        modificada_id=id_de(r.get("tipo_sentenca_modificada_id")),
        agressor=bool(r.get("has_advogado_adverso_agressor")),
        contumaz=r.get("agressor_contumaz") == "s",
    )


def _nome_cliente(valor) -> str:
    nome = nome_de(valor, SEM_CLIENTE)
    return ALIAS_CLIENTE.get(nome, nome)


# --------------------------------------------------------------------------
# Transformação (função pura — é o que os testes exercitam)
# --------------------------------------------------------------------------

def _vetor(r: Registro) -> tuple[list[int], int]:
    v = [0] * len(SLOTS)
    origem, destino = _classe(r.tipo_id), _classe(r.modificada_id)
    slot = _IDX_TRANSICAO.get((origem, destino), SLOT_NAO_CLASSIFICAVEL)
    v[slot] = 1
    if (origem, destino) == ("D", "F"):
        if r.modificada_id == TIPO_IMPROCEDENTE:
            v[5] = 1
        if r.modificada_id in _TIPOS_EXTINCAO:
            v[6] = 1
            v[9] = int(r.agressor)
            v[11] = int(r.contumaz)
    elif (origem, destino) == ("F", "F"):
        # vitória mantida: só dá para separar improcedência x extinção pelo tipo da
        # SENTENÇA mantida — o resultado gravado após o acórdão tende a registrar
        # "Improcedente" mesmo quando a extinção foi o que foi mantido.
        if r.tipo_id == TIPO_IMPROCEDENTE:
            v[7] = 1
        if r.tipo_id in _TIPOS_EXTINCAO:
            v[8] = 1
            v[10] = int(r.agressor)
            v[12] = int(r.contumaz)
    return v, slot


def _soma_no_mes(balde: dict, ano: int, mes: int, vetor: list[int]) -> None:
    linha = balde[ano][mes - 1]
    for i, v in enumerate(vetor):
        linha[i] += v


def montar(registros: Iterable[Registro], as_of: str, ultimo_mes_fechado: int, ano: int,
           cobertura: list[dict] | None = None) -> dict:
    """Devolve o dicionário que vira o bloco `r-data` da página.

    `cobertura` é o bloco "quanto disto dá para auditar" (acórdãos com inteiro
    teor gravado, por ano). Vem de uma auditoria separada, não desta pipeline;
    o valor é repassado como recebido.
    """
    anos = (ano - 1, ano)
    n = len(SLOTS)
    registros = list(registros)

    clientes: dict[str, dict] = {}
    projetos: dict[str, dict] = {}
    nota_ext = {"ff_ext": 0, "ff_ext_como_improc": 0}

    def balde_vazio() -> dict:
        return {"tot": matriz(anos, n), "nos": matriz(anos, n)}

    for r in registros:
        if r.ano not in anos:
            continue
        vetor, slot = _vetor(r)
        alvos = [clientes.setdefault(r.cliente, balde_vazio())]
        if r.cliente == "Santander" and r.projeto:
            alvos.append(projetos.setdefault(r.projeto, balde_vazio()))
        for balde in alvos:
            _soma_no_mes(balde["tot"], r.ano, r.mes, vetor)
            if r.nosso:
                _soma_no_mes(balde["nos"], r.ano, r.mes, vetor)

        if r.ano == ano and r.mes <= ultimo_mes_fechado and slot == 0 and r.tipo_id in _TIPOS_EXTINCAO:
            nota_ext["ff_ext"] += 1
            if r.modificada_id == TIPO_IMPROCEDENTE:
                nota_ext["ff_ext_como_improc"] += 1

    saida_clientes = _empacotar(clientes, CLIENTES_PADRAO, OUTROS, anos, n)

    def volume_projeto(nome: str) -> int:
        return sum(sum(mes[:5]) for mes in projetos[nome]["tot"][ano])

    proj_top = sorted(projetos, key=lambda k: -volume_projeto(k))[:TOP_PROJETOS_REVERSAO]
    saida_projetos = _empacotar(projetos, proj_top, OUTROS_PROJETOS, anos, n)

    return {
        "asOf": as_of,
        "lastFullMonth": ultimo_mes_fechado,
        "clients": saida_clientes,
        "projects": saida_projetos,
        "cobertura": cobertura or [],
        "nota_ext": nota_ext,
    }


def _empacotar(store: dict, nomes_top: list[str], rotulo_outros: str,
               anos: tuple[int, ...], n: int) -> list[dict]:
    saida = [
        {"name": k, "tot": com_chave_de_ano_string(store[k]["tot"]), "nos": com_chave_de_ano_string(store[k]["nos"])}
        for k in nomes_top if k in store
    ]
    resto = [k for k in store if k not in nomes_top]
    if resto:
        agregado = {"tot": matriz(anos, n), "nos": matriz(anos, n)}
        for k in resto:
            for parte in ("tot", "nos"):
                for ano_ in anos:
                    soma_em(agregado[parte][ano_], store[k][parte][ano_])
        saida.append({
            "name": rotulo_outros,
            "tot": com_chave_de_ano_string(agregado["tot"]),
            "nos": com_chave_de_ano_string(agregado["nos"]),
            "members": sorted(resto),
        })
    return saida


# --------------------------------------------------------------------------
# Conferência
# --------------------------------------------------------------------------

def conferir(odoo: Odoo, registros: list[Registro], data_inicio: str, data_fim: str) -> list[tuple[str, int, int]]:
    """Compara o total extraído (linha a linha) com `search_count` no servidor."""
    total_servidor = odoo.search_count(MODELO, [
        ("data_acordao", ">=", data_inicio), ("data_acordao", "<", data_fim),
    ])
    return [("acórdãos extraídos (linha a linha)", len(registros), total_servidor)]
