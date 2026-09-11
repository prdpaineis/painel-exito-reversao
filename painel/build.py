# -*- coding: utf-8 -*-
"""Injeta os dados no template e grava a página final."""
from __future__ import annotations

import json
from pathlib import Path

PLACEHOLDER_SENTENCAS = "__EDATA__"
PLACEHOLDER_REVERSAO = "__RDATA__"
PLACEHOLDER_ATUACAO = "__ADATA__"
PLACEHOLDER_DATA = "__ASOF__"


def _json_para_html(dados: dict) -> str:
    """JSON compacto, seguro para ir dentro de <script type="application/json">.

    A única sequência que fecharia a tag é `</`; escapamos para `<\\/`, que o
    JSON.parse do navegador lê de volta como `</`.
    """
    return json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def montar_pagina(template: str, sentencas: dict, reversao: dict, atuacao: dict, as_of: str) -> str:
    faltando = [p for p in (PLACEHOLDER_SENTENCAS, PLACEHOLDER_REVERSAO,
                            PLACEHOLDER_ATUACAO, PLACEHOLDER_DATA)
                if p not in template]
    if faltando:
        raise ValueError(
            "O template não tem os marcadores esperados: " + ", ".join(faltando)
            + ". Veja o README (seção 'Como o template funciona')."
        )
    pagina = template.replace(PLACEHOLDER_DATA, as_of)
    pagina = pagina.replace(PLACEHOLDER_SENTENCAS, _json_para_html(sentencas), 1)
    pagina = pagina.replace(PLACEHOLDER_REVERSAO, _json_para_html(reversao), 1)
    pagina = pagina.replace(PLACEHOLDER_ATUACAO, _json_para_html(atuacao), 1)
    return pagina


def gravar(caminho: Path, conteudo: str) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho
