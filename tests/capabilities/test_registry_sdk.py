"""Testes do SDK de registro de Capabilities (`registry_sdk.py`)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from batman_os.capabilities.capability_contract import CapabilityImplementation
from batman_os.capabilities.registry_sdk import (
    TipoDuplicado,
    limpar_registry,
    registrar,
    registry,
)
from batman_os.foundation.types import CapabilityId
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects


@pytest.fixture(autouse=True)
def _registry_limpo() -> Iterator[None]:
    limpar_registry()
    yield
    limpar_registry()


def _fake_implementacao() -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("fake-capability"),
        name="fake",
        version="1.0.0",
        deterministic=True,
        side_effects=SideEffects.NONE,
    )
    return CapabilityImplementation(definition=definicao, handler=lambda entrada, ctx: entrada)


def _fake_construir_implementacao() -> CapabilityImplementation:
    return _fake_implementacao()


def _fake_carregar_especificacoes() -> list[dict[str, Any]]:
    return [{"regra": "r", "descoberta": {"tipo": "x"}}]


def _fake_entradas_para_regra(root: Path, regra: Any, descoberta: dict[str, Any]) -> list[Any]:
    return [f"entrada-para-{regra}"]


class TestRegistrar:
    def test_registrar_populariza_o_registry(self) -> None:
        registrar(
            tipo="fake",
            regra_cls=str,
            construir_implementacao=_fake_construir_implementacao,
            carregar_especificacoes=_fake_carregar_especificacoes,
            entradas_para_regra=_fake_entradas_para_regra,
        )

        plugins = registry()
        assert set(plugins) == {"fake"}
        assert plugins["fake"].construir_implementacao().definition.id == "fake-capability"
        assert plugins["fake"].carregar_especificacoes() == [
            {"regra": "r", "descoberta": {"tipo": "x"}}
        ]
        entradas = plugins["fake"].entradas_para_regra(Path("."), "regra-x", {})
        assert entradas == ["entrada-para-regra-x"]

    def test_registrar_tipo_duplicado_levanta_excecao(self) -> None:
        registrar(
            tipo="fake",
            regra_cls=str,
            construir_implementacao=_fake_construir_implementacao,
            carregar_especificacoes=_fake_carregar_especificacoes,
            entradas_para_regra=_fake_entradas_para_regra,
        )

        with pytest.raises(TipoDuplicado):
            registrar(
                tipo="fake",
                regra_cls=str,
                construir_implementacao=_fake_construir_implementacao,
                carregar_especificacoes=_fake_carregar_especificacoes,
                entradas_para_regra=_fake_entradas_para_regra,
            )

    def test_registry_retorna_copia_nao_a_estrutura_interna(self) -> None:
        registrar(
            tipo="fake",
            regra_cls=str,
            construir_implementacao=_fake_construir_implementacao,
            carregar_especificacoes=_fake_carregar_especificacoes,
            entradas_para_regra=_fake_entradas_para_regra,
        )

        plugins = registry()
        plugins["outro"] = plugins["fake"]

        assert set(registry()) == {"fake"}

    def test_limpar_registry_reinicia_o_estado(self) -> None:
        registrar(
            tipo="fake",
            regra_cls=str,
            construir_implementacao=_fake_construir_implementacao,
            carregar_especificacoes=_fake_carregar_especificacoes,
            entradas_para_regra=_fake_entradas_para_regra,
        )

        limpar_registry()

        assert registry() == {}
