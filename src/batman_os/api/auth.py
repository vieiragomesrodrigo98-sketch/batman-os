"""Autenticação real da API (Fase 8 do roadmap de plataforma, `.claude/
plans/peaceful-wondering-hearth.md`, Estágio 8.1).

Antes desta fase, `tenant_id` era um campo explícito no corpo/query da
requisição — seleção livre, nunca prova de identidade (achado de
investigação: `foundation/tenant_isolation.py::exigir_tenant_
correspondente()` só compara dois valores já em mãos, nunca verifica
credencial nenhuma). A spec de 10 volumes é sistemicamente silenciosa
sobre autenticação de borda (zero menção a API key/JWT/OAuth/Bearer em
qualquer capítulo/ADR) — espaço de design livre.

Mecanismo escolhido: 1 API key estática por tenant, enviada via
`Authorization: Bearer <chave>` (`fastapi.security.HTTPBearer`, já
disponível sem dependência nova — confirmado por import real contra o
FastAPI instalado). Hashing de chave em repouso fica para quando houver
deploy real (hoje o batman-os é 100% local/desenvolvimento, mesmo
tratamento do `ANTHROPIC_API_KEY` em texto puro no `.env`,
`.gitignore`d) — proporcional ao resto do projeto, não uma lacuna
esquecida.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from batman_os.foundation.types import TenantId

_esquema_bearer = HTTPBearer(auto_error=False)


class ApiKeyStore:
    """Constrói a partir do formato de autoria natural (tenant→chave) e
    inverte para lookup por chave (o sentido em que a autenticação
    precisa resolver: dada uma chave recebida, qual tenant ela prova)."""

    def __init__(self, chaves_por_tenant: Mapping[str, str]) -> None:
        self._tenant_por_chave: dict[str, TenantId] = {
            chave: TenantId(tenant) for tenant, chave in chaves_por_tenant.items()
        }

    def resolver(self, chave: str) -> TenantId | None:
        return self._tenant_por_chave.get(chave)

    @classmethod
    def carregar(
        cls, env: Mapping[str, str] | None = None, dotenv_path: str | Path | None = None
    ) -> ApiKeyStore:
        """Mesmo padrão de `llm/settings.py::Settings.carregar()`: `env`
        explícito (testes) nunca toca o `.env` real; `env` omitido lê
        `BATMAN_API_KEYS` de `.env`/variável de ambiente real via
        `load_dotenv()`. Formato: JSON `{"tenant": "chave", ...}`.
        Variável ausente ou vazia -> store vazio (zero chaves válidas,
        nunca um default inseguro implícito). JSON malformado -> erro
        claro na inicialização, nunca silenciado."""
        if env is None:
            load_dotenv(dotenv_path=dotenv_path)
        fonte = env if env is not None else os.environ
        bruto = fonte.get("BATMAN_API_KEYS", "").strip()
        if not bruto:
            return cls({})
        try:
            chaves_por_tenant = json.loads(bruto)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "BATMAN_API_KEYS deve ser um objeto JSON tenant->chave, "
                f'ex.: {{"local": "..."}}. Recebido inválido: {exc}'
            ) from exc
        if not isinstance(chaves_por_tenant, dict):
            raise ValueError(
                "BATMAN_API_KEYS deve ser um objeto JSON tenant->chave, "
                f"não {type(chaves_por_tenant).__name__}"
            )
        return cls(chaves_por_tenant)


def obter_chave_store(request: Request) -> ApiKeyStore:
    chave_store: ApiKeyStore = request.app.state.chave_store
    return chave_store


ApiKeyStoreDep = Annotated[ApiKeyStore, Depends(obter_chave_store)]


def autenticar_tenant(
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Security(_esquema_bearer)],
    chave_store: ApiKeyStoreDep,
) -> TenantId:
    """Dependency de borda: toda rota que precisa de um `tenant_id`
    confiável declara `tenant_id: TenantAutenticadoDep` em vez de ler um
    campo de corpo/query não verificado. `401` (não `403`) em qualquer
    falha — "não autenticado", nunca "autenticado mas proibido", e
    sempre com `WWW-Authenticate: Bearer` (convenção HTTP para indicar
    QUAL esquema o cliente deveria usar)."""
    if credenciais is not None:
        tenant_id = chave_store.resolver(credenciais.credentials)
        if tenant_id is not None:
            return tenant_id
    raise HTTPException(
        status_code=401,
        detail="Credenciais invalidas ou ausentes",
        headers={"WWW-Authenticate": "Bearer"},
    )


TenantAutenticadoDep = Annotated[TenantId, Depends(autenticar_tenant)]
