#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Roda main.py com --as-of e --last-full-month calculados automaticamente."""
import subprocess
import sys
from datetime import date

hoje = date.today()
as_of = hoje.strftime("%d/%m/%Y")
last_full = hoje.month - 1 if hoje.month > 1 else 12

print(f"Rodando para {as_of} · mês fechado: {last_full}")
resultado = subprocess.run(
    [sys.executable, "main.py", "--as-of", as_of, "--last-full-month", str(last_full)],
    check=False,
)
sys.exit(resultado.returncode)
