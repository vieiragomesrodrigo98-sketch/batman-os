"""Testes do enforcement de isolamento de tenant (Vol.VIII Cap.32/33,
Milestone 7 desta construção)."""

from __future__ import annotations

import pytest

from batman_os.foundation.tenant_isolation import (
    IsolamentoDeTenantViolado,
    exigir_tenant_correspondente,
)
from batman_os.foundation.types import TenantId


def test_tenant_correspondente_nao_levanta() -> None:
    exigir_tenant_correspondente(TenantId("t-1"), TenantId("t-1"))  # nao levanta


def test_tenant_diferente_levanta_isolamento_violado() -> None:
    with pytest.raises(IsolamentoDeTenantViolado):
        exigir_tenant_correspondente(TenantId("t-1"), TenantId("t-2"))


def test_mensagem_da_excecao_identifica_ambos_os_tenants() -> None:
    with pytest.raises(IsolamentoDeTenantViolado, match="t-1") as exc_info:
        exigir_tenant_correspondente(TenantId("t-esperado"), TenantId("t-1"))
    assert "t-esperado" in str(exc_info.value)
