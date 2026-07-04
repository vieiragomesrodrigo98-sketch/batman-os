"""Testes de Playbooks (Vol.V Cap.21) — AT-21.1 a AT-21.3."""

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
from batman_os.kernel.planning_engine import PlanStepTemplate
from batman_os.workflow.playbooks import (
    FieldCondition,
    GapDeCertificacaoDoPlaybook,
    IntentMatcher,
    PlaybookDefinition,
    PlaybookProvenance,
    PlaybookResolutionAmbiguity,
    StatusPlaybook,
    certificar_playbook,
    resolve_playbook,
)

TIPO = MissionTypeId("investigate-incident")
_APPROVED_BY_PADRAO = HumanReviewRef("review-1")


def _matcher(*condicoes: FieldCondition) -> IntentMatcher:
    return IntentMatcher(conditions=list(condicoes))


def _playbook(
    id_: str,
    priority: int,
    matcher: IntentMatcher,
    version: str = "1.0.0",
    approved_by: HumanReviewRef | None = _APPROVED_BY_PADRAO,
    status: StatusPlaybook = StatusPlaybook.ACTIVE,
    steps_template: list[PlanStepTemplate] | None = None,
    recovery_defaults: dict[int, object] | None = None,
    required_capabilities: list[CapabilityRef] | None = None,
) -> PlaybookDefinition:
    return PlaybookDefinition(
        id=PlaybookId(id_),
        version=version,
        applies_to=matcher,
        mission_type_id=TIPO,
        priority=priority,
        steps_template=steps_template or [],
        required_capabilities=required_capabilities or [],
        recovery_defaults=recovery_defaults or {},
        status=status,
        provenance=PlaybookProvenance(origin="hand-authored", approved_by=approved_by),
    )


class TestAT211ResolucaoDeterministaDeConflito:
    def test_nenhum_candidato_casa_retorna_none(self) -> None:
        matcher = _matcher(FieldCondition(campo="sintoma", operador="eq", valor="timeout"))
        playbook = _playbook("p-1", priority=1, matcher=matcher)

        resultado = resolve_playbook(MissionIntent(dados={"sintoma": "outro"}), [playbook])
        assert resultado is None

    def test_um_unico_candidato_e_retornado_direto(self) -> None:
        matcher = _matcher(FieldCondition(campo="sintoma", operador="eq", valor="timeout"))
        playbook = _playbook("p-1", priority=1, matcher=matcher)

        resultado = resolve_playbook(MissionIntent(dados={"sintoma": "timeout"}), [playbook])
        assert resultado is playbook

    def test_prioridade_mais_alta_desempata(self) -> None:
        matcher = _matcher(FieldCondition(campo="sintoma", operador="eq", valor="timeout"))
        baixa = _playbook("p-baixa", priority=1, matcher=matcher)
        alta = _playbook("p-alta", priority=10, matcher=matcher)

        resultado = resolve_playbook(MissionIntent(dados={"sintoma": "timeout"}), [baixa, alta])
        assert resultado is alta

    def test_especificidade_desempata_quando_prioridade_igual(self) -> None:
        generico = _matcher(FieldCondition(campo="sintoma", operador="eq", valor="timeout"))
        especifico = _matcher(
            FieldCondition(campo="sintoma", operador="eq", valor="timeout"),
            FieldCondition(campo="servico", operador="eq", valor="gunicorn"),
        )
        p_generico = _playbook("p-generico", priority=5, matcher=generico)
        p_especifico = _playbook("p-especifico", priority=5, matcher=especifico)

        intent = MissionIntent(dados={"sintoma": "timeout", "servico": "gunicorn"})
        resultado = resolve_playbook(intent, [p_generico, p_especifico])
        assert resultado is p_especifico

    def test_empate_real_prioridade_e_especificidade_levanta_ambiguidade(self) -> None:
        matcher = _matcher(FieldCondition(campo="sintoma", operador="eq", valor="timeout"))
        p1 = _playbook("p-1", priority=5, matcher=matcher, version="1.0.0")
        p2 = _playbook("p-2", priority=5, matcher=matcher, version="2.0.0")

        with pytest.raises(PlaybookResolutionAmbiguity):
            resolve_playbook(MissionIntent(dados={"sintoma": "timeout"}), [p1, p2])

    def test_versao_nao_e_criterio_de_desempate_de_ambiguidade(self) -> None:
        """Secao 21.4: o algoritmo usa versao para ORDENAR, mas o check de
        ambiguidade (passo 6) so compara prioridade e especificidade — uma
        versao mais recente NAO resolve um empate real."""
        matcher = _matcher(FieldCondition(campo="sintoma", operador="eq", valor="timeout"))
        antigo = _playbook("p-antigo", priority=5, matcher=matcher, version="1.0.0")
        novo = _playbook("p-novo", priority=5, matcher=matcher, version="9.9.9")

        with pytest.raises(PlaybookResolutionAmbiguity):
            resolve_playbook(MissionIntent(dados={"sintoma": "timeout"}), [antigo, novo])


class TestAT212ApprovedByObrigatorioParaActive:
    def test_sem_approved_by_nao_certifica(self) -> None:
        matcher = _matcher()
        playbook = _playbook("p-1", priority=1, matcher=matcher, approved_by=None)

        with pytest.raises(GapDeCertificacaoDoPlaybook):
            certificar_playbook(
                playbook,
                outros_ativos=[],
                capability_esta_ativa=lambda _c: True,
                tem_efeito_colateral=lambda _c: False,
            )

    def test_promovido_do_learning_engine_tambem_exige_approved_by(self) -> None:
        matcher = _matcher()
        playbook = PlaybookDefinition(
            id=PlaybookId("p-promovido"),
            version="1.0.0",
            applies_to=matcher,
            mission_type_id=TIPO,
            priority=1,
            provenance=PlaybookProvenance(origin="promoted-from-learning-engine", approved_by=None),
        )

        with pytest.raises(GapDeCertificacaoDoPlaybook):
            certificar_playbook(
                playbook,
                outros_ativos=[],
                capability_esta_ativa=lambda _c: True,
                tem_efeito_colateral=lambda _c: False,
            )

    def test_com_approved_by_certifica(self) -> None:
        matcher = _matcher()
        playbook = _playbook("p-1", priority=1, matcher=matcher)

        certificado = certificar_playbook(
            playbook,
            outros_ativos=[],
            capability_esta_ativa=lambda _c: True,
            tem_efeito_colateral=lambda _c: False,
        )
        assert certificado.status == StatusPlaybook.ACTIVE


class TestAT213RecoveryDefaultsObrigatorioParaEfeitoColateral:
    def test_step_com_efeito_colateral_sem_recovery_reprova(self) -> None:
        template = PlanStepTemplate(
            capability=CapabilityRef(capability_id=CapabilityId("efeito"), versao="1.0.0")
        )
        playbook = _playbook("p-1", priority=1, matcher=_matcher(), steps_template=[template])

        with pytest.raises(GapDeCertificacaoDoPlaybook):
            certificar_playbook(
                playbook,
                outros_ativos=[],
                capability_esta_ativa=lambda _c: True,
                tem_efeito_colateral=lambda _c: True,
            )

    def test_step_com_efeito_colateral_com_recovery_certifica(self) -> None:
        from batman_os.foundation.types import RecoveryStrategy, TipoRecoveryStrategy

        template = PlanStepTemplate(
            capability=CapabilityRef(capability_id=CapabilityId("efeito"), versao="1.0.0")
        )
        playbook = _playbook(
            "p-1",
            priority=1,
            matcher=_matcher(),
            steps_template=[template],
            recovery_defaults={
                0: RecoveryStrategy(tipo=TipoRecoveryStrategy.RETRY, max_tentativas=3)
            },
        )

        certificado = certificar_playbook(
            playbook,
            outros_ativos=[],
            capability_esta_ativa=lambda _c: True,
            tem_efeito_colateral=lambda _c: True,
        )
        assert certificado.status == StatusPlaybook.ACTIVE

    def test_step_sem_efeito_colateral_nao_exige_recovery(self) -> None:
        template = PlanStepTemplate(
            capability=CapabilityRef(capability_id=CapabilityId("sem-efeito"), versao="1.0.0")
        )
        playbook = _playbook("p-1", priority=1, matcher=_matcher(), steps_template=[template])

        certificado = certificar_playbook(
            playbook,
            outros_ativos=[],
            capability_esta_ativa=lambda _c: True,
            tem_efeito_colateral=lambda _c: False,
        )
        assert certificado.status == StatusPlaybook.ACTIVE


class TestCertificacaoRequiredCapabilitiesEIntentMatcher:
    def test_capability_requerida_inativa_reprova(self) -> None:
        playbook = _playbook(
            "p-1",
            priority=1,
            matcher=_matcher(),
            required_capabilities=[
                CapabilityRef(capability_id=CapabilityId("cap-x"), versao="1.0.0")
            ],
        )

        with pytest.raises(GapDeCertificacaoDoPlaybook):
            certificar_playbook(
                playbook,
                outros_ativos=[],
                capability_esta_ativa=lambda _c: False,
                tem_efeito_colateral=lambda _c: False,
            )

    def test_ambiguidade_com_playbook_ja_ativo_reprova(self) -> None:
        matcher = _matcher(FieldCondition(campo="sintoma", operador="eq", valor="timeout"))
        ja_ativo = _playbook("p-ja-ativo", priority=5, matcher=matcher)
        novo = _playbook("p-novo", priority=5, matcher=matcher)

        with pytest.raises(GapDeCertificacaoDoPlaybook):
            certificar_playbook(
                novo,
                outros_ativos=[ja_ativo],
                capability_esta_ativa=lambda _c: True,
                tem_efeito_colateral=lambda _c: False,
            )
