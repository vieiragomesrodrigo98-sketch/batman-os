"""Vol. V, Cap. 20 — Missões: Modelagem Formal.

Formaliza a taxonomia de `MissionType` (criticidade, SLA, política de
escalonamento) e os padrões de composição entre Missões — o vocabulário
estrutural que Playbooks (Cap. 21) instanciam. O ciclo de vida genérico da
Missão já foi especificado no Volume II, Cap. 6; este capítulo não o
redefine, apenas o alimenta com taxonomia.

Fonte da verdade: docs/spec/05-workflow/01-missions-formal-model.md
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel

from batman_os.foundation.types import CapabilityRef, Criticidade, EscalationPolicy, MissionTypeId
from batman_os.kernel.planning_engine import ExecutionPlan
from batman_os.kernel.scheduler import Priority

BreachAction = Literal["alert-only", "auto-escalate-priority"]


class MissionTypeDefinition(BaseModel):
    """Vol.V Cap.20, secao 20.2."""

    id: MissionTypeId
    criticality: Criticidade
    default_sla: timedelta
    escalation_defaults: EscalationPolicy
    allows_sub_missions: bool = True
    cognitive_debt_tracked: bool = True


class SLAContract(BaseModel):
    """Vol.V Cap.20, secao 20.5."""

    mission_type_id: MissionTypeId
    target_sla: timedelta
    warning_threshold: timedelta
    breach_action: BreachAction


class TipoDeMissaoNaoRegistrado(Exception):
    """Vol.V Cap.20, secao 20.2 (AT-20.1) — nenhuma Missao pode existir com
    `MissionTypeId` nao registrado; nao existe missao de tipo generico."""


class RecoveryObrigatoriaAusente(Exception):
    """Vol.V Cap.20, secao 20.3 (tabela, linha 3) — missao `critical` exige
    `RecoveryStrategy` em todo step com efeito colateral; plano sem isso e
    rejeitado, nunca aceito "melhor esforco" (mesma doutrina do AT-7.2)."""


class MissionTypeRegistry:
    """Vol.V Cap.20, secao 20.2."""

    def __init__(self) -> None:
        self._tipos: dict[MissionTypeId, MissionTypeDefinition] = {}

    def register(self, definicao: MissionTypeDefinition) -> None:
        self._tipos[definicao.id] = definicao

    def resolve(self, tipo: MissionTypeId) -> MissionTypeDefinition | None:
        return self._tipos.get(tipo)

    def exigir(self, tipo: MissionTypeId) -> MissionTypeDefinition:
        """AT-20.1 — versao que levanta exceção, para quem precisa da
        definição completa (não apenas confirmar que existe)."""
        definicao = self.resolve(tipo)
        if definicao is None:
            raise TipoDeMissaoNaoRegistrado(
                f"MissionTypeId '{tipo}' nao registrado — nao existe missao "
                "de tipo generico (secao 20.2, AT-20.1)"
            )
        return definicao

    def validar(self, tipo: MissionTypeId) -> None:
        """Satisfaz `RegistroTiposDeMissao` (Vol.II Cap.6) estruturalmente —
        Mission Runtime chama isto em `create()`, sem importar este módulo."""
        self.exigir(tipo)


def prioridade_base_por_criticidade(criticidade: Criticidade) -> Priority:
    """Vol.V Cap.20, secao 20.3 (tabela, linha 1) — criticidade determina a
    prioridade base na fila do Scheduler (Vol.II Cap.10), antes do aging.
    Mapeamento linear simples; a especificação não define os valores exatos,
    apenas que `criticality` é consumido pelo Scheduler como prioridade
    base — a métrica em si é decisão de implementação de referência."""
    return {
        Criticidade.LOW: 0,
        Criticidade.MEDIUM: 10,
        Criticidade.HIGH: 20,
        Criticidade.CRITICAL: 30,
    }[criticidade]


def escalar_prioridade_por_sla(
    prioridade_atual: Priority, incremento: Priority, plano: ExecutionPlan
) -> tuple[Priority, ExecutionPlan]:
    """Vol.V Cap.20, secao 20.5 (AT-20.3) — `breachAction:
    "auto-escalate-priority"` nunca altera o plano já gerado (mesmos `steps`
    e `decision_points`, mesmo `plan_hash`), apenas a prioridade de
    despacho. Retorna o MESMO objeto de plano (identidade preservada) e uma
    nova prioridade — nunca reconstrói ou remonta o plano."""
    return prioridade_atual + incremento, plano


def validar_recovery_obrigatoria_para_criticas(
    plano: ExecutionPlan,
    criticidade: Criticidade,
    tem_efeito_colateral: Callable[[CapabilityRef], bool],
) -> None:
    """Vol.V Cap.20, secao 20.3 (tabela, linha 3) — só relevante quando
    `criticidade == CRITICAL`; para as demais, nunca levanta. Nada aqui
    consulta o Capability Registry (Vol.III Cap.11) diretamente — quem
    chama fornece `tem_efeito_colateral`, para não acoplar este módulo ao
    Runtime (mesmo raciocínio de `RegistroCapacidades` no Planning Engine)."""
    if criticidade != Criticidade.CRITICAL:
        return

    sem_recovery = [
        step.id
        for step in plano.steps
        if tem_efeito_colateral(step.capability) and step.recovery_strategy is None
    ]
    if sem_recovery:
        raise RecoveryObrigatoriaAusente(
            f"Plano {plano.id}: missao critical exige RecoveryStrategy em "
            f"todo step com efeito colateral; ausente em: {sem_recovery}"
        )
