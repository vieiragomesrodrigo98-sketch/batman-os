"""Vol. V, Cap. 21 — Playbooks.

Estrutura, versionamento, certificação e resolução determinística de
conflito entre Playbooks — o principal Knowledge Asset produtor de
determinismo em escala (Volume II, Cap. 7, seção 7.4: fonte preferencial
de instanciação de um `ExecutionPlan`).

Fonte da verdade: docs/spec/05-workflow/02-playbooks.md
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    CapabilityRef,
    HumanReviewRef,
    KnowledgeAssetRef,
    MissionTypeId,
    PlaybookId,
    RecoveryStrategy,
)
from batman_os.kernel.mission_runtime import MissionIntent
from batman_os.kernel.planning_engine import PlanStepTemplate


class StatusPlaybook(StrEnum):
    """Vol.V Cap.21, secao 21.3 — espelha deliberadamente o ciclo de vida de
    Capability (Vol.III Cap.11, secao 11.5): nunca remover fisicamente,
    apenas desativar."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class FieldCondition(BaseModel):
    """Vol.V Cap.21, secao 21.2 — refinamento estrutural adicional sobre um
    campo do intent. Casamento sempre estrutural, nunca semântico via LLM."""

    campo: str
    operador: Literal["eq", "in", "exists"]
    valor: Any = None


class IntentMatcher(BaseModel):
    """Vol.V Cap.21, secao 21.2.

    Campo `schema` da especificação renomeado para `intent_schema`: nome
    reservado que colide com um atributo de `pydantic.BaseModel` (gap
    mecânico de nomenclatura entre linguagens, não decisão arquitetural)."""

    intent_schema: dict[str, Any] = Field(default_factory=dict)
    conditions: list[FieldCondition] = Field(default_factory=list)

    def especificidade(self) -> int:
        """Vol.V Cap.21, secao 21.4 — 'matcher mais específico (mais
        condições)', critério de desempate 2 em `resolve_playbook`."""
        return len(self.conditions)

    def casa_com(self, intent: MissionIntent) -> bool:
        """Casamento estrutural: cada `FieldCondition` deve ser satisfeita
        pelos dados do intent. Validação de JSON Schema completa (`schema`)
        é responsabilidade de uma lib externa — fora de escopo desta
        construção; aqui, o casamento é decidido pelas `conditions`."""
        for condicao in self.conditions:
            if condicao.operador == "exists":
                if condicao.campo not in intent.dados:
                    return False
            elif condicao.operador == "eq":
                if intent.dados.get(condicao.campo) != condicao.valor:
                    return False
            elif condicao.operador == "in":
                if intent.dados.get(condicao.campo) not in (condicao.valor or []):
                    return False
        return True


class PlaybookProvenance(BaseModel):
    """Vol.V Cap.21, secao 21.5 — obrigatória para qualquer Playbook, mesmo
    promovido automaticamente do Learning Engine (Vol.VI); `approved_by`
    ausente é o que impede `Active` (AT-21.2)."""

    origin: Literal["hand-authored", "promoted-from-learning-engine"]
    source_knowledge_assets: list[KnowledgeAssetRef] = Field(default_factory=list)
    approved_by: HumanReviewRef | None = None


class PlaybookDefinition(BaseModel):
    """Vol.V Cap.21, secao 21.2.

    Nota de implementação: `recoveryDefaults` na especificação é chaveado
    por `StepId`, mas `PlanStepTemplate` (Vol.II Cap.7) não tem `StepId`
    estável antes da instanciação — o mesmo motivo pelo qual
    `depende_de_indices` já referencia por índice, não por id. Chaveado
    aqui por índice em `steps_template`, consistente com essa escolha já
    feita no Planning Engine (gap mecânico, não decisão arquitetural nova).
    """

    id: PlaybookId
    version: str
    applies_to: IntentMatcher
    mission_type_id: MissionTypeId
    priority: int
    steps_template: list[PlanStepTemplate] = Field(default_factory=list)
    required_capabilities: list[CapabilityRef] = Field(default_factory=list)
    recovery_defaults: dict[int, RecoveryStrategy] = Field(default_factory=dict)
    status: StatusPlaybook = StatusPlaybook.DRAFT
    provenance: PlaybookProvenance


class PlaybookResolutionAmbiguity(Exception):
    """Vol.V Cap.21, secao 21.4 (AT-21.1) — empate real (mesma prioridade,
    mesma especificidade) nunca é resolvido silenciosamente."""

    def __init__(self, motivo: str, evidencia: dict[str, object] | None = None) -> None:
        super().__init__(motivo)
        self.evidencia = evidencia or {}


class GapDeCertificacaoDoPlaybook(Exception):
    """Vol.V Cap.21, secao 21.6 — checklist de certificação não satisfeito."""


def _partes_versao(versao: str) -> tuple[int, int, int]:
    major, minor, patch = (versao.split(".") + ["0", "0"])[:3]
    return int(major), int(minor), int(patch)


def resolve_playbook(
    intent: MissionIntent, candidatos: list[PlaybookDefinition]
) -> PlaybookDefinition | None:
    """Vol.V Cap.21, secao 21.4 (AT-21.1). Retorna `None` quando nenhum
    Playbook casa (segue para composição via grafo, Vol.II Cap.7) — nunca
    lança para esse caso, apenas para empate real entre casamentos."""
    combinados = [p for p in candidatos if p.applies_to.casa_com(intent)]
    if not combinados:
        return None
    if len(combinados) == 1:
        return combinados[0]

    ordenados = sorted(
        combinados,
        key=lambda p: (
            -p.priority,
            -p.applies_to.especificidade(),
            tuple(-parte for parte in _partes_versao(p.version)),
        ),
    )
    primeiro, segundo = ordenados[0], ordenados[1]
    empate_real = (
        primeiro.priority == segundo.priority
        and primeiro.applies_to.especificidade() == segundo.applies_to.especificidade()
    )
    if empate_real:
        raise PlaybookResolutionAmbiguity(
            f"Empate real entre Playbooks '{primeiro.id}' e '{segundo.id}' "
            "para o mesmo intent (mesma prioridade e especificidade)",
            evidencia={"candidatos": [p.id for p in combinados]},
        )
    return ordenados[0]


def certificar_playbook(
    playbook: PlaybookDefinition,
    outros_ativos: list[PlaybookDefinition],
    capability_esta_ativa: Callable[[CapabilityRef], bool],
    tem_efeito_colateral: Callable[[CapabilityRef], bool],
) -> PlaybookDefinition:
    """Vol.V Cap.21, secao 21.6 — checklist de certificação. `capability_
    esta_ativa`/`tem_efeito_colateral` fornecidos pelo chamador (consulta ao
    Capability Registry, Vol.III Cap.11), para não acoplar este módulo ao
    Runtime diretamente (mesmo raciocínio de `RegistroCapacidades` no
    Planning Engine)."""
    gaps: list[str] = []

    mesmo_tipo_ativos = [
        p
        for p in outros_ativos
        if p.mission_type_id == playbook.mission_type_id and p.status == StatusPlaybook.ACTIVE
    ]
    for outro in mesmo_tipo_ativos:
        ambiguo = (
            outro.priority == playbook.priority
            and outro.applies_to.especificidade() == playbook.applies_to.especificidade()
        )
        if ambiguo:
            gaps.append(f"IntentMatcher ambiguo frente ao Playbook ja ativo '{outro.id}'")

    inativas = [
        c.capability_id for c in playbook.required_capabilities if not capability_esta_ativa(c)
    ]
    if inativas:
        gaps.append(f"requiredCapabilities nao ativas no Capability Registry: {inativas}")

    faltando_recovery = [
        indice
        for indice, template in enumerate(playbook.steps_template)
        if tem_efeito_colateral(template.capability) and indice not in playbook.recovery_defaults
    ]
    if faltando_recovery:
        gaps.append(
            f"PlanStepTemplate com efeito colateral sem recoveryDefaults: {faltando_recovery}"
        )

    if playbook.provenance.approved_by is None:
        gaps.append(
            "provenance.approved_by ausente — nenhum Playbook atinge Active sem aprovacao "
            "humana registrada, independente da origem"
        )

    if gaps:
        raise GapDeCertificacaoDoPlaybook(f"Playbook '{playbook.id}' reprovado: {gaps}")

    return playbook.model_copy(update={"status": StatusPlaybook.ACTIVE})
