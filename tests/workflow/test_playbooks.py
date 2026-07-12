"""Testes de Playbooks (Vol.V Cap.21) — AT-21.1 a AT-21.3."""

from __future__ import annotations

import pytest

from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    DecisionOption,
    EscalationPolicy,
    HumanReviewRef,
    MissionId,
    MissionTypeId,
    PlaybookId,
    RecoveryStrategy,
    Reversibilidade,
    StepId,
    TenantId,
    TipoRecoveryStrategy,
)
from batman_os.kernel.mission_runtime import MissionIntent
from batman_os.kernel.planning_engine import DecisionPoint, PlanStepTemplate, plan
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
from batman_os.workflow.recovery import FallbackChain

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
    decision_points_template: dict[int, DecisionPoint] | None = None,
    required_capabilities: list[CapabilityRef] | None = None,
    fallback_chains: list[FallbackChain] | None = None,
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
        decision_points_template=decision_points_template or {},
        fallback_chains=fallback_chains or [],
        status=status,
        provenance=PlaybookProvenance(origin="hand-authored", approved_by=approved_by),
    )


def _ponto_decisao(pergunta: str = "aprovar?") -> DecisionPoint:
    return DecisionPoint(
        pergunta=pergunta,
        opcoes=[DecisionOption(id="sim", descricao="Aprovar")],
        escalation_policy=EscalationPolicy(
            confidence_threshold=0.8,
            preferred_escalation="human",
            max_llm_retries=1,
            reversibility=Reversibilidade.REVERSIVEL,
        ),
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


class TestFallbackChainConectadaNaCertificacao:
    """Achado de revisão: `validar_fallback_chains()` (Cap.22) existia mas
    nunca era chamada por `certificar_playbook()` (Cap.21) — um Playbook com
    FallbackChain invalida certificava normalmente. Corrigido: `fallback_
    chains` agora e campo de `PlaybookDefinition` e e verificado aqui."""

    def _estrategia_fallback(self, capability_id: str | None) -> RecoveryStrategy:
        return RecoveryStrategy(
            tipo=TipoRecoveryStrategy.FALLBACK_CAPABILITY,
            alternative_capability=(
                CapabilityRef(capability_id=CapabilityId(capability_id), versao="1.0.0")
                if capability_id is not None
                else None
            ),
        )

    def test_fallback_chain_partial_success_em_step_critico_reprova(self) -> None:

        chain = FallbackChain(
            step_id=StepId("s-1"),
            chain=[self._estrategia_fallback("alt")],
            on_chain_exhausted="partial-success",
        )
        playbook = _playbook("p-1", priority=1, matcher=_matcher(), fallback_chains=[chain])

        with pytest.raises(GapDeCertificacaoDoPlaybook):
            certificar_playbook(
                playbook,
                outros_ativos=[],
                capability_esta_ativa=lambda _c: True,
                tem_efeito_colateral=lambda _c: False,
                steps_criticos={StepId("s-1")},
                schema_compativel_para_fallback=lambda _c, _s: True,
            )

    def test_fallback_chain_schema_incompativel_reprova(self) -> None:

        chain = FallbackChain(
            step_id=StepId("s-1"),
            chain=[self._estrategia_fallback("alt")],
            on_chain_exhausted="fail",
        )
        playbook = _playbook("p-1", priority=1, matcher=_matcher(), fallback_chains=[chain])

        with pytest.raises(GapDeCertificacaoDoPlaybook):
            certificar_playbook(
                playbook,
                outros_ativos=[],
                capability_esta_ativa=lambda _c: True,
                tem_efeito_colateral=lambda _c: False,
                schema_compativel_para_fallback=lambda _c, _s: False,
            )

    def test_fallback_chain_valida_certifica_normalmente(self) -> None:

        chain = FallbackChain(
            step_id=StepId("s-1"),
            chain=[self._estrategia_fallback("alt")],
            on_chain_exhausted="fail",
        )
        playbook = _playbook("p-1", priority=1, matcher=_matcher(), fallback_chains=[chain])

        certificado = certificar_playbook(
            playbook,
            outros_ativos=[],
            capability_esta_ativa=lambda _c: True,
            tem_efeito_colateral=lambda _c: False,
            schema_compativel_para_fallback=lambda _c, _s: True,
        )
        assert certificado.status == StatusPlaybook.ACTIVE

    def test_sem_fallback_chains_nao_exige_os_novos_parametros(self) -> None:
        """Retrocompatibilidade: Playbook sem fallback_chains certifica sem
        precisar de steps_criticos/schema_compativel_para_fallback."""
        playbook = _playbook("p-1", priority=1, matcher=_matcher())

        certificado = certificar_playbook(
            playbook,
            outros_ativos=[],
            capability_esta_ativa=lambda _c: True,
            tem_efeito_colateral=lambda _c: False,
        )
        assert certificado.status == StatusPlaybook.ACTIVE


class TestRecoveryDefaultsPropagamParaPlanStepReal:
    """Achado de revisão: `_instanciar_de_playbook()` (Cap.7) ignorava
    `PlaybookDefinition.recovery_defaults` — um Playbook certificado com
    cobertura completa de recovery (AT-21.3) gerava PlanSteps reais sem
    nenhuma RecoveryStrategy. Corrigido em `kernel/planning_engine.py`."""

    class _RegistroCapacidadesFake:
        def buscar_candidatos(self, intent: MissionIntent) -> list[CapabilityRef]:
            del intent
            return []

        def versao(self) -> str:
            return "v1"

    class _RepositorioPlaybooksFake:
        def __init__(self, playbook: PlaybookDefinition) -> None:
            self._playbook = playbook

        def encontrar_correspondente(self, intent: MissionIntent) -> PlaybookDefinition | None:
            del intent
            return self._playbook

    def test_recovery_strategy_chega_ao_plan_step_real(self) -> None:
        recovery = RecoveryStrategy(tipo=TipoRecoveryStrategy.RETRY, max_tentativas=3)
        template = PlanStepTemplate(
            capability=CapabilityRef(capability_id=CapabilityId("efeito"), versao="1.0.0")
        )
        playbook = _playbook(
            "p-1",
            priority=1,
            matcher=_matcher(),
            steps_template=[template],
            recovery_defaults={0: recovery},
        )

        resultado = plan(
            mission_id=MissionId("m-1"),
            tenant_id=TenantId("t-1"),
            intent=MissionIntent(dados={}),
            registro=self._RegistroCapacidadesFake(),
            repositorio_playbooks=self._RepositorioPlaybooksFake(playbook),
        )

        assert len(resultado.steps) == 1
        assert resultado.steps[0].recovery_strategy == recovery
        assert resultado.source_playbook == playbook.id

    def test_step_sem_recovery_default_fica_none(self) -> None:
        template = PlanStepTemplate(
            capability=CapabilityRef(capability_id=CapabilityId("sem-efeito"), versao="1.0.0")
        )
        playbook = _playbook("p-1", priority=1, matcher=_matcher(), steps_template=[template])

        resultado = plan(
            mission_id=MissionId("m-1"),
            tenant_id=TenantId("t-1"),
            intent=MissionIntent(dados={}),
            registro=self._RegistroCapacidadesFake(),
            repositorio_playbooks=self._RepositorioPlaybooksFake(playbook),
        )

        assert resultado.steps[0].recovery_strategy is None


class TestFase9Estagio92CertificacaoDeDecisionPointsTemplate:
    """Fase 9 do roadmap de plataforma (`.claude/plans/peaceful-wondering-
    hearth.md`), Estagio 9.2 — `decision_points_template` e chaveado por
    indice em `steps_template` (mesma convencao de `recovery_defaults`);
    um indice fora do range nunca teria efeito (silenciosamente ignorado
    por `_instanciar_de_playbook()`) sem esta checagem."""

    def test_indice_fora_de_steps_template_reprova(self) -> None:
        template = PlanStepTemplate(
            capability=CapabilityRef(capability_id=CapabilityId("cap-a"), versao="1.0.0")
        )
        playbook = _playbook(
            "p-1",
            priority=1,
            matcher=_matcher(),
            steps_template=[template],
            decision_points_template={5: _ponto_decisao()},
        )

        with pytest.raises(GapDeCertificacaoDoPlaybook):
            certificar_playbook(
                playbook,
                outros_ativos=[],
                capability_esta_ativa=lambda _c: True,
                tem_efeito_colateral=lambda _c: False,
            )

    def test_indice_valido_certifica_normalmente(self) -> None:
        template = PlanStepTemplate(
            capability=CapabilityRef(capability_id=CapabilityId("cap-a"), versao="1.0.0")
        )
        playbook = _playbook(
            "p-1",
            priority=1,
            matcher=_matcher(),
            steps_template=[template],
            decision_points_template={0: _ponto_decisao()},
        )

        certificado = certificar_playbook(
            playbook,
            outros_ativos=[],
            capability_esta_ativa=lambda _c: True,
            tem_efeito_colateral=lambda _c: False,
        )
        assert certificado.status == StatusPlaybook.ACTIVE

    def test_sem_decision_points_template_nao_exige_nada_novo(self) -> None:
        """Retrocompatibilidade: Playbook sem decision_points_template
        certifica exatamente como antes desta fase."""
        playbook = _playbook("p-1", priority=1, matcher=_matcher())

        certificado = certificar_playbook(
            playbook,
            outros_ativos=[],
            capability_esta_ativa=lambda _c: True,
            tem_efeito_colateral=lambda _c: False,
        )
        assert certificado.status == StatusPlaybook.ACTIVE


class TestDecisionPointsTemplatePropagamParaPlanStepReal:
    """Mesma doutrina de `TestRecoveryDefaultsPropagamParaPlanStepReal`
    acima, para `decision_points_template` — prova com um `PlaybookDefinition`
    REAL (não o fake estrutural de `tests/kernel/test_planning_engine.py`)
    que a extração funciona ponta-a-ponta através de `plan()`."""

    class _RegistroCapacidadesFake:
        def buscar_candidatos(self, intent: MissionIntent) -> list[CapabilityRef]:
            del intent
            return []

        def versao(self) -> str:
            return "v1"

    class _RepositorioPlaybooksFake:
        def __init__(self, playbook: PlaybookDefinition) -> None:
            self._playbook = playbook

        def encontrar_correspondente(self, intent: MissionIntent) -> PlaybookDefinition | None:
            del intent
            return self._playbook

    def test_decision_point_chega_ao_execution_plan_real(self) -> None:
        ponto = _ponto_decisao()
        template = PlanStepTemplate(
            capability=CapabilityRef(capability_id=CapabilityId("cap-a"), versao="1.0.0")
        )
        playbook = _playbook(
            "p-1",
            priority=1,
            matcher=_matcher(),
            steps_template=[template],
            decision_points_template={0: ponto},
        )

        resultado = plan(
            mission_id=MissionId("m-1"),
            tenant_id=TenantId("t-1"),
            intent=MissionIntent(dados={}),
            registro=self._RegistroCapacidadesFake(),
            repositorio_playbooks=self._RepositorioPlaybooksFake(playbook),
        )

        assert resultado.decision_points == [ponto]
        assert resultado.steps[0].decision_point_id == ponto.id

    def test_step_sem_decision_point_template_fica_none(self) -> None:
        template = PlanStepTemplate(
            capability=CapabilityRef(capability_id=CapabilityId("cap-a"), versao="1.0.0")
        )
        playbook = _playbook("p-1", priority=1, matcher=_matcher(), steps_template=[template])

        resultado = plan(
            mission_id=MissionId("m-1"),
            tenant_id=TenantId("t-1"),
            intent=MissionIntent(dados={}),
            registro=self._RegistroCapacidadesFake(),
            repositorio_playbooks=self._RepositorioPlaybooksFake(playbook),
        )

        assert resultado.decision_points == []
        assert resultado.steps[0].decision_point_id is None
