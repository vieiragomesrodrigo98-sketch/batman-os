"""Testes de Missões: Modelagem Formal (Vol.V Cap.20) — AT-20.1 a AT-20.3."""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

import pytest

from batman_os.capabilities.cooperation import criar_submissao
from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    Criticidade,
    DecisionOption,
    EscalationPolicy,
    MissionId,
    MissionTypeId,
    PlanId,
    Reversibilidade,
    TenantId,
)
from batman_os.kernel.decision_engine import (
    DecisionEngine,
    ResolucaoConhecimento,
    RespostaLlmCandidata,
)
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import MissionIntent, MissionRuntime
from batman_os.kernel.planning_engine import DecisionPoint, ExecutionPlan, PlanStep
from batman_os.workflow.missions import (
    MissionTypeDefinition,
    MissionTypeRegistry,
    RecoveryObrigatoriaAusente,
    SLAContract,
    TipoDeMissaoNaoRegistrado,
    escalar_prioridade_por_sla,
    prioridade_base_por_criticidade,
    validar_recovery_obrigatoria_para_criticas,
)


def _politica(
    preferred_escalation: Literal["human", "llm"] = "llm",
) -> EscalationPolicy:
    return EscalationPolicy(
        confidence_threshold=0.9,
        preferred_escalation=preferred_escalation,
        max_llm_retries=2,
        reversibility=Reversibilidade.REVERSIVEL,
    )


def _tipo(id_: str, criticidade: Criticidade = Criticidade.MEDIUM) -> MissionTypeDefinition:
    return MissionTypeDefinition(
        id=MissionTypeId(id_),
        criticality=criticidade,
        default_sla=timedelta(hours=1),
        escalation_defaults=_politica(),
    )


class TestAT201NenhumaMissaoSemTipoRegistrado:
    def test_criar_com_tipo_nao_registrado_falha(self) -> None:
        registro = MissionTypeRegistry()
        runtime = MissionRuntime(EventBus(), tipos=registro)

        with pytest.raises(TipoDeMissaoNaoRegistrado):
            runtime.create(
                MissionIntent(dados={}),
                MissionTypeId("tipo-inexistente"),
                tenant_id=TenantId("t-1"),
            )

    def test_criar_com_tipo_registrado_funciona(self) -> None:
        registro = MissionTypeRegistry()
        registro.register(_tipo("investigate-incident"))
        runtime = MissionRuntime(EventBus(), tipos=registro)

        mission = runtime.create(
            MissionIntent(dados={}),
            MissionTypeId("investigate-incident"),
            tenant_id=TenantId("t-1"),
        )

        assert mission.tipo == MissionTypeId("investigate-incident")

    def test_exigir_retorna_a_definicao_completa(self) -> None:
        registro = MissionTypeRegistry()
        definicao = _tipo("investigate-incident", criticidade=Criticidade.HIGH)
        registro.register(definicao)

        assert registro.exigir(MissionTypeId("investigate-incident")) == definicao

    def test_resolve_retorna_none_para_tipo_ausente(self) -> None:
        registro = MissionTypeRegistry()
        assert registro.resolve(MissionTypeId("ausente")) is None


class TestAT202CriticidadeCriticalNuncaEscalaLlm:
    def _ponto_preferindo_llm(self) -> DecisionPoint:
        return DecisionPoint(
            pergunta="qual acao tomar?",
            opcoes=[DecisionOption(id="a", descricao="A")],
            escalation_policy=_politica(preferred_escalation="llm"),
        )

    def test_missao_critical_nunca_tenta_llm_mesmo_preferindo_llm(self) -> None:
        chamadas_llm = {"n": 0}

        class LlmContador:
            def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
                del ponto
                chamadas_llm["n"] += 1
                return RespostaLlmCandidata(
                    opcao=DecisionOption(id="a", descricao="A"),
                    confidence=0.99,
                    evidencia_bruta="resposta",
                )

        class SemConhecimento:
            def consultar(self, ponto: DecisionPoint) -> ResolucaoConhecimento | None:
                del ponto
                return None

        class ValidadorAprova:
            def validar(self, ponto: DecisionPoint, resposta: RespostaLlmCandidata) -> bool:
                del ponto, resposta
                return True

        engine = DecisionEngine(
            base_conhecimento=SemConhecimento(),
            llm_gateway=LlmContador(),
            validador=ValidadorAprova(),
        )

        resultado = engine.resolve(
            self._ponto_preferindo_llm(), MissionId("m-1"), criticidade=Criticidade.CRITICAL
        )

        assert resultado.escalonado_para == "human"
        assert chamadas_llm["n"] == 0

    def test_missao_nao_critical_tenta_llm_normalmente(self) -> None:
        class SemConhecimento:
            def consultar(self, ponto: DecisionPoint) -> ResolucaoConhecimento | None:
                del ponto
                return None

        class LlmAprovado:
            def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
                del ponto
                return RespostaLlmCandidata(
                    opcao=DecisionOption(id="a", descricao="A"),
                    confidence=0.95,
                    evidencia_bruta="resposta",
                )

        class ValidadorAprova:
            def validar(self, ponto: DecisionPoint, resposta: RespostaLlmCandidata) -> bool:
                del ponto, resposta
                return True

        engine = DecisionEngine(
            base_conhecimento=SemConhecimento(),
            llm_gateway=LlmAprovado(),
            validador=ValidadorAprova(),
        )

        resultado = engine.resolve(
            self._ponto_preferindo_llm(), MissionId("m-1"), criticidade=Criticidade.MEDIUM
        )

        assert resultado.decision is not None
        assert resultado.decision.resolved_by == "llm"

    def test_sem_criticidade_informada_comportamento_e_o_anterior(self) -> None:
        """Retrocompatibilidade: `criticidade=None` (default) preserva o
        comportamento do Decision Engine anterior ao Volume V."""

        class SemConhecimento:
            def consultar(self, ponto: DecisionPoint) -> ResolucaoConhecimento | None:
                del ponto
                return None

        class LlmAprovado:
            def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
                del ponto
                return RespostaLlmCandidata(
                    opcao=DecisionOption(id="a", descricao="A"),
                    confidence=0.95,
                    evidencia_bruta="resposta",
                )

        class ValidadorAprova:
            def validar(self, ponto: DecisionPoint, resposta: RespostaLlmCandidata) -> bool:
                del ponto, resposta
                return True

        engine = DecisionEngine(
            base_conhecimento=SemConhecimento(),
            llm_gateway=LlmAprovado(),
            validador=ValidadorAprova(),
        )

        resultado = engine.resolve(self._ponto_preferindo_llm(), MissionId("m-1"))

        assert resultado.decision is not None
        assert resultado.decision.resolved_by == "llm"


class TestAT203AutoEscalatePriorityNuncaAlteraPlano:
    def test_escalar_prioridade_preserva_identidade_e_hash_do_plano(self) -> None:
        step = PlanStep(
            capability=CapabilityRef(capability_id=CapabilityId("cap-a"), versao="1.0.0")
        )
        plano = ExecutionPlan(
            id=PlanId("p-1"),
            mission_id=MissionId("m-1"),
            tenant_id=TenantId("t-1"),
            steps=[step],
            decision_points=[],
            plan_hash="hash-original",
        )

        nova_prioridade, plano_retornado = escalar_prioridade_por_sla(
            prioridade_atual=10, incremento=5, plano=plano
        )

        assert nova_prioridade == 15
        assert plano_retornado is plano
        assert plano_retornado.plan_hash == "hash-original"
        assert plano_retornado.steps == [step]
        assert plano_retornado.decision_points == []


class TestRecoveryObrigatoriaParaCriticasNaoFormal:
    """Vol.V Cap.20, secao 20.3 (tabela, linha 3) — nao e um AT numerado, mas
    e uma regra estrutural explicita do capitulo."""

    def _plano_com_step_sem_recovery(self) -> ExecutionPlan:
        step = PlanStep(
            capability=CapabilityRef(capability_id=CapabilityId("efeito"), versao="1.0.0")
        )
        return ExecutionPlan(
            id=PlanId("p-1"),
            mission_id=MissionId("m-1"),
            tenant_id=TenantId("t-1"),
            steps=[step],
            decision_points=[],
            plan_hash="h",
        )

    def test_critical_sem_recovery_em_step_com_efeito_colateral_falha(self) -> None:
        plano = self._plano_com_step_sem_recovery()

        with pytest.raises(RecoveryObrigatoriaAusente):
            validar_recovery_obrigatoria_para_criticas(
                plano, Criticidade.CRITICAL, tem_efeito_colateral=lambda _c: True
            )

    def test_critical_sem_efeito_colateral_nao_exige_recovery(self) -> None:
        plano = self._plano_com_step_sem_recovery()

        validar_recovery_obrigatoria_para_criticas(
            plano, Criticidade.CRITICAL, tem_efeito_colateral=lambda _c: False
        )  # nao levanta

    def test_nao_critical_nunca_exige_recovery_mesmo_com_efeito_colateral(self) -> None:
        plano = self._plano_com_step_sem_recovery()

        validar_recovery_obrigatoria_para_criticas(
            plano, Criticidade.MEDIUM, tem_efeito_colateral=lambda _c: True
        )  # nao levanta


class TestPrioridadeBasePorCriticidade:
    def test_ordem_monotonica_crescente(self) -> None:
        valores = [prioridade_base_por_criticidade(c) for c in Criticidade]
        assert valores == sorted(valores)
        assert len(set(valores)) == len(valores)


class TestPadroesDeComposicao:
    """Vol.V Cap.20, secao 20.4 — padroes ja suportados estruturalmente pelo
    Mission Runtime (Cap.6, `parent_mission_id`) e pela Cooperacao (Cap.19,
    `criar_submissao`); este capitulo formaliza o vocabulario, nao introduz
    mecanismo novo. Testado aqui compondo uma missao orquestradora real com
    multiplas sub-missoes (secao 20.4.2)."""

    def test_missao_orquestradora_com_multiplas_submissoes(self) -> None:
        registro = MissionTypeRegistry()
        registro.register(_tipo("preparar-deploy"))
        registro.register(_tipo("rodar-testes"))
        registro.register(_tipo("revisar-migracao"))
        registro.register(_tipo("notificar-stakeholders"))
        runtime = MissionRuntime(EventBus(), tipos=registro)

        orquestradora = runtime.create(
            MissionIntent(dados={}), MissionTypeId("preparar-deploy"), tenant_id=TenantId("t-1")
        )

        sub_missoes = [
            criar_submissao(runtime, orquestradora, MissionIntent(dados={}), MissionTypeId(tipo))
            for tipo in ("rodar-testes", "revisar-migracao", "notificar-stakeholders")
        ]

        assert len(sub_missoes) == 3
        assert all(s.parent_mission_id == orquestradora.id for s in sub_missoes)
        assert all(s.tenant_id == orquestradora.tenant_id for s in sub_missoes)

    def test_missao_recorrente_e_estruturalmente_identica_a_qualquer_outra(self) -> None:
        """Secao 20.4.3 — a unica diferenca de uma missao 'agendada' e a
        origem do intent (um agendador, nao um evento externo); nao existe
        estado ou excecao nova na maquina de estados (Vol.II Cap.6)."""
        registro = MissionTypeRegistry()
        registro.register(_tipo("auditoria-compliance-diaria"))
        runtime = MissionRuntime(EventBus(), tipos=registro)

        mission = runtime.create(
            MissionIntent(dados={"origem": "agendador"}),
            MissionTypeId("auditoria-compliance-diaria"),
            tenant_id=TenantId("t-1"),
        )

        assert mission.tipo == MissionTypeId("auditoria-compliance-diaria")


class TestSLAContract:
    def test_sla_contract_valido(self) -> None:
        contrato = SLAContract(
            mission_type_id=MissionTypeId("investigate-incident"),
            target_sla=timedelta(hours=1),
            warning_threshold=timedelta(minutes=45),
            breach_action="auto-escalate-priority",
        )
        assert contrato.breach_action == "auto-escalate-priority"
