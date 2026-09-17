# -*- coding: utf-8 -*-
"""Aba "Sentenças" — êxito por carteira (v2).

Êxito = Improcedente + Extinção (sem mérito ou da execução). As duas aparecem
separadas na página, porque não valem o mesmo: extinção em regra deixa o autor
livre para ajuizar de novo.

Diferente da aba de Reversão e de "Onde atuar", aqui a extração é linha a linha
(`search_read`, não `read_group`): a carteira é dinâmica — um cliente só ganha
chip próprio com um piso de sentenças nos últimos meses — e isso não dá para
decidir só com um agregado do servidor.

Cada caso (`dossie.dossie`) conta uma vez, pelo mês de `data_sentenca`.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple

from .config import (
    ALIAS_CLIENTE,
    MESES_JANELA_CARTEIRA,
    MIN_SENTENCAS_CARTEIRA,
    NOME_UF,
    OUTROS_PROJETOS,
    SEM_CLIENTE,
    SEM_PROJETO,
    SIGLA_UF,
    TIPO_EXTINCAO_EXECUCAO,
    TIPO_EXTINCAO_SEM_MERITO,
    TIPO_HOMOLOGACAO_ACORDO,
    TIPO_IMPROCEDENTE,
    TIPO_PARCIALMENTE_PROCEDENTE,
    TIPO_PROCEDENTE,
    TOP_PROJETOS_SENTENCAS,
)
from .odoo import Odoo
from .util import (chave_ano_mes, com_chave_de_ano_string, id_de, matriz, mes_curto,
                   nome_curto_projeto, nome_de, soma_em, ultimos_meses_fechados)

MODELO = "dossie.dossie"

CAMPOS = ["data_sentenca", "tipo_sentenca_id", "grupo_id", "projeto_id", "estado_id",
          "comarca_id", "has_advogado_adverso_agressor", "agressor_contumaz"]

# Ordem dos slots no vetor mensal consumido pelo JavaScript da página.
SLOTS = ("improcedente", "extincao", "parcial", "procedente", "acordo", "sem_tipo",
         "extincao_adv_agressor", "extincao_agressor_contumaz")
SLOT_SEM_TIPO = 5
SLOT_EXTINCAO = 1
TIPO_PARA_SLOT = {
    TIPO_IMPROCEDENTE: 0,
    TIPO_EXTINCAO_SEM_MERITO: 1,
    TIPO_EXTINCAO_EXECUCAO: 1,
    TIPO_PARCIALMENTE_PROCEDENTE: 2,
    TIPO_PROCEDENTE: 3,
    TIPO_HOMOLOGACAO_ACORDO: 4,
}
# Índices do vetor de 7 posições gravado em `geo` (pula o "sem tipo": lá só entram
# sentenças classificáveis).
_SLOTS_GEO = (0, 1, 2, 3, 4, 6, 7)


class Registro(NamedTuple):
    """Um caso com sentença — a unidade que a extração devolve, um por linha."""
    cliente: str
    projeto: str          # só quando cliente == "Santander"; "" nos demais
    ano: int
    mes: int              # 1-12
    tipo_id: str           # id de tipo.sentenca, "" quando não informado
    agressor: bool         # has_advogado_adverso_agressor
    contumaz: bool         # agressor_contumaz == "s"
    uf_sigla: str          # "??" quando não informado
    comarca: str


# --------------------------------------------------------------------------
# Extração
# --------------------------------------------------------------------------

def buscar(odoo: Odoo, data_inicio: str, data_fim: str) -> list[Registro]:
    dominio = [("data_sentenca", ">=", data_inicio), ("data_sentenca", "<", data_fim)]
    return [_registro(r) for r in odoo.search_read(MODELO, dominio, CAMPOS)]


def _registro(r: dict) -> Registro:
    ano, mes = _ano_mes(r["data_sentenca"])
    cliente = _nome_cliente(r.get("grupo_id"))
    projeto = nome_curto_projeto(nome_de(r.get("projeto_id"), SEM_PROJETO)) if cliente == "Santander" else ""
    return Registro(
        cliente=cliente,
        projeto=projeto,
        ano=ano,
        mes=mes,
        tipo_id=id_de(r.get("tipo_sentenca_id")),
        agressor=bool(r.get("has_advogado_adverso_agressor")),
        contumaz=r.get("agressor_contumaz") == "s",
        uf_sigla=_uf_sigla(r.get("estado_id")),
        comarca=nome_de(r.get("comarca_id"), "(sem comarca)"),
    )


def _nome_cliente(valor) -> str:
    nome = nome_de(valor, SEM_CLIENTE)
    return ALIAS_CLIENTE.get(nome, nome)


def _uf_sigla(valor) -> str:
    nome = nome_de(valor)
    return SIGLA_UF.get(nome, nome) if nome else "??"


def _ano_mes(data_iso: str) -> tuple[int, int]:
    return int(data_iso[:4]), int(data_iso[5:7])


# --------------------------------------------------------------------------
# Transformação (função pura — é o que os testes exercitam)
# --------------------------------------------------------------------------

def _vetor(r: Registro) -> tuple[list[int], int]:
    v = [0] * len(SLOTS)
    slot = TIPO_PARA_SLOT.get(r.tipo_id, SLOT_SEM_TIPO)
    v[slot] = 1
    if slot == SLOT_EXTINCAO:
        if r.agressor:
            v[6] = 1
        if r.contumaz:
            v[7] = 1
    return v, slot


def _soma_no_mes(balde: dict, ano: int, mes: int, vetor: list[int]) -> None:
    linha = balde[ano][mes - 1]
    for i, v in enumerate(vetor):
        linha[i] += v


def montar(registros: Iterable[Registro], as_of: str, ultimo_mes_fechado: int, ano: int) -> dict:
    """Devolve o dicionário que vira o bloco `e-data` da página."""
    anos = (ano - 1, ano)
    n = len(SLOTS)
    janela = ultimos_meses_fechados(ano, ultimo_mes_fechado, MESES_JANELA_CARTEIRA)
    inicio_ano = chave_ano_mes(ano, 1)

    registros = list(registros)

    # 1) carteira: quem tem chip próprio, quem vira "Outros" e quem saiu
    primeiro: dict[str, str] = {}
    ultimo: dict[str, str] = {}
    na_janela: dict[str, int] = {}
    volume_ano: dict[str, int] = {}
    for r in registros:
        chave = chave_ano_mes(r.ano, r.mes)
        primeiro[r.cliente] = min(primeiro.get(r.cliente, chave), chave)
        ultimo[r.cliente] = max(ultimo.get(r.cliente, chave), chave)
        if chave in janela:
            na_janela[r.cliente] = na_janela.get(r.cliente, 0) + 1
        if r.ano == ano:
            volume_ano[r.cliente] = volume_ano.get(r.cliente, 0) + 1

    ativos = sorted(
        (c for c in primeiro if c != SEM_CLIENTE and na_janela.get(c, 0) >= MIN_SENTENCAS_CARTEIRA),
        key=lambda c: -volume_ano.get(c, 0),
    )
    outros_nomes = sorted(
        c for c in primeiro
        if (1 <= na_janela.get(c, 0) < MIN_SENTENCAS_CARTEIRA)
        or (c == SEM_CLIENTE and na_janela.get(c, 0) >= 1)
    )
    sairam = sorted((c for c in primeiro if na_janela.get(c, 0) == 0), key=lambda c: ultimo[c], reverse=True)
    novos = [c for c in ativos + outros_nomes if primeiro[c] >= inicio_ano]

    rotulo: dict[str, str] = {c: c for c in ativos}
    rotulo.update({c: "Outros" for c in outros_nomes})

    # 2) vetores mensais por cliente, por projeto do Santander e por UF/comarca
    clientes: dict[str, dict] = {}
    projetos: dict[str, dict] = {}
    geo: dict[tuple[str, str, str], list[int]] = {}

    for r in registros:
        if r.ano not in anos:
            continue
        lab = rotulo.get(r.cliente)
        if lab is None:      # cliente que saiu da carteira: fora de todos os números
            continue
        vetor, slot = _vetor(r)
        _soma_no_mes(clientes.setdefault(lab, matriz(anos, n)), r.ano, r.mes, vetor)
        if lab == "Santander" and r.projeto:
            _soma_no_mes(projetos.setdefault(r.projeto, matriz(anos, n)), r.ano, r.mes, vetor)
        if r.ano == ano and r.mes <= ultimo_mes_fechado and slot <= 4:
            gv = geo.setdefault((lab, r.uf_sigla, r.comarca), [0] * 7)
            for i, idx in enumerate(_SLOTS_GEO):
                gv[i] += vetor[idx]

    # 3) empacotamento
    cli_list = ativos + (["Outros"] if outros_nomes else [])
    clients_out = [
        {"name": k, "y": com_chave_de_ano_string(clientes[k]),
         **({"members": outros_nomes} if k == "Outros" else {})}
        for k in cli_list if k in clientes
    ]
    sairam_out = [{"name": c, "ultimo": mes_curto(ultimo[c])} for c in sairam]
    novos_out = [{"name": c, "desde": mes_curto(primeiro[c])} for c in novos]

    def volume_projeto(nome: str) -> int:
        # soma os 12 meses do ano corrente (os que ainda não chegaram ficam zerados);
        # inclui o mês parcial em curso, igual ao volume mostrado na aba.
        return sum(sum(mes[:5]) for mes in projetos[nome][ano])

    proj_top = sorted(projetos, key=lambda k: -volume_projeto(k))[:TOP_PROJETOS_SENTENCAS]
    projects_out = _empacotar(projetos, proj_top, OUTROS_PROJETOS, anos, n)

    cli_index = {nome: i for i, nome in enumerate(cli_list)}
    ufs: dict[str, str] = {}
    coms: list[list[str]] = []
    com_idx: dict[tuple[str, str], int] = {}
    rows: list[list] = []
    for (lab, sigla, comarca), vetor in geo.items():
        ufs.setdefault(sigla, "Sem UF" if sigla == "??" else NOME_UF.get(sigla, sigla))
        chave_com = (comarca, sigla)
        if chave_com not in com_idx:
            com_idx[chave_com] = len(coms)
            coms.append([comarca, sigla])
        rows.append([cli_index[lab], com_idx[chave_com], *vetor])

    return {
        "asOf": as_of,
        "ano": ano,
        "lastFullMonth": ultimo_mes_fechado,
        "clients": clients_out,
        "sairam": sairam_out,
        "novos": novos_out,
        "projects": projects_out,
        "geo": {"cli": cli_list, "ufs": ufs, "com": coms, "rows": rows},
    }


def _empacotar(store: dict, nomes_top: list[str], rotulo_outros: str,
               anos: tuple[int, ...], n: int) -> list[dict]:
    """Os nomes em `nomes_top` ganham linha própria; o resto soma em `rotulo_outros`."""
    saida = [{"name": k, "y": com_chave_de_ano_string(store[k])} for k in nomes_top if k in store]
    resto = [k for k in store if k not in nomes_top]
    if resto:
        agregado = matriz(anos, n)
        for k in resto:
            for ano_ in anos:
                soma_em(agregado[ano_], store[k][ano_])
        saida.append({"name": rotulo_outros, "y": com_chave_de_ano_string(agregado), "members": sorted(resto)})
    return saida


# --------------------------------------------------------------------------
# Conferência
# --------------------------------------------------------------------------

def conferir(odoo: Odoo, registros: list[Registro], data_inicio: str, data_fim: str) -> list[tuple[str, int, int]]:
    """Compara o total extraído (linha a linha) com `search_count` no servidor.

    Não confere a carteira nem o `geo` — esses dependem de classificação que não
    tem equivalente direto em `search_count`. O que este gate protege é o mais
    provável de quebrar numa reescrita para `search_read`: domínio errado,
    paginação incompleta, `active_test` diferente do esperado.
    """
    total_servidor = odoo.search_count(MODELO, [
        ("data_sentenca", ">=", data_inicio), ("data_sentenca", "<", data_fim),
    ])
    return [("sentenças extraídas (linha a linha)", len(registros), total_servidor)]
