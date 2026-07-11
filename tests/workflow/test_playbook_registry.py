"""Testes de `PlaybookRegistry` (Fase 3 do roadmap de plataforma,
`.claude/plans/peaceful-wondering-hearth.md`, Estágio 3.3)."""

from __future__ import annotations

import pytest

from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    HumanReviewRef,
    MissionTypeId,
    PlaybookId,
)
from batman_os.kernel.mission_runtime import MissionIntent
from batman_os.workflow.playbooks import (
    FieldCondition,
    IntentMatcher,
    PlaybookDefinition,
    PlaybookNaoAtivo,
    PlaybookProvenance,
    PlaybookRegistry,
    PlaybookResolutionAmbiguity,
    StatusPlaybook,
)

TIPO = MissionTypeId("investigate-incident")
_APPROVED_BY_PADRAO = HumanReviewRef("review-1")


def _matcher(*condicoes: FieldCondition) -> IntentMatcher:
    return IntentMatcher(conditions=list(condicoes))


def _ref(nome: str) -> CapabilityRef:
    return CapabilityRef(capability_id=CapabilityId(nome), versao="1.0.0")


def _playbook(
    id_: str,
    priority: int,
    matcher: IntentMatcher,
    status: StatusPlaybook = StatusPlaybook.ACTIVE,
) -> PlaybookDefinition:
    return PlaybookDefinition(
        id=PlaybookId(id_),
        version="1.0.0",
        applies_to=matcher,
        mission_type_id=TIPO,
        priority=priority,
        provenance=PlaybookProvenance(origin="hand-authored", approved_by=_APPROVED_BY_PADRAO),
        status=status,
    )


class TestPlaybookRegistry:
    def test_round_trip_register_e_resolve_por_id(self) -> None:
        registry = PlaybookRegistry()
        matcher = _matcher(FieldCondition(campo="tipo", operador="eq", valor="security-audit"))
        playbook = _playbook("auditoria-seguranca", priority=5, matcher=matcher)

        registry.register(playbook)

        assert registry.resolve_por_id(PlaybookId("auditoria-seguranca")) == playbook
        assert registry.resolve_por_id(PlaybookId("inexistente")) is None

    def test_rejeita_playbook_nao_active(self) -> None:
        registry = PlaybookRegistry()
        matcher = _matcher(FieldCondition(campo="tipo", operador="eq", valor="x"))
        playbook_draft = _playbook(
            "p-draft", priority=1, matcher=matcher, status=StatusPlaybook.DRAFT
        )

        with pytest.raises(PlaybookNaoAtivo):
            registry.register(playbook_draft)

    def test_encontrar_correspondente_delega_a_resolve_playbook(self) -> None:
        registry = PlaybookRegistry()
        matcher = _matcher(FieldCondition(campo="tipo", operador="eq", valor="security-audit"))
        playbook = _playbook("auditoria-seguranca", priority=5, matcher=matcher)
        registry.register(playbook)

        encontrado = registry.encontrar_correspondente(
            MissionIntent(dados={"tipo": "security-audit"})
        )
        assert encontrado is not None
        assert encontrado.id == playbook.id

        nao_encontrado = registry.encontrar_correspondente(MissionIntent(dados={"tipo": "outro"}))
        assert nao_encontrado is None

    def test_encontrar_correspondente_propaga_ambiguidade(self) -> None:
        registry = PlaybookRegistry()
        matcher = _matcher(FieldCondition(campo="tipo", operador="eq", valor="x"))
        registry.register(_playbook("p-1", priority=5, matcher=matcher))
        registry.register(_playbook("p-2", priority=5, matcher=matcher))

        with pytest.raises(PlaybookResolutionAmbiguity):
            registry.encontrar_correspondente(MissionIntent(dados={"tipo": "x"}))

    def test_satisfaz_repositorio_playbooks_estruturalmente(self) -> None:
        """Usado direto dentro de plan(..., repositorio_playbooks=registry)
        — RepositorioPlaybooks (kernel/planning_engine.py) exige só
        encontrar_correspondente(intent) -> PlaybookCandidato | None."""
        from batman_os.kernel.planning_engine import RepositorioPlaybooks

        registry = PlaybookRegistry()
        matcher = _matcher(FieldCondition(campo="tipo", operador="eq", valor="security-audit"))
        registry.register(_playbook("auditoria-seguranca", priority=5, matcher=matcher))

        repositorio: RepositorioPlaybooks = registry
        candidato = repositorio.encontrar_correspondente(
            MissionIntent(dados={"tipo": "security-audit"})
        )
        assert candidato is not None
        assert candidato.id == PlaybookId("auditoria-seguranca")
