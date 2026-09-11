# -*- coding: utf-8 -*-
"""Utilitários compartilhados pelas duas abas do painel."""
from __future__ import annotations

import re
from typing import Any

MESES_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
_DATA_ISO = re.compile(r"(\d{4})-(\d{2})-\d{2}")


def parse_ano_mes(rotulo: Any, dominio: Any = None) -> tuple[int, int]:
    """Converte o rótulo de um agrupamento `campo:month` em (ano, mês).

    O Odoo devolve algo como "January 2026", traduzido conforme o idioma do
    usuário. Tentamos inglês, depois português; se nada casar, extraímos a data
    do `__domain` do próprio grupo, que é independente de idioma.
    """
    if isinstance(rotulo, str):
        partes = rotulo.replace("/", " ").split()
        if len(partes) == 2:
            nome, ano = partes[0].strip().lower(), partes[1]
            mes = MESES_EN.get(nome) or MESES_PT.get(nome)
            if mes and ano.isdigit():
                return int(ano), mes

    for termo in dominio or []:
        if isinstance(termo, (list, tuple)) and len(termo) == 3 and isinstance(termo[2], str):
            achou = _DATA_ISO.match(termo[2])
            if achou:
                return int(achou.group(1)), int(achou.group(2))

    raise ValueError(f"Não consegui interpretar o mês do agrupamento: {rotulo!r}")


def id_de(valor: Any) -> str:
    """Odoo devolve many2one como [id, nome]; aqui só o id, como string."""
    return str(valor[0]) if isinstance(valor, (list, tuple)) and valor else ""


def nome_de(valor: Any, padrao: str = "") -> str:
    """Nome de um many2one, ou `padrao` quando o campo está vazio."""
    if isinstance(valor, (list, tuple)) and len(valor) > 1:
        return valor[1] or padrao
    return padrao


def nome_curto_projeto(nome: str, cliente: str = "Santander") -> str:
    """"Santander - Consignado" -> "Consignado".

    O `projeto_id` do MMP repete o nome do cliente em todo projeto; como a tabela
    de projetos já é de um cliente só, o prefixo só ocupa espaço na página.
    """
    prefixo = f"{cliente} - "
    return nome[len(prefixo):] if nome.startswith(prefixo) else nome


def matriz(anos: tuple[int, ...], slots: int) -> dict[int, list[list[int]]]:
    """Estrutura zerada: ano -> 12 meses -> vetor de `slots` contagens."""
    return {ano: [[0] * slots for _ in range(12)] for ano in anos}


def soma_em(destino: list[list[int]], origem: list[list[int]]) -> None:
    for mes in range(12):
        for slot in range(len(origem[mes])):
            destino[mes][slot] += origem[mes][slot]


def com_chave_de_ano_string(por_ano: dict[int, list[list[int]]]) -> dict[str, list[list[int]]]:
    """O JSON do painel usa o ano como string ("2025"/"2026")."""
    return {str(ano): valores for ano, valores in sorted(por_ano.items())}
