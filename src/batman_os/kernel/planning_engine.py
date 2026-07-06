"""Vol. II, Cap. 7 — Planning Engine.

Transforma uma `MissionIntent` em um `ExecutionPlan` determinístico: quais
passos, em que ordem, com quais dependências — nunca resolve qual alternativa
escolher em cada ponto de ambiguidade (isso é o Decision Engine, Cap.8).

Fonte da verdade: docs/spec/02-kernel/03-planning-engine.md
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    CapabilityRef,
    DecisionOption,
    DecisionPointId,
    EscalationPolicy,
    MissionId,
    PlanId,
    PlaybookId,
    RecoveryStrategy,
    StepId,
    TenantId,
    Timestamp,
    agora,
    novo_uuid7,
)
from batman_os.kernel.mission_runtime import MissionIntent


class DecisionPoint(BaseModel):
    """Vol.II Cap.7, secao 7.3.

    `dados` (Milestone 4 desta construção — achado de revisão): payload
    genérico do contexto da decisão. Sem ele, `RuleEvolution`
    (`learning/rule_evolution_adapter.py`) só conseguia casar
    `RuleDefinition`s com `condition` vazio, já que não havia nada além de
    `pergunta` para avaliar `RuleCondition.satisfeita_por()`."""

    id: DecisionPointId = Field(default_factory=lambda: DecisionPointId(novo_uuid7()))
    pergunta: str
    opcoes: list[DecisionOption]
    escalation_policy: EscalationPolicy
    dados: dict[str, Any] = Field(default_factory=dict)


class PlanStep(BaseModel):
    """Vol.II Cap.7, secao 7.3."""

    id: StepId = Field(default_factory=lambda: StepId(novo_uuid7()))
    capability: CapabilityRef
    depende_de: list[StepId] = Field(default_factory=list)
    decision_point_id: DecisionPointId | None = None
    recovery_strategy: RecoveryStrategy | None = None


class ExecutionPlan(BaseModel):
    """Vol.II Cap.7, secao 7.3.

    `tenant_id` obrigatorio desde Vol.III Cap.14 (ADR-0005)."""

    id: PlanId = Field(default_factory=lambda: PlanId(novo_uuid7()))
    mission_id: MissionId
    tenant_id: TenantId
    steps: list[PlanStep]
    decision_points: list[DecisionPoint]
    source_playbook: PlaybookId | None = None
    gerado_em: Timestamp = Field(default_factory=agora)
    plan_hash: str


class PlanningFailure(Exception):
    """Vol.II Cap.7, secao 7.4.1 — levantada quando nenhum Playbook casa com o
    intent E a composicao via grafo de Capabilities tambem nao encontra uma
    composicao valida. Carrega evidencia; a missao e escalada como gap de
    conhecimento (Cap.1, secao 1.4), nunca resolvida "adivinhando" via LLM."""

    def __init__(self, motivo: str, evidencia: dict[str, object] | None = None) -> None:
        super().__init__(motivo)
        self.evidencia = evidencia or {}


class PlaybookCandidato(Protocol):
    """Forma minima que a Planning Engine precisa de um Playbook (Vol.V
    Cap.21, `workflow/playbooks.py`) para instanciar steps. Definido como
    Protocol para nao criar dependencia do pacote de Workflow: basta que
    `PlaybookDefinition` satisfaca esta forma estruturalmente, sem import
    direto daqui (Vol.VIII Cap.32, secao 32.3 — kernel nunca depende de
    workflow)."""

    @property
    def id(self) -> PlaybookId: ...

    @property
    def steps_template(self) -> list[PlanStepTemplate]: ...

    @property
    def recovery_defaults(self) -> dict[int, RecoveryStrategy]: ...


class PlanStepTemplate(BaseModel):
    """Versao minima de um passo de Playbook (Vol.V Cap.21) — o suficiente
    para a Planning Engine instanciar `PlanStep`s a partir de um Playbook
    candidato."""

    capability: CapabilityRef
    depende_de_indices: list[int] = Field(default_factory=list)


class RepositorioPlaybooks(Protocol):
    """Vol.II Cap.7, secao 7.4, passo 1. Satisfeito de verdade por
    `PlaybookRegistry`/consultas equivalentes (Vol.V Cap.21) — `plan()`
    tambem aceita `None` e cai direto para composicao via grafo (secao 7.4,
    passo 3), para quem ainda nao tem um repositorio de Playbooks."""

    def encontrar_correspondente(self, intent: MissionIntent) -> PlaybookCandidato | None: ...


class RegistroCapacidades(Protocol):
    """Vol.II Cap.7, secao 7.4, passo 3 / Vol.III Cap.11. Implementado de
    verdade no Capability Engine (Task futura desta construcao) — aqui apenas
    o contrato que a Planning Engine precisa para compor um plano."""

    def buscar_candidatos(self, intent: MissionIntent) -> list[CapabilityRef]: ...

    def versao(self) -> str: ...


def plan(
    mission_id: MissionId,
    tenant_id: TenantId,
    intent: MissionIntent,
    registro: RegistroCapacidades,
    repositorio_playbooks: RepositorioPlaybooks | None = None,
) -> ExecutionPlan:
    """Vol.II Cap.7, secao 7.4.

    Nota de implementacao: a assinatura da especificacao (`plan(intent,
    registry)`) nao recebe `mission_id`/`tenant_id` explicitamente, mas
    `ExecutionPlan` exige ambos os campos — adicionados aqui como parametros
    obrigatorios (gap mecanico, nao decisao arquitetural nova; `tenant_id`
    e exigido estruturalmente desde Vol.III Cap.14, ADR-0005).
    """
    playbook = (
        repositorio_playbooks.encontrar_correspondente(intent) if repositorio_playbooks else None
    )

    origem: PlaybookId | None
    if playbook is not None:
        steps = _instanciar_de_playbook(playbook)
        origem = playbook.id
    else:
        steps = _compor_via_grafo_capacidades(intent, registro)
        origem = None

    decision_points = _extrair_decision_points(steps)
    _validar(steps)

    plan_hash = _hash_determinístico(intent, registro.versao())

    return ExecutionPlan(
        mission_id=mission_id,
        tenant_id=tenant_id,
        steps=steps,
        decision_points=decision_points,
        source_playbook=origem,
        plan_hash=plan_hash,
    )


def _instanciar_de_playbook(playbook: PlaybookCandidato) -> list[PlanStep]:
    """Vol.V Cap.21, secao 21.6 (AT-21.3) — `recovery_defaults` (chaveado por
    indice em `steps_template`, mesma convencao de `depende_de_indices`)
    precisa chegar ao `PlanStep` real gerado aqui; sem isso, a certificacao
    do Playbook garantiria cobertura de recovery que a instanciacao real
    descartaria silenciosamente."""
    passos: list[PlanStep] = []
    for indice, template in enumerate(playbook.steps_template):
        passos.append(
            PlanStep(
                capability=template.capability,
                depende_de=[passos[i].id for i in template.depende_de_indices if i < indice],
                recovery_strategy=playbook.recovery_defaults.get(indice),
            )
        )
    return passos


def _compor_via_grafo_capacidades(
    intent: MissionIntent, registro: RegistroCapacidades
) -> list[PlanStep]:
    """Vol.II Cap.7, secao 7.4, passo 3 — fallback determinístico quando não
    há Playbook. NUNCA invoca um LLM neste ponto (Determinism First).

    Heurística mínima desta construção (a especificação não detalha um
    algoritmo de composição): um passo por Capability candidata retornada
    pelo registro, encadeados sequencialmente na ordem retornada. Composição
    mais sofisticada (paralelismo, agrupamento) é trabalho futuro quando o
    Capability Engine real estiver integrado.
    """
    candidatos = registro.buscar_candidatos(intent)
    passos: list[PlanStep] = []
    anterior: StepId | None = None
    for candidato in candidatos:
        depende_de = [anterior] if anterior is not None else []
        passo = PlanStep(capability=candidato, depende_de=depende_de)
        passos.append(passo)
        anterior = passo.id
    return passos


def _extrair_decision_points(steps: list[PlanStep]) -> list[DecisionPoint]:
    """Vol.II Cap.7, secao 7.4, passo 3 — nesta construção, DecisionPoints só
    chegam via Playbook (fora de escopo); a composição via grafo de
    Capabilities não gera nenhum por si só. Retorna sempre vazio até Playbooks
    reais (Volume V) poderem anexar DecisionPoints aos templates."""
    del steps
    return []


def _validar(steps: list[PlanStep]) -> None:
    """Vol.II Cap.7, secao 7.4, passo 4 (AT-7.2) — detecta ciclos e steps
    órfãos (dependência para step inexistente). Nunca aceito como "melhor
    esforço"."""
    ids_existentes = {s.id for s in steps}
    for step in steps:
        para_inexistente = [dep for dep in step.depende_de if dep not in ids_existentes]
        if para_inexistente:
            raise PlanningFailure(
                f"Step {step.id} depende de step(s) inexistente(s): {para_inexistente}",
                evidencia={"step_id": step.id, "dependencias_invalidas": para_inexistente},
            )

    ciclo = _encontrar_ciclo(steps)
    if ciclo is not None:
        raise PlanningFailure(
            f"Grafo de dependencias contem ciclo: {ciclo}",
            evidencia={"ciclo": ciclo},
        )


def _encontrar_ciclo(steps: list[PlanStep]) -> list[StepId] | None:
    grafo = {s.id: s.depende_de for s in steps}
    cor: dict[StepId, int] = dict.fromkeys(grafo, 0)  # 0=branco 1=cinza 2=preto
    pilha: list[StepId] = []

    def dfs(no: StepId) -> list[StepId] | None:
        cor[no] = 1
        pilha.append(no)
        for vizinho in grafo.get(no, []):
            if cor.get(vizinho, 0) == 1:
                inicio = pilha.index(vizinho)
                return [*pilha[inicio:], vizinho]
            if cor.get(vizinho, 0) == 0:
                achado = dfs(vizinho)
                if achado is not None:
                    return achado
        pilha.pop()
        cor[no] = 2
        return None

    for no in grafo:
        if cor[no] == 0:
            achado = dfs(no)
            if achado is not None:
                return achado
    return None


def _hash_determinístico(intent: MissionIntent, versao_registro: str) -> str:
    """Vol.II Cap.7, secao 7.3 (`planHash`) / AT-7.1 — mesmo intent + mesma
    versao do Capability Registry produzem sempre o mesmo hash (replay
    determinístico), independente de quando/quantas vezes `plan()` é chamado."""
    payload = json.dumps(
        {"intent": intent.dados, "registro_versao": versao_registro},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
