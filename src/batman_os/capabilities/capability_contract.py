"""Vol. IV, Cap. 16 — Capabilities: Contrato e Ciclo de Vida.

Complementa o Capability Engine (Vol.III Cap.11, ponto de vista do catálogo)
do ponto de vista de QUEM IMPLEMENTA uma Capability nova: checklist de
engenharia, testes obrigatórios e critérios de aceitação antes de `Active`.

Fonte da verdade: docs/spec/04-capabilities/02-capability-contract.md
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from batman_os.capabilities.operator import ExecutionContext
from batman_os.foundation.types import SkillRef
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects, StatusCapability


class ResultadoEsperado(StrEnum):
    """Vol.IV Cap.16, secao 16.3 (`AcceptanceTest.expectedOutcome`)."""

    SUCCESS = "success"
    SCHEMA_REJECTION = "schema-rejection"
    TIMEOUT = "timeout"


class AcceptanceTest(BaseModel):
    """Vol.IV Cap.16, secao 16.3."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    entrada: Any = None
    resultado_esperado: ResultadoEsperado
    matcher_saida: Callable[[Any], bool] | None = None


class CapabilityImplementation(BaseModel):
    """Vol.IV Cap.16, secao 16.3."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    definition: CapabilityDefinition
    handler: Callable[[Any, ExecutionContext], Any]
    acceptance_tests: list[AcceptanceTest] = Field(default_factory=list)
    recovery_strategy_defaults: Any | None = None
    skills_used: list[SkillRef] = Field(default_factory=list)


class GapDeChecklist(Exception):
    """Vol.IV Cap.16, secao 16.2/16.6 (AT-16.1) — checklist obrigatório não
    satisfeito. Nunca aceito "para ajustar depois"."""


class RevisaoHumanaObrigatoria(Exception):
    """Vol.IV Cap.16, secao 16.4 (AT-16.2) — `sideEffects: irreversible`
    nunca é certificado automaticamente, mesmo com todos os testes passando."""


class FalhaDeIdempotencia(Exception):
    """Vol.IV Cap.16, secao 16.5 (AT-16.3) — Capability declarada
    `idempotent: true` reprovada no teste de dupla invocação."""


def verificar_checklist(implementacao: CapabilityImplementation) -> list[str]:
    """Vol.IV Cap.16, secao 16.2 (AT-16.1) — retorna a lista de gaps (vazia
    se ok). Não levanta exceção: quem decide o que fazer com os gaps é
    `certificar()`."""
    gaps: list[str] = []
    definicao = implementacao.definition

    if not definicao.input_schema:
        gaps.append("inputSchema ausente ou vazio")
    if not definicao.output_schema:
        gaps.append("outputSchema ausente ou vazio")

    if not implementacao.acceptance_tests:
        gaps.append("nenhum teste de aceitacao declarado")
    else:
        cobertos = {t.resultado_esperado for t in implementacao.acceptance_tests}
        if ResultadoEsperado.SUCCESS not in cobertos:
            gaps.append("nenhum teste cobre o caminho feliz (success)")
        if ResultadoEsperado.SCHEMA_REJECTION not in cobertos:
            gaps.append("nenhum teste cobre entrada invalida (schema-rejection)")
        if ResultadoEsperado.TIMEOUT not in cobertos:
            gaps.append("nenhum teste cobre timeout/falha de dependencia externa")

    return gaps


def _rodar_testes_de_aceitacao(implementacao: CapabilityImplementation) -> list[str]:
    """Executa `acceptance_tests` em processo isolado (nesta implementação de
    referência: chamada direta ao handler — isolamento real de ambiente é
    responsabilidade do Volume VIII, Infrastructure, fora de escopo). Retorna
    os nomes dos testes reprovados."""
    reprovados: list[str] = []
    for teste in implementacao.acceptance_tests:
        try:
            saida = implementacao.handler(teste.entrada, _contexto_de_teste())
        except Exception:
            if teste.resultado_esperado in (
                ResultadoEsperado.SCHEMA_REJECTION,
                ResultadoEsperado.TIMEOUT,
            ):
                continue
            reprovados.append(teste.name)
            continue

        if teste.resultado_esperado != ResultadoEsperado.SUCCESS:
            reprovados.append(teste.name)
            continue
        if teste.matcher_saida is not None and not teste.matcher_saida(saida):
            reprovados.append(teste.name)

    return reprovados


def _contexto_de_teste() -> ExecutionContext:
    from batman_os.foundation.types import MissionId, StepId, TenantId, agora

    return ExecutionContext(
        mission_id=MissionId("mission-de-certificacao"),
        tenant_id=TenantId("tenant-de-certificacao"),
        step_id=StepId("step-de-certificacao"),
        deadline=agora(),
    )


def verificar_idempotencia(
    handler: Callable[[Any, ExecutionContext], Any], entrada: Any, contexto: ExecutionContext
) -> bool:
    """Vol.IV Cap.16, secao 16.5 (AT-16.3) — invoca o handler duas vezes com
    o mesmo `input` e o mesmo `ExecutionContext.step_id`; aprovado se o
    efeito líquido (saída) for idêntico nas duas chamadas — o mesmo padrão
    recomendado na especificação (chave de idempotência derivada do
    `step_id`)."""
    primeira = handler(entrada, contexto)
    segunda = handler(entrada, contexto)
    return bool(primeira == segunda)


def certificar(
    implementacao: CapabilityImplementation,
    revisao_humana_obtida: bool = False,
    entrada_para_teste_idempotencia: Any = None,
    contexto_para_teste_idempotencia: ExecutionContext | None = None,
) -> CapabilityDefinition:
    """Vol.IV Cap.16, secao 16.4 — fluxo completo de certificação.

    Retorna a `CapabilityDefinition` com `status=Active` se aprovada; levanta
    exceção específica se rejeitada em qualquer etapa (nunca aceita
    parcialmente — secao 16.6)."""
    gaps = verificar_checklist(implementacao)
    if gaps:
        raise GapDeChecklist(f"Checklist (secao 16.2) nao satisfeito: {gaps}")

    reprovados = _rodar_testes_de_aceitacao(implementacao)
    if reprovados:
        raise GapDeChecklist(f"Testes de aceitacao reprovados: {reprovados}")

    if implementacao.definition.idempotent:
        if contexto_para_teste_idempotencia is None:
            raise FalhaDeIdempotencia(
                f"Capability '{implementacao.definition.id}' declarada idempotent=true "
                "exige contexto de teste de dupla invocacao antes da certificacao (AT-16.3)"
            )
        aprovado = verificar_idempotencia(
            implementacao.handler, entrada_para_teste_idempotencia, contexto_para_teste_idempotencia
        )
        if not aprovado:
            raise FalhaDeIdempotencia(
                f"Capability '{implementacao.definition.id}' reprovada no teste de "
                "dupla invocacao (AT-16.3) — saida diverge entre as duas chamadas"
            )

    if (
        implementacao.definition.side_effects == SideEffects.IRREVERSIBLE
        and not revisao_humana_obtida
    ):
        raise RevisaoHumanaObrigatoria(
            f"Capability '{implementacao.definition.id}' com sideEffects=irreversible "
            "exige revisao humana explicita antes de Active (AT-16.2)"
        )

    return implementacao.definition.model_copy(update={"status": StatusCapability.ACTIVE})
