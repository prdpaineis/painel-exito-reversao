#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o painel "Êxito e Reversão" a partir do Odoo do MMP.

Uso típico (mês fechado em agosto):

    python main.py --as-of 09/09/2026 --last-full-month 8

Saída: out/painel.html (mais sentencas.json, reversao.json, atuacao.json e recursos.json).
Credenciais vêm do ambiente ou de um .env local — ver .env.example.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from painel import atuacao as mod_atuacao
from painel import recursos as mod_recursos
from painel import reversao as mod_reversao
from painel import sentencas as mod_sentencas
from painel.build import gravar, montar_pagina
from painel.config import load_config
from painel.odoo import Odoo, OdooError
from painel.util import MESES_CURTOS

RAIZ = Path(__file__).resolve().parent


def _hoje_br() -> str:
    return date.today().strftime("%d/%m/%Y")


def _mes_fechado_padrao() -> int:
    """Último mês inteiramente decorrido (em janeiro, devolve 12 do ano anterior
    — nesse caso passe --last-full-month explicitamente)."""
    hoje = date.today()
    return hoje.month - 1 if hoje.month > 1 else 12


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gera o painel Êxito e Reversão (Odoo MMP).")
    p.add_argument("--as-of", default=_hoje_br(),
                   help="data mostrada na página, dd/mm/aaaa (padrão: hoje)")
    p.add_argument("--last-full-month", type=int, default=_mes_fechado_padrao(),
                   help="último mês fechado, 1-12: gráficos e acumulados param nele")
    p.add_argument("--year", type=int, default=date.today().year,
                   help="ano corrente do painel (padrão: ano de hoje)")
    p.add_argument("--out", type=Path, default=RAIZ / "out",
                   help="diretório de saída (padrão: ./out)")
    p.add_argument("--template", type=Path, default=RAIZ / "templates" / "painel.html",
                   help="template HTML com os marcadores")
    p.add_argument("--cobertura", type=Path, default=RAIZ / "data" / "cobertura.json",
                   help="bloco de auditoria da aba de reversão (JSON)")
    p.add_argument("--env-file", type=Path, default=RAIZ / ".env",
                   help="arquivo .env a carregar (padrão: ./.env)")
    p.add_argument("--no-check", action="store_true",
                   help="não conferir os totais contra search_count no servidor")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not 1 <= args.last_full_month <= 12:
        print("--last-full-month precisa estar entre 1 e 12", file=sys.stderr)
        return 2

    ano = args.year
    anos = (ano - 1, ano)
    inicio = f"{anos[0]}-01-01"
    # o painel mostra o mês seguinte ao fechado como parcial, então buscamos um mês a mais
    fim_busca = f"{ano + 1}-01-01" if args.last_full_month >= 11 else f"{ano}-{args.last_full_month + 2:02d}-01"

    try:
        cfg = load_config(args.env_file)
        odoo = Odoo(cfg)
    except (RuntimeError, OdooError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 1

    print(f"Conectado em {cfg.url} · Odoo {odoo.version} · {odoo.whoami()}")
    print(f"Período: {inicio} até {fim_busca} (exclusivo) · mês fechado: {args.last_full_month}")

    cobertura = []
    if args.cobertura.is_file():
        cobertura = json.loads(args.cobertura.read_text(encoding="utf-8"))
    else:
        print(f"AVISO: {args.cobertura} não encontrado — a aba de reversão sai sem o bloco de auditoria.")

    fim_fechado = (f"{ano}-{args.last_full_month + 1:02d}-01"
                   if args.last_full_month < 12 else f"{ano + 1}-01-01")

    try:
        print("Buscando sentenças...", flush=True)
        linhas_s = mod_sentencas.buscar(odoo, inicio, fim_busca)
        dados_s = mod_sentencas.montar(linhas_s, args.as_of, args.last_full_month, ano)

        print("Buscando acórdãos...", flush=True)
        linhas_r = mod_reversao.buscar(odoo, inicio, fim_busca)
        dados_r = mod_reversao.montar(linhas_r, args.as_of, args.last_full_month, ano,
                                      cobertura=cobertura)

        print("Buscando o recorte por UF, comarca e tipo de ação...", flush=True)
        periodo = f"jan–{MESES_CURTOS[args.last_full_month]}/{ano}"
        linhas_as, linhas_aa = mod_atuacao.buscar(odoo, f"{ano}-01-01", fim_fechado)
        dados_a = mod_atuacao.montar(linhas_as, linhas_aa, args.as_of, periodo)

        print("Buscando quem recorreu (Recorri e ganhei / Autor recorreu e perdi)...", flush=True)
        linhas_rl = mod_recursos.buscar(odoo, f"{ano}-01-01", fim_busca)
        dados_rl = mod_recursos.montar(linhas_rl, args.as_of, fim_fechado)
    except OdooError as exc:
        print(f"ERRO na consulta: {exc}", file=sys.stderr)
        return 1

    print(f"  {len(linhas_s)} sentenças · {len(linhas_r)} acórdãos"
          f" · {len(linhas_as) + len(linhas_aa)} grupos por UF/comarca/tipo de ação"
          f" · {len(linhas_rl)} acórdãos p/ recursos")

    ok = True
    if not args.no_check:
        print("Conferindo contra o servidor:")
        for descricao, no_json, no_servidor in (
            mod_sentencas.conferir(odoo, linhas_s, inicio, fim_busca)
            + mod_reversao.conferir(odoo, linhas_r, inicio, fim_busca)
            + mod_atuacao.conferir(odoo, dados_a, f"{ano}-01-01", fim_fechado)
            + mod_recursos.conferir(odoo, linhas_rl, f"{ano}-01-01", fim_busca)
        ):
            bate = no_json == no_servidor
            ok = ok and bate
            print(f"  [{'ok' if bate else 'DIVERGE'}] {descricao}: {no_json:,} no painel"
                  f" · {no_servidor:,} no servidor".replace(",", "."))

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "sentencas.json").write_text(
        json.dumps(dados_s, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (args.out / "reversao.json").write_text(
        json.dumps(dados_r, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (args.out / "atuacao.json").write_text(
        json.dumps(dados_a, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (args.out / "recursos.json").write_text(
        json.dumps(dados_rl, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    pagina = montar_pagina(
        args.template.read_text(encoding="utf-8"), dados_s, dados_r, dados_a, dados_rl, args.as_of
    )
    destino = gravar(args.out / "painel.html", pagina)
    print(f"Página gerada: {destino} ({destino.stat().st_size // 1024} KB)")

    if not ok:
        print("Atenção: algum total não bateu com o servidor — confira antes de publicar.",
              file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
