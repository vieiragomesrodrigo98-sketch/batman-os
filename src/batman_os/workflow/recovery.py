"""Vol. V, Cap. 22 — Estratégias de Recuperação e Fallback.

Generaliza `RecoveryStrategy` (Vol.II Cap.9) para cadeias de fallback —
sequências ordenadas de estratégias com degradação controlada — e formaliza
a relação entre degradação recorrente e Cognitive Debt (Volume VI, Learning
Engine). Fecha o Volume V.

Fonte da verdade: docs/spec/05-workflow/03-recovery-fallback-strategies.md
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from batman_os.foundation.types import (
    CapabilityRef,
    DegradationRecord,
    ImpactoDegradacao,
    RecoveryStrategy,
    StepId,
    TipoRecoveryStrategy,
)

OnChainExhausted = Literal["fail", "partial-success", "escalate"]


class FallbackChain(BaseModel):
    """Vol.V Cap.22, secao 22.2 — estende (nunca substitui) `RecoveryStrategy`
    (Vol.II Cap.9): cada elo da cadeia é um `RecoveryStrategy` já existente,
    tentado da esquerda para a direita até esgotar."""

    step_id: StepId
    chain: list[RecoveryStrategy]
    on_chain_exhausted: OnChainExhausted


class GapDeFallbackChain(Exception):
    """Vol.V Cap.22, secao 21.6/22.6 — checklist de certificação de
    `FallbackChain` não satisfeito (AT-22.1, AT-22.2)."""


def validar_fallback_chains(
    chains: list[FallbackChain],
    steps_criticos: set[StepId],
    schema_compativel: Callable[[CapabilityRef, StepId], bool],
) -> None:
    """Vol.V Cap.22, secao 22.6 (AT-22.1, AT-22.2) — verificado na
    certificação do Playbook (Cap.21), nunca detectado só em runtime.

    `steps_criticos` — StepIds críticos ao objetivo central da missão
    (decidido em tempo de design do Playbook, nunca inferido em runtime pelo
    Workflow Engine, secao 22.4). `schema_compativel` fornecido pelo
    chamador (consulta ao Capability Registry, Vol.III Cap.11), mesmo
    raciocínio de `RegistroCapacidades` no Planning Engine."""
    gaps: list[str] = []

    for chain in chains:
        if chain.on_chain_exhausted == "partial-success" and chain.step_id in steps_criticos:
            gaps.append(
                f"Step critico '{chain.step_id}' nao pode declarar "
                "onChainExhausted='partial-success' (AT-22.1)"
            )

        for estrategia in chain.chain:
            if estrategia.tipo != TipoRecoveryStrategy.FALLBACK_CAPABILITY:
                continue
            if estrategia.alternative_capability is None:
                gaps.append(
                    f"Step '{chain.step_id}': estrategia fallback-capability sem "
                    "alternativeCapability declarada"
                )
            elif not schema_compativel(estrategia.alternative_capability, chain.step_id):
                gaps.append(
                    f"Step '{chain.step_id}': fallback-capability "
                    f"'{estrategia.alternative_capability.capability_id}' com outputSchema "
                    "incompativel com os passos subsequentes (AT-22.2)"
                )

    if gaps:
        raise GapDeFallbackChain(f"FallbackChain(s) reprovada(s): {gaps}")


def deveria_gerar_candidato_de_gap(degradacao: DegradationRecord) -> bool:
    """Vol.V Cap.22, secao 22.5 — toda `DegradationRecord` com `impact:
    "requires-follow-up"` gera automaticamente um candidato de gap de
    conhecimento na Operational Memory (Vol.III Cap.13); o padrão de
    degradação recorrente sinaliza que uma nova Capability, Tool ou
    Playbook precisa ser desenvolvido (Volume VI, Learning Engine)."""
    return degradacao.impact == ImpactoDegradacao.REQUIRES_FOLLOW_UP
