# -*- coding: utf-8 -*-
"""Cliente XML-RPC mínimo para o Odoo do MMP.

O servidor é Odoo 10 rodando em Python 2.7. Dois cuidados que já custaram tempo:

* `execute_kw(db, uid, pw, model, method, args, kwargs)` — `args[0]` é o domínio,
  **sem envelope extra**. Errar isso devolve um traceback de Python 2 apontando
  para módulos customizados, e não uma mensagem de "domínio inválido".
* `limit=0` significa *sem limite* neste servidor. Nunca passe zero em tabela grande.

Este módulo é somente leitura: expõe apenas `search_count` e `read_group`.
"""
from __future__ import annotations

import xmlrpc.client
from typing import Any, Iterable, Sequence

from .config import OdooConfig

# Força os rótulos de mês em inglês nos agrupamentos por :month.
# (O parser tem fallback pelo __domain, mas com o lang fixo o caminho feliz
# não depende do idioma do usuário que roda o script.)
BASE_CONTEXT = {"lang": "en_US", "active_test": False}


class OdooError(RuntimeError):
    pass


class Odoo:
    """Conexão autenticada, somente leitura."""

    def __init__(self, cfg: OdooConfig, timeout: int = 600) -> None:
        self._cfg = cfg
        self._common = xmlrpc.client.ServerProxy(f"{cfg.url}/xmlrpc/2/common", allow_none=True)
        self._models = xmlrpc.client.ServerProxy(f"{cfg.url}/xmlrpc/2/object", allow_none=True)
        try:
            self.version = self._common.version().get("server_version", "?")
            uid = self._common.authenticate(cfg.db, cfg.login, cfg.password, {})
        except Exception as exc:  # rede, TLS, host errado...
            raise OdooError(f"Não foi possível falar com {cfg.url}: {exc}") from exc
        if not uid:
            raise OdooError(
                "Autenticação recusada (uid vazio). Confira ODOO_DB, ODOO_LOGIN e ODOO_PASSWORD."
            )
        self.uid: int = uid

    # -- chamada crua ------------------------------------------------------
    def execute_kw(self, model: str, method: str, args: Sequence[Any], **kwargs: Any) -> Any:
        try:
            return self._models.execute_kw(
                self._cfg.db, self.uid, self._cfg.password, model, method, list(args), kwargs
            )
        except xmlrpc.client.Fault as fault:
            raise OdooError(f"{model}.{method} falhou: {fault.faultString.strip()[-500:]}") from fault

    # -- leituras ----------------------------------------------------------
    def search_count(self, model: str, domain: Iterable[Any]) -> int:
        return self.execute_kw(model, "search_count", [list(domain)], context=dict(BASE_CONTEXT))

    def read_group(
        self,
        model: str,
        domain: Iterable[Any],
        fields: Sequence[str],
        groupby: Sequence[str],
        lazy: bool = False,
    ) -> list[dict]:
        """`read_group` com o contexto padrão.

        Em Odoo 10 todo campo usado em `groupby` precisa aparecer também em
        `fields` (inclusive o de data que recebe o sufixo `:month`).
        """
        return self.execute_kw(
            model,
            "read_group",
            [list(domain), list(fields), list(groupby)],
            lazy=lazy,
            context=dict(BASE_CONTEXT),
        )

    def search_read(
        self, model: str, domain: Iterable[Any], fields: Sequence[str],
        order: str = "id", page_size: int = 1000,
    ) -> list[dict]:
        """Lê registro a registro, paginado.

        Usado onde `read_group` não chega: classificação por caso (carteira ativa/
        saiu, tarefas de recurso relacionadas) precisa do registro, não do agregado.
        """
        registros: list[dict] = []
        offset = 0
        while True:
            lote = self.execute_kw(
                model, "search_read", [list(domain)],
                fields=list(fields), limit=page_size, offset=offset, order=order,
                context=dict(BASE_CONTEXT),
            )
            registros += lote
            offset += len(lote)
            if len(lote) < page_size:
                break
        return registros

    def whoami(self) -> str:
        rec = self.execute_kw("res.users", "read", [[self.uid]], fields=["name", "login"])
        return f"{rec[0]['name']} ({rec[0]['login']}, uid {self.uid})"
