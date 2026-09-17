# -*- coding: utf-8 -*-
"""Injeta os dados no template e grava a página final."""
from __future__ import annotations

import json
from pathlib import Path

from .config import MESES_JANELA_CARTEIRA
from .util import MESES_CURTOS, MESES_LONGOS

PLACEHOLDER_SENTENCAS = "__EDATA__"
PLACEHOLDER_REVERSAO = "__RDATA__"
PLACEHOLDER_ATUACAO = "__ADATA__"
PLACEHOLDER_RECURSOS = "__RLDATA__"
PLACEHOLDER_DATA = "__ASOF__"

PLACEHOLDERS_JSON = (PLACEHOLDER_SENTENCAS, PLACEHOLDER_REVERSAO, PLACEHOLDER_ATUACAO, PLACEHOLDER_RECURSOS)

# O template também cita, em prosa (fora do JSON), alguns números e períodos que
# mudam a cada rodada — o texto explica o método e cita o dado ao mesmo tempo, então
# não dá pra deixar tudo a cargo do JS sem duplicar a agregação lá. Cada marcador
# abaixo é resolvido uma vez aqui, a partir dos dicionários já montados.
PLACEHOLDER_ANO = "__ANO__"
PLACEHOLDER_ANO_ANT = "__ANO_ANT__"
PLACEHOLDER_PERIODO = "__PERIODO__"                # "jan–ago/2026"
PLACEHOLDER_PERIODO_CURTO = "__PERIODO_CURTO__"    # "jan–ago", sem ano
PLACEHOLDER_PERIODO_TH = "__PERIODO_TH__"          # "jan–ago 2026" (cabeçalho de tabela)
PLACEHOLDER_PERIODO_TH_ANT = "__PERIODO_TH_ANT__"  # "jan–ago 2025"
PLACEHOLDER_MES_PARCIAL = "__MES_PARCIAL__"                # "set"
PLACEHOLDER_MES_PARCIAL_LONGO_CAP = "__MES_PARCIAL_LONGO_CAP__"  # "Setembro"
PLACEHOLDER_MES_FECHADO_LONGO = "__MES_FECHADO_LONGO__"    # "agosto"
PLACEHOLDER_JANELA_CARTEIRA = "__JANELA_CARTEIRA__"        # "jun–ago/2026"

PLACEHOLDER_SENT_EXT_AGR = "__AGR__"
PLACEHOLDER_SENT_EXT_TOTAL = "__EXT__"
PLACEHOLDER_SENT_EXT_CONTUMAZ = "__CONT__"
PLACEHOLDER_REV_FF_EXT = "__FFEXT__"
PLACEHOLDER_REV_FF_EXT_IMPROC = "__FFEXTIMPROC__"

PLACEHOLDER_RL_AMBOS = "__AMBOS__"
PLACEHOLDER_RL_SEM = "__SEM__"
PLACEHOLDER_RL_ESC_REP = "__ESCREP__"
PLACEHOLDER_RL_ESC_CON = "__ESCCON__"
PLACEHOLDER_RL_AUT_CON = "__AUTCON__"
PLACEHOLDER_RL_AUT_REP = "__AUTREP__"


def _br(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _json_para_html(dados: dict) -> str:
    """JSON compacto, seguro para ir dentro de <script type="application/json">.

    A única sequência que fecharia a tag é `</`; escapamos para `<\\/`, que o
    JSON.parse do navegador lê de volta como `</`.
    """
    return json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _resumo_extincoes(sentencas: dict) -> tuple[int, int, int]:
    """(extinções, com advogado agressor, com agressor/contumaz) no período fechado."""
    ano = str(sentencas["ano"])
    ate = sentencas["lastFullMonth"]
    ext = agr = cont = 0
    for cliente in sentencas["clients"]:
        for mes in cliente["y"][ano][:ate]:
            ext += mes[1]
            agr += mes[6]
            cont += mes[7]
    return ext, agr, cont


def _textos_de_periodo(ano: int, ultimo_mes_fechado: int) -> dict[str, str]:
    mes_parcial = ultimo_mes_fechado % 12 + 1     # o mês seguinte ao fechado, com dados parciais
    inicio_janela = ultimo_mes_fechado - MESES_JANELA_CARTEIRA + 1
    return {
        PLACEHOLDER_ANO: str(ano),
        PLACEHOLDER_ANO_ANT: str(ano - 1),
        PLACEHOLDER_PERIODO: f"jan–{MESES_CURTOS[ultimo_mes_fechado]}/{ano}",
        PLACEHOLDER_PERIODO_CURTO: f"jan–{MESES_CURTOS[ultimo_mes_fechado]}",
        PLACEHOLDER_PERIODO_TH: f"jan–{MESES_CURTOS[ultimo_mes_fechado]} {ano}",
        PLACEHOLDER_PERIODO_TH_ANT: f"jan–{MESES_CURTOS[ultimo_mes_fechado]} {ano - 1}",
        PLACEHOLDER_MES_PARCIAL: MESES_CURTOS[mes_parcial],
        PLACEHOLDER_MES_PARCIAL_LONGO_CAP: MESES_LONGOS[mes_parcial].capitalize(),
        PLACEHOLDER_MES_FECHADO_LONGO: MESES_LONGOS[ultimo_mes_fechado],
        PLACEHOLDER_JANELA_CARTEIRA: f"{MESES_CURTOS[inicio_janela]}–{MESES_CURTOS[ultimo_mes_fechado]}/{ano}",
    }


def montar_pagina(template: str, sentencas: dict, reversao: dict, atuacao: dict,
                   recursos: dict, as_of: str) -> str:
    faltando = [p for p in PLACEHOLDERS_JSON + (PLACEHOLDER_DATA,) if p not in template]
    if faltando:
        raise ValueError(
            "O template não tem os marcadores esperados: " + ", ".join(faltando)
            + ". Veja o README (seção 'Como o template funciona')."
        )

    ext, agr, cont = _resumo_extincoes(sentencas)
    nota_ext = reversao.get("nota_ext", {})
    conf = recursos.get("conferencia", {})

    pagina = template.replace(PLACEHOLDER_DATA, as_of)
    pagina = pagina.replace(PLACEHOLDER_SENTENCAS, _json_para_html(sentencas), 1)
    pagina = pagina.replace(PLACEHOLDER_REVERSAO, _json_para_html(reversao), 1)
    pagina = pagina.replace(PLACEHOLDER_ATUACAO, _json_para_html(atuacao), 1)
    pagina = pagina.replace(PLACEHOLDER_RECURSOS, _json_para_html(recursos), 1)

    for marcador, valor in _textos_de_periodo(sentencas["ano"], sentencas["lastFullMonth"]).items():
        pagina = pagina.replace(marcador, valor)

    pagina = pagina.replace(PLACEHOLDER_SENT_EXT_TOTAL, _br(ext))
    pagina = pagina.replace(PLACEHOLDER_SENT_EXT_AGR, _br(agr))
    pagina = pagina.replace(PLACEHOLDER_SENT_EXT_CONTUMAZ, _br(cont))
    pagina = pagina.replace(PLACEHOLDER_REV_FF_EXT, _br(nota_ext.get("ff_ext", 0)))
    pagina = pagina.replace(PLACEHOLDER_REV_FF_EXT_IMPROC, _br(nota_ext.get("ff_ext_como_improc", 0)))

    pagina = pagina.replace(PLACEHOLDER_RL_AMBOS, _br(conf.get("ambos", 0)))
    pagina = pagina.replace(PLACEHOLDER_RL_SEM, _br(conf.get("semTarefa", 0)))
    pagina = pagina.replace(PLACEHOLDER_RL_ESC_REP, _br(conf.get("escRepresentada", 0)))
    pagina = pagina.replace(PLACEHOLDER_RL_ESC_CON, _br(conf.get("escContraria", 0)))
    pagina = pagina.replace(PLACEHOLDER_RL_AUT_CON, _br(conf.get("autContraria", 0)))
    aut_rep = conf.get("autRepresentada", 0)
    pagina = pagina.replace(PLACEHOLDER_RL_AUT_REP, "nenhum" if aut_rep == 0 else _br(aut_rep))
    return pagina


def gravar(caminho: Path, conteudo: str) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho
