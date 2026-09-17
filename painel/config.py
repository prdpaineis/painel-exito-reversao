# -*- coding: utf-8 -*-
"""Configuração e constantes do painel.

As credenciais vêm SOMENTE de variáveis de ambiente (ou de um arquivo .env local,
que não é versionado). Nada de segredo neste repositório.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------
# Credenciais
# --------------------------------------------------------------------------

ENV_VARS = ("ODOO_URL", "ODOO_DB", "ODOO_LOGIN", "ODOO_PASSWORD")


@dataclass(frozen=True)
class OdooConfig:
    url: str
    db: str
    login: str
    password: str

    def __repr__(self) -> str:  # nunca vazar a senha em log/traceback
        return f"OdooConfig(url={self.url!r}, db={self.db!r}, login={self.login!r}, password=***)"


def load_dotenv(path: Path) -> None:
    """Carrega um .env simples (KEY=valor) sem dependência externa.

    Não sobrescreve variáveis já definidas no ambiente — o ambiente vence,
    que é o comportamento esperado em CI.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def load_config(dotenv: Path | None = None) -> OdooConfig:
    """Lê a configuração do ambiente. Levanta RuntimeError se faltar algo."""
    load_dotenv(dotenv or Path(".env"))
    missing = [name for name in ENV_VARS if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Variáveis de ambiente ausentes: "
            + ", ".join(missing)
            + ". Copie .env.example para .env e preencha, ou exporte no ambiente/CI."
        )
    return OdooConfig(
        url=os.environ["ODOO_URL"].rstrip("/"),
        db=os.environ["ODOO_DB"],
        login=os.environ["ODOO_LOGIN"],
        password=os.environ["ODOO_PASSWORD"],
    )


# --------------------------------------------------------------------------
# Constantes do MMP (ids conferidos no servidor em set/2026)
# --------------------------------------------------------------------------

SANTANDER_GROUP_ID = 215688

# tipo.sentenca
TIPO_IMPROCEDENTE = "1"
TIPO_PROCEDENTE = "2"
TIPO_EXTINCAO_SEM_MERITO = "3"
TIPO_PARCIALMENTE_PROCEDENTE = "4"
TIPO_HOMOLOGACAO_ACORDO = "5"
TIPO_EXTINCAO_EXECUCAO = "7"
TIPO_FAVORAVEL = "9"
TIPO_DESFAVORAVEL = "10"

# Classes usadas na aba de reversão recursal
CLASSE_FAVORAVEL = {TIPO_IMPROCEDENTE, TIPO_EXTINCAO_SEM_MERITO, TIPO_EXTINCAO_EXECUCAO, TIPO_FAVORAVEL}
CLASSE_DESFAVORAVEL = {TIPO_PROCEDENTE, TIPO_PARCIALMENTE_PROCEDENTE, TIPO_DESFAVORAVEL}

# dossie_recurso: quais valores contam como "recurso nosso"
RECURSO_NOSSO = {"representada", "ambos"}

# project.task.tipo_recurso_id (nome do tipo): quem recorreu, usado nas abas
# "Recorri e ganhei" e "Autor recorreu e perdi". 'inomi' e 'prep' são valores
# abreviados que aparecem em lançamentos mais antigos — mantidos porque ainda
# existem casos de 2026 com esse texto no campo.
RECURSO_TIPO_NOSSO = {"Apelação", "Inominado", "Preparo", "inomi", "prep"}
RECURSO_TIPO_AUTOR = {"Contrarrazões - Apelação", "Contrarrazões - Inominado", "Contrarrazões - Adesivo"}

# O nome longo do CCB (como o Odoo devolve em grupo_id) vira este apelido em toda
# a página — Sentenças, Reversão, Onde atuar e as duas abas de recursos.
ALIAS_CLIENTE = {"Ccb Brasil - China Construction Bank": "CCB Brasil"}

# Carteira padrão (7 clientes) das abas Reversão, "Recorri e ganhei" e "Autor
# recorreu e perdi" — o resto vai para "Outros". A aba Sentenças não usa uma
# lista fixa: a carteira lá é dinâmica, por volume recente (ver sentencas.py).
CLIENTES_PADRAO = ["Santander", "Gol", "Bradesco", "Mercantil", "Cielo", "Omni", "CCB Brasil"]

# Aba "Onde atuar": lista e ordem dos clientes (a ordem define os índices no JSON).
# ATENÇÃO: aqui o CCB entra abreviado, como na aba de sentenças; a aba de reversão
# usa o nome completo. É assim que o painel está publicado — mudar altera o rótulo.
CLIENTES_ATUACAO = [
    "Santander",
    "Gol",
    "Bradesco",
    "Mercantil",
    "Cielo",
    "Ccb Brasil - China Construction Bank",
    "Omni",
]
APELIDOS_ATUACAO = {"Ccb Brasil - China Construction Bank": "CCB Brasil"}

# O Odoo devolve o nome do estado por extenso; o painel mostra a sigla.
SIGLA_UF = {
    "Acre": "AC", "Alagoas": "AL", "Amapá": "AP", "Amazonas": "AM", "Bahia": "BA",
    "Ceará": "CE", "Distrito Federal": "DF", "Espírito Santo": "ES", "Goiás": "GO",
    "Maranhão": "MA", "Mato Grosso": "MT", "Mato Grosso do Sul": "MS", "Minas Gerais": "MG",
    "Pará": "PA", "Paraíba": "PB", "Paraná": "PR", "Pernambuco": "PE", "Piauí": "PI",
    "Rio de Janeiro": "RJ", "Rio Grande do Norte": "RN", "Rio Grande do Sul": "RS",
    "Rondônia": "RO", "Roraima": "RR", "Santa Catarina": "SC", "São Paulo": "SP",
    "Sergipe": "SE", "Tocantins": "TO",
}
NOME_UF = {sigla: nome for nome, sigla in SIGLA_UF.items()}

# Sentenças e Reversão: só os N projetos do Santander com mais volume no ano
# corrente ganham linha própria; os demais somam em "Outros projetos".
TOP_PROJETOS_SENTENCAS = 13
TOP_PROJETOS_REVERSAO = 11

# Aba "Sentenças": um cliente só ganha aba/chip próprio (carteira) com pelo menos
# este número de sentenças nos últimos N meses fechados; de 1 até esse piso vira
# "Outros"; 0 nesse período = saiu da carteira (fora de todos os números).
MIN_SENTENCAS_CARTEIRA = 5
MESES_JANELA_CARTEIRA = 3

# Aba "Onde atuar": piso para um projeto ganhar chip próprio. O volume é medido no
# recorte por UF (a dimensão que a aba abre por padrão), então cada caso conta uma
# vez — nas outras dimensões o mesmo caso reaparece e inflaria a contagem.
MIN_ACORDAOS_PROJETO_ATUACAO = 10
MIN_SENTENCAS_PROJETO_ATUACAO = 50

OUTROS_PROJETOS = "Outros projetos"

# Rótulos de fallback quando o campo vem vazio
SEM_CLIENTE = "(sem cliente)"
SEM_PROJETO = "(sem projeto)"
