"""Testes de `orchestration/playbook_driver.py` (Fase 3 do roadmap de
plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estágio 3.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest

from batman_os.capabilities.capability_contract import (
    AcceptanceTest,
    CapabilityImplementation,
    certificar,
)
from batman_os.capabilities.operator import (
    ExecutionContext,
    FilesystemAccess,
    NetworkPolicy,
    Operator,
    PermissionSet,
    ResourceLimits,
    SandboxPolicy,
    SideEffectScope,
)
from batman_os.capabilities.rules.relatorio_consolidado import (
    construir_implementacao as construir_implementacao_relatorio,
)
from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    Criticidade,
    DecisionOption,
    EscalationPolicy,
    HumanReviewRef,
    MissionTypeId,
    OperatorId,
    OperatorRef,
    PlaybookId,
    Reversibilidade,
    StepId,
    TenantId,
)
from batman_os.kernel.decision_engine import DecisionEngine
from batman_os.kernel.event_bus import EmissorKernel, EventBus, KernelEvent
from batman_os.kernel.mission_runtime import MissionIntent, MissionRuntime, MissionState
from batman_os.kernel.planning_engine import (
    DecisionPoint,
    ExecutionPlan,
    PlanStep,
    PlanStepTemplate,
    hidratar_plano,
)
from batman_os.orchestration import playbook_driver as playbook_driver_mod
from batman_os.orchestration.implementation_registry import ExecutorViaImplementacoes
from batman_os.orchestration.playbook_driver import (
    EspecificacaoDeStepAusente,
    PlaybookNaoResolvido,
    executar_missao_via_playbook,
)
from batman_os.orchestration.playbook_step_specs import RelatorioConsolidadoSpec
from batman_os.orchestration.schema_validators import (
    ValidadorContratoSempreAprova,
    ValidadorSchemaEstrutural,
)
from batman_os.runtime.capability_engine import (
    CapabilityDefinition,
    CapabilityRegistry,
    SideEffects,
)
from batman_os.runtime.execution_engine import ExecutionEngine
from batman_os.workflow.missions import MissionTypeDefinition, MissionTypeRegistry
from batman_os.workflow.playbooks import (
    FieldCondition,
    IntentMatcher,
    PlaybookDefinition,
    PlaybookProvenance,
    PlaybookRegistry,
    StatusPlaybook,
)

TIPO = MissionTypeId("investigate-incident")
TENANT = TenantId("t-1")
CAP_CHECK_ID = CapabilityId("check-fake")
CAP_CHECK_FALHA_ID = CapabilityId("check-fake-falha")
CAP_RELATORIO_ID = CapabilityId("relatorio-consolidado-de-achados")


@dataclass(frozen=True)
class _ConstrutorFixo:
    """`ConstrutorDeEntrada` de teste — entrada estática, ignora
    dependências."""

    entrada: dict[str, Any]

    def construir(self, outputs_das_dependencias: dict[StepId, Any]) -> Any:
        del outputs_das_dependencias
        return self.entrada


def _handler_check_sucesso(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    return {"achados": entrada.get("achados_fixos", [])}


def _handler_check_falha(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    if entrada.get("forcar_falha"):
        raise ValueError("falha proposital do check")
    return {"achados": entrada.get("achados_fixos", [])}


def _registro_tipos() -> MissionTypeRegistry:
    registro = MissionTypeRegistry()
    registro.register(
        MissionTypeDefinition(
            id=TIPO,
            criticality=Criticidade.MEDIUM,
            default_sla=timedelta(hours=1),
            escalation_defaults=EscalationPolicy(
                confidence_threshold=0.8,
                preferred_escalation="human",
                max_llm_retries=1,
                reversibility=Reversibilidade.REVERSIVEL,
            ),
        )
    )
    return registro


def _capability_check(capability_id: CapabilityId, handler: Any) -> CapabilityDefinition:
    impl = CapabilityImplementation(
        definition=CapabilityDefinition(
            id=capability_id,
            name="check-fake",
            version="1.0.0",
            input_schema={"properties": {"achados_fixos": {}}},
            output_schema={"properties": {"achados": {}}},
            deterministic=True,
            side_effects=SideEffects.NONE,
            idempotent=True,
        ),
        handler=handler,
        acceptance_tests=[
            AcceptanceTest(
                name="sucesso",
                entrada={"achados_fixos": []},
                resultado_esperado="success",
                matcher_saida=lambda saida: "achados" in saida,
            ),
            AcceptanceTest(name="rejeicao", entrada=None, resultado_esperado="schema-rejection"),
            AcceptanceTest(name="timeout", entrada=None, resultado_esperado="timeout"),
        ],
    )
    return certificar(
        impl,
        entrada_para_teste_idempotencia={"achados_fixos": []},
        contexto_para_teste_idempotencia=_contexto(),
    )


def _contexto() -> ExecutionContext:
    from batman_os.foundation.types import MissionId, agora

    return ExecutionContext(
        mission_id=MissionId("m-cert"), tenant_id=TENANT, step_id=StepId("s-cert"), deadline=agora()
    )


def _montar_infra(
    handler_check: Any, capability_id_check: CapabilityId
) -> tuple[
    MissionRuntime, CapabilityRegistry, DecisionEngine, ExecutionEngine, Operator, OperatorRef
]:
    event_bus = EventBus()
    runtime = MissionRuntime(event_bus, tipos=_registro_tipos())

    definicao_check = _capability_check(capability_id_check, handler_check)
    definicao_relatorio = certificar(
        construir_implementacao_relatorio(),
        entrada_para_teste_idempotencia=construir_implementacao_relatorio()
        .acceptance_tests[0]
        .entrada,
        contexto_para_teste_idempotencia=_contexto(),
    )

    registry = CapabilityRegistry()
    registry.register(definicao_check)
    registry.register(definicao_relatorio)

    operator = Operator(
        operator_id=OperatorId("op-playbook"),
        capabilities=[capability_id_check, CAP_RELATORIO_ID],
        permissions=PermissionSet(
            allowed_actions=[str(capability_id_check), str(CAP_RELATORIO_ID)],
            side_effect_scope=SideEffectScope.READ_ONLY,
        ),
        sandbox=SandboxPolicy(
            resource_limits=ResourceLimits(),
            network_policy=NetworkPolicy.NONE,
            filesystem_access=FilesystemAccess.NONE,
        ),
        executor=ExecutorViaImplementacoes(
            {
                capability_id_check: CapabilityImplementation(
                    definition=definicao_check, handler=handler_check
                ),
                CAP_RELATORIO_ID: CapabilityImplementation(
                    definition=definicao_relatorio,
                    handler=construir_implementacao_relatorio().handler,
                ),
            }
        ),
    )

    decision_engine = DecisionEngine(
        base_conhecimento=_SemConhecimento(),
        llm_gateway=_LlmNuncaChamado(),
        validador=_ValidadorQualquer(),
    )
    execution_engine = ExecutionEngine(
        validador_schema=ValidadorSchemaEstrutural(),
        validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
    )
    operator_ref = OperatorRef(operator_id=operator.id)

    return runtime, registry, decision_engine, execution_engine, operator, operator_ref


class _SemConhecimento:
    def consultar(self, ponto: object) -> None:
        del ponto
        return None


class _LlmNuncaChamado:
    def consultar(self, ponto: object) -> None:
        del ponto
        raise AssertionError("Playbook de teste nao deveria envolver LLM")


class _ValidadorQualquer:
    def validar(self, ponto: object, resposta: object) -> bool:
        del ponto, resposta
        return True


class _RegistroCapacidadesFake:
    """Nunca consultado quando um Playbook resolve (`_instanciar_de_
    playbook` usa `template.capability` direto) — presente só para
    satisfazer o Protocol `RegistroCapacidades` de `plan()`."""

    def buscar_candidatos(self, intent: object) -> list[CapabilityRef]:
        del intent
        return []

    def versao(self) -> str:
        return "v1"


def _playbook_2_steps(capability_id_check: CapabilityId) -> PlaybookDefinition:
    matcher = IntentMatcher(
        conditions=[FieldCondition(campo="tipo", operador="eq", valor="playbook-de-teste")]
    )
    return PlaybookDefinition(
        id=PlaybookId("playbook-de-teste"),
        version="1.0.0",
        applies_to=matcher,
        mission_type_id=TIPO,
        priority=5,
        steps_template=[
            PlanStepTemplate(
                capability=CapabilityRef(capability_id=capability_id_check, versao="1.0.0")
            ),
            PlanStepTemplate(
                capability=CapabilityRef(capability_id=CAP_RELATORIO_ID, versao="1.0.0"),
                depende_de_indices=[0],
            ),
        ],
        provenance=PlaybookProvenance(
            origin="hand-authored", approved_by=HumanReviewRef("review-1")
        ),
        status=StatusPlaybook.ACTIVE,
    )


class TestExecutarMissaoViaPlaybook:
    def test_relatorio_recebe_exatamente_os_achados_do_step_anterior(self) -> None:
        runtime, registry, decision_engine, execution_engine, operator, operator_ref = (
            _montar_infra(_handler_check_sucesso, CAP_CHECK_ID)
        )
        playbook_registry = PlaybookRegistry()
        playbook_registry.register(_playbook_2_steps(CAP_CHECK_ID))

        achados_esperados = [
            {"codigo": "TEST-001", "severidade": "high"},
            {"codigo": "TEST-002", "severidade": "medium"},
        ]
        especificacoes = {
            0: _ConstrutorFixo({"achados_fixos": achados_esperados}),
            1: RelatorioConsolidadoSpec(titulo_missao="Auditoria de teste"),
        }

        resultado = executar_missao_via_playbook(
            MissionIntent(dados={"tipo": "playbook-de-teste"}),
            TIPO,
            TENANT,
            especificacoes,
            runtime=runtime,
            registro=_RegistroCapacidadesFake(),
            registry=registry,
            decision_engine=decision_engine,
            execution_engine=execution_engine,
            operator=operator,
            operator_ref=operator_ref,
            repositorio_playbooks=playbook_registry,
        )

        assert resultado.estado_final == "completed"
        assert resultado.achados == achados_esperados
        assert resultado.relatorio is not None
        assert resultado.relatorio["achados"] == achados_esperados
        assert resultado.relatorio["total_achados"] == 2
        assert resultado.relatorio["resumo_por_severidade"] == {"high": 1, "medium": 1}

        final_mission = runtime.get_mission(resultado.mission_id, TENANT)
        assert final_mission.estado == MissionState.COMPLETED

        execution_engine.fechar()

    def test_falha_no_check_nunca_deixa_o_relatorio_pronto(self) -> None:
        runtime, registry, decision_engine, execution_engine, operator, operator_ref = (
            _montar_infra(_handler_check_falha, CAP_CHECK_FALHA_ID)
        )
        playbook_registry = PlaybookRegistry()
        playbook_registry.register(_playbook_2_steps(CAP_CHECK_FALHA_ID))

        especificacoes = {
            0: _ConstrutorFixo({"forcar_falha": True}),
            1: RelatorioConsolidadoSpec(),
        }

        resultado = executar_missao_via_playbook(
            MissionIntent(dados={"tipo": "playbook-de-teste"}),
            TIPO,
            TENANT,
            especificacoes,
            runtime=runtime,
            registro=_RegistroCapacidadesFake(),
            registry=registry,
            decision_engine=decision_engine,
            execution_engine=execution_engine,
            operator=operator,
            operator_ref=operator_ref,
            repositorio_playbooks=playbook_registry,
        )

        assert resultado.estado_final == "failed"
        assert resultado.relatorio is None

        final_mission = runtime.get_mission(resultado.mission_id, TENANT)
        assert final_mission.estado == MissionState.FAILED

        execution_engine.fechar()

    def test_playbook_nao_resolvido_levanta_excecao_dedicada(self) -> None:
        runtime, registry, decision_engine, execution_engine, operator, operator_ref = (
            _montar_infra(_handler_check_sucesso, CAP_CHECK_ID)
        )
        playbook_registry = PlaybookRegistry()  # vazio -- nenhum Playbook registrado

        with pytest.raises(PlaybookNaoResolvido):
            executar_missao_via_playbook(
                MissionIntent(dados={"tipo": "playbook-de-teste"}),
                TIPO,
                TENANT,
                {},
                runtime=runtime,
                registro=_RegistroCapacidadesFake(),
                registry=registry,
                decision_engine=decision_engine,
                execution_engine=execution_engine,
                operator=operator,
                operator_ref=operator_ref,
                repositorio_playbooks=playbook_registry,
            )
        execution_engine.fechar()

    def test_especificacao_ausente_levanta_excecao_dedicada(self) -> None:
        runtime, registry, decision_engine, execution_engine, operator, operator_ref = (
            _montar_infra(_handler_check_sucesso, CAP_CHECK_ID)
        )
        playbook_registry = PlaybookRegistry()
        playbook_registry.register(_playbook_2_steps(CAP_CHECK_ID))

        with pytest.raises(EspecificacaoDeStepAusente):
            executar_missao_via_playbook(
                MissionIntent(dados={"tipo": "playbook-de-teste"}),
                TIPO,
                TENANT,
                {0: _ConstrutorFixo({"achados_fixos": []})},  # falta indice 1
                runtime=runtime,
                registro=_RegistroCapacidadesFake(),
                registry=registry,
                decision_engine=decision_engine,
                execution_engine=execution_engine,
                operator=operator,
                operator_ref=operator_ref,
                repositorio_playbooks=playbook_registry,
            )
        execution_engine.fechar()


def _fake_plan_com_escalada(capability_id: CapabilityId) -> Any:
    """Fase 7, Estágio 7.1 — `plan()` real nunca produz `decision_points`
    para um Playbook real (`_extrair_decision_points()` sempre retorna
    `[]`, fora de escopo até Volume V, achado de investigação). Este fake
    substitui `plan()` DENTRO do módulo `playbook_driver` (via
    monkeypatch) para provar que o DRIVER reage corretamente a uma
    escalada — replica o mesmo comportamento de publicar `PlanCreated`
    que `plan(..., event_bus=...)` já faz, sem depender da função
    privada `_publicar_plan_created`."""

    def _plan(
        mission_id: Any,
        tenant_id: Any,
        intent: Any,
        registro: Any,
        repositorio_playbooks: Any = None,
        event_bus: Any = None,
    ) -> ExecutionPlan:
        del intent, registro, repositorio_playbooks
        plano = ExecutionPlan(
            mission_id=mission_id,
            tenant_id=tenant_id,
            steps=[PlanStep(capability=CapabilityRef(capability_id=capability_id, versao="1.0.0"))],
            decision_points=[
                DecisionPoint(
                    pergunta="precisa de aprovacao humana?",
                    opcoes=[DecisionOption(id="a", descricao="Aprovar")],
                    escalation_policy=EscalationPolicy(
                        confidence_threshold=0.8,
                        preferred_escalation="human",
                        max_llm_retries=1,
                        reversibility=Reversibilidade.REVERSIVEL,
                    ),
                )
            ],
            plan_hash="hash-escalada",
        )
        if event_bus is not None:
            event_bus.publish(
                KernelEvent(
                    mission_id=plano.mission_id,
                    tenant_id=plano.tenant_id,
                    tipo="PlanCreated",
                    emitido_por=EmissorKernel.PLANNING_ENGINE,
                    payload={"plano": plano.model_dump(mode="json")},
                )
            )
        return plano

    return _plan


class TestFase7Estagio71ReconhecimentoDeEscalada:
    """Fase 7 do roadmap de plataforma (`.claude/plans/peaceful-
    wondering-hearth.md`), Estágio 7.1 — achado de investigação: antes
    desta correção, `executar_missao_via_playbook` descartava uma
    escalada silenciosamente (decision=None, loop continuava,
    DECISIONS_RESOLVED disparava incondicionalmente) e despachava o
    workflow mesmo assim."""

    def test_escalada_interrompe_e_nao_cria_workflow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runtime, registry, decision_engine, execution_engine, operator, operator_ref = (
            _montar_infra(_handler_check_sucesso, CAP_CHECK_ID)
        )
        playbook_registry = PlaybookRegistry()
        playbook_registry.register(_playbook_2_steps(CAP_CHECK_ID))
        monkeypatch.setattr(playbook_driver_mod, "plan", _fake_plan_com_escalada(CAP_CHECK_ID))

        resultado = executar_missao_via_playbook(
            MissionIntent(dados={"tipo": "playbook-de-teste"}),
            TIPO,
            TENANT,
            {},  # nenhum ConstrutorDeEntrada necessario -- workflow nunca desperta
            runtime=runtime,
            registro=_RegistroCapacidadesFake(),
            registry=registry,
            decision_engine=decision_engine,
            execution_engine=execution_engine,
            operator=operator,
            operator_ref=operator_ref,
            repositorio_playbooks=playbook_registry,
        )

        assert resultado.estado_final == "awaiting_human"
        assert resultado.workflow_run_id is None
        assert resultado.decision_pendente is not None
        assert resultado.decision_pendente.pergunta == "precisa de aprovacao humana?"
        assert resultado.achados == []
        assert resultado.relatorio is None

        missao_real = runtime.get_mission(resultado.mission_id, TENANT)
        assert missao_real.estado == MissionState.AWAITING_HUMAN

        execution_engine.fechar()

    def test_sem_event_bus_plano_nao_e_persistido(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runtime, registry, decision_engine, execution_engine, operator, operator_ref = (
            _montar_infra(_handler_check_sucesso, CAP_CHECK_ID)
        )
        playbook_registry = PlaybookRegistry()
        playbook_registry.register(_playbook_2_steps(CAP_CHECK_ID))
        monkeypatch.setattr(playbook_driver_mod, "plan", _fake_plan_com_escalada(CAP_CHECK_ID))
        event_bus_de_verificacao = EventBus()  # instancia PROPRIA, nunca passada ao driver

        resultado = executar_missao_via_playbook(
            MissionIntent(dados={"tipo": "playbook-de-teste"}),
            TIPO,
            TENANT,
            {},
            runtime=runtime,
            registro=_RegistroCapacidadesFake(),
            registry=registry,
            decision_engine=decision_engine,
            execution_engine=execution_engine,
            operator=operator,
            operator_ref=operator_ref,
            repositorio_playbooks=playbook_registry,
            # event_bus NAO fornecido -- comportamento default preservado
        )

        assert hidratar_plano(event_bus_de_verificacao, resultado.mission_id) is None
        execution_engine.fechar()

    def test_com_event_bus_plano_e_persistido_e_hidratavel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        event_bus = EventBus()
        runtime = MissionRuntime(event_bus, tipos=_registro_tipos())
        definicao_check = _capability_check(CAP_CHECK_ID, _handler_check_sucesso)
        registry = CapabilityRegistry()
        registry.register(definicao_check)
        registry.register(
            certificar(
                construir_implementacao_relatorio(),
                entrada_para_teste_idempotencia=construir_implementacao_relatorio()
                .acceptance_tests[0]
                .entrada,
                contexto_para_teste_idempotencia=_contexto(),
            )
        )
        operator = Operator(
            operator_id=OperatorId("op-playbook-eb"),
            capabilities=[CAP_CHECK_ID, CAP_RELATORIO_ID],
            permissions=PermissionSet(
                allowed_actions=[str(CAP_CHECK_ID), str(CAP_RELATORIO_ID)],
                side_effect_scope=SideEffectScope.READ_ONLY,
            ),
            sandbox=SandboxPolicy(
                resource_limits=ResourceLimits(),
                network_policy=NetworkPolicy.NONE,
                filesystem_access=FilesystemAccess.NONE,
            ),
            executor=ExecutorViaImplementacoes({}),
        )
        decision_engine = DecisionEngine(
            base_conhecimento=_SemConhecimento(),
            llm_gateway=_LlmNuncaChamado(),
            validador=_ValidadorQualquer(),
        )
        execution_engine = ExecutionEngine(
            validador_schema=ValidadorSchemaEstrutural(),
            validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
        )
        operator_ref = OperatorRef(operator_id=operator.id)
        playbook_registry = PlaybookRegistry()
        playbook_registry.register(_playbook_2_steps(CAP_CHECK_ID))
        monkeypatch.setattr(playbook_driver_mod, "plan", _fake_plan_com_escalada(CAP_CHECK_ID))

        resultado = executar_missao_via_playbook(
            MissionIntent(dados={"tipo": "playbook-de-teste"}),
            TIPO,
            TENANT,
            {},
            runtime=runtime,
            registro=_RegistroCapacidadesFake(),
            registry=registry,
            decision_engine=decision_engine,
            execution_engine=execution_engine,
            operator=operator,
            operator_ref=operator_ref,
            repositorio_playbooks=playbook_registry,
            event_bus=event_bus,
        )

        plano_hidratado = hidratar_plano(event_bus, resultado.mission_id)
        assert plano_hidratado is not None
        assert len(plano_hidratado.decision_points) == 1
        assert plano_hidratado.decision_points[0].pergunta == "precisa de aprovacao humana?"

        execution_engine.fechar()
