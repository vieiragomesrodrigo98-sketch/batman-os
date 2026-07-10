"""SDK de registro de Capabilities (Fase 1 do roadmap de plataforma,
"Consolidar o Núcleo" — `.claude/plans/peaceful-wondering-hearth.md`).

Substitui o wiring manual que existia em `cli/scan_command.py` (import
disperso + tupla de certificação por Capability + 2 unions de tipos +
cadeia `elif isinstance(regra, RegraXSpec)`) por um registro único: cada
Capability chama `registrar(tipo=..., ...)` uma vez — hoje centralizado
em `cli/descoberta_arquivos.py::registrar_capabilities_conhecidas()`,
não dentro do próprio módulo da Capability.

**Por que não dentro do módulo da Capability** (o `@capability class X`
que seria o ideal): `entradas_X_para_regra()` (a função que constrói as
`EntradaX` a partir do resultado da descoberta em disco) vive em
`cli/descoberta_arquivos.py`, que por sua vez importa `EntradaX`/
`RegraXSpec` de `capabilities/rules/*.py` — se o módulo da Capability
importasse de volta `cli/descoberta_arquivos.py` para se auto-registrar,
seria import circular. Registrar em `descoberta_arquivos.py` (que já
importa dos dois lados) resolve isso sem violar a direção de dependência
atual. Mover as primitivas de descoberta (`arquivos_para_regra` etc.)
para um módulo abaixo de `cli/` destravaria o registro dentro do próprio
módulo da Capability — extensão natural documentada no plano, não feita
nesta rodada (mudança maior, risco maior)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from batman_os.capabilities.capability_contract import CapabilityImplementation


@dataclass(frozen=True)
class CapabilityPlugin:
    """Tudo que `scan_command.py`/`compare_migracao.py` precisam saber
    sobre uma Capability para registrá-la, carregar seus specs e montar
    as entradas de uma Missão — sem nenhum código específico por
    Capability fora deste registro.

    `regra_cls` é a classe Pydantic (`RegraXSpec`) que identifica essa
    Capability num item de spec já carregado (`item["regra"]`) — permite
    `scan_command.py` despachar por `type(regra)` (dict O(1)) em vez da
    cadeia `elif isinstance(...)` antiga, SEM exigir que quem chama
    `executar_scan(especificacoes=...)` marque os itens com um `tipo`
    (mantém compatibilidade com specs carregados direto de um loader,
    ex.: `carregar_lote_01()`, como os testes existentes já fazem)."""

    tipo: str
    regra_cls: type[Any]
    construir_implementacao: Callable[[], CapabilityImplementation]
    carregar_especificacoes: Callable[[], list[Any]]
    entradas_para_regra: Callable[[Path, Any, dict[str, Any]], list[Any]]


class TipoDuplicado(Exception):
    """Dois registros para o mesmo `tipo` — import ambíguo; falha cedo em
    vez de um sobrescrever o outro silenciosamente."""


_REGISTRY: dict[str, CapabilityPlugin] = {}


def registrar(
    tipo: str,
    *,
    regra_cls: type[Any],
    construir_implementacao: Callable[[], CapabilityImplementation],
    carregar_especificacoes: Callable[[], list[Any]],
    entradas_para_regra: Callable[[Path, Any, dict[str, Any]], list[Any]],
) -> None:
    if tipo in _REGISTRY:
        raise TipoDuplicado(f"tipo={tipo!r} já registrado por outra Capability")
    _REGISTRY[tipo] = CapabilityPlugin(
        tipo=tipo,
        regra_cls=regra_cls,
        construir_implementacao=construir_implementacao,
        carregar_especificacoes=carregar_especificacoes,
        entradas_para_regra=entradas_para_regra,
    )


def registry() -> dict[str, CapabilityPlugin]:
    return dict(_REGISTRY)


def registry_por_regra_cls() -> dict[type[Any], CapabilityPlugin]:
    """Índice por `regra_cls` — dispatch O(1) por `type(regra)`, mesmo
    espírito da cadeia `elif isinstance(regra, RegraXSpec)` que existia em
    `scan_command.py`, sem precisar dela."""
    return {plugin.regra_cls: plugin for plugin in _REGISTRY.values()}


def limpar_registry() -> None:
    """Só para testes — reinicia o registro global entre casos de teste
    isolados (produção chama `registrar_capabilities_conhecidas()` uma
    única vez por processo)."""
    _REGISTRY.clear()
