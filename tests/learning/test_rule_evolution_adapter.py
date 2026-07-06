"""Testes do adaptador Rule Evolution -> Decision Engine (achado de revisão).

Prova que uma `RuleDefinition` promovida a `active` (Vol.VI Cap.24) passa a
ser, de fato, consultada por um `DecisionEngine` real (Vol.II Cap.8) —
fechando o ciclo descrito no diagrama do Cap.26, secao 26.2, que antes
existia só como dois módulos testados isoladamente sem nunca se tocarem.
"""

from __future__ import annotations

from batman_os.foundation.types import (
    DecisionOption,
    EscalationPolicy,
    HumanReviewRef,
    MissionId,
    Reversibilidade,
    RuleId,
)
from batman_os.kernel.decision_engine import DecisionEngine, RespostaLlmCandidata
from batman_os.kernel.planning_engine import DecisionPoint
from batman_os.learning.rule_evolution import (
    DecisionPointSignature,
    RuleCondition,
    RuleDefinition,
    RulePromotion,
    StatusRegra,
)
from batman_os.learning.rule_evolution_adapter import CatalogoDeRegrasComoBaseConhecimento


class LlmNuncaChamado:
    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        raise AssertionError(
            "LLM nao deveria ser consultado quando a regra resolve por conhecimento"
        )


class ValidadorQualquer:
    def validar(self, ponto: DecisionPoint, resposta: RespostaLlmCandidata) -> bool:
        del ponto, resposta
        return True


def _politica() -> EscalationPolicy:
    return EscalationPolicy(
        confidence_threshold=0.8,
        preferred_escalation="llm",
        max_llm_retries=1,
        reversibility=Reversibilidade.REVERSIVEL,
    )


def _regra_ativa(pergunta: str) -> RuleDefinition:
    return RuleDefinition(
        id=RuleId("R-timeout"),
        version="1.0.0",
        applies_to=DecisionPointSignature(pergunta_padrao=pergunta),
        condition=[],
        resolution=DecisionOption(id="aumentar-timeout", descricao="Aumentar timeout"),
        confidence_base=0.95,
        provenance=RulePromotion(
            source_candidate_signature="sig-1", reviewed_by=HumanReviewRef("review-1")
        ),
        status=StatusRegra.ACTIVE,
    )


class TestAdaptadorFechaOCicloDeAprendizado:
    def test_regra_ativa_e_consultada_e_resolve_por_conhecimento(self) -> None:
        regra = _regra_ativa("qual acao para timeout?")
        catalogo = CatalogoDeRegrasComoBaseConhecimento([regra])
        engine = DecisionEngine(
            base_conhecimento=catalogo, llm_gateway=LlmNuncaChamado(), validador=ValidadorQualquer()
        )
        ponto = DecisionPoint(
            pergunta="qual acao para timeout?",
            opcoes=[DecisionOption(id="aumentar-timeout", descricao="Aumentar timeout")],
            escalation_policy=_politica(),
        )

        resultado = engine.resolve(ponto, MissionId("m-1"))

        assert resultado.decision is not None
        assert resultado.decision.resolved_by == "knowledge"
        assert resultado.decision.chosen_option.id == "aumentar-timeout"
        assert resultado.decision.confidence == 0.95

    def test_regra_ativa_com_pergunta_diferente_nao_resolve_escala_para_llm(self) -> None:
        regra = _regra_ativa("qual acao para timeout?")
        catalogo = CatalogoDeRegrasComoBaseConhecimento([regra])

        class LlmAprovado:
            def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
                del ponto
                return RespostaLlmCandidata(
                    opcao=DecisionOption(id="a", descricao="A"),
                    confidence=0.9,
                    evidencia_bruta="resposta",
                )

        engine = DecisionEngine(
            base_conhecimento=catalogo, llm_gateway=LlmAprovado(), validador=ValidadorQualquer()
        )
        ponto = DecisionPoint(
            pergunta="pergunta completamente diferente",
            opcoes=[DecisionOption(id="a", descricao="A")],
            escalation_policy=_politica(),
        )

        resultado = engine.resolve(ponto, MissionId("m-1"))

        assert resultado.decision is not None
        assert resultado.decision.resolved_by == "llm"

    def test_regra_draft_nunca_e_consultada(self) -> None:
        from batman_os.learning.rule_evolution import resolve_rule

        regra_draft = _regra_ativa("qual acao para timeout?").model_copy(
            update={"status": StatusRegra.DRAFT}
        )
        catalogo = CatalogoDeRegrasComoBaseConhecimento([regra_draft])
        ponto = DecisionPoint(
            pergunta="qual acao para timeout?",
            opcoes=[DecisionOption(id="a", descricao="A")],
            escalation_policy=_politica(),
        )

        assert catalogo.consultar(ponto) is None
        assert resolve_rule(ponto, {}, [regra_draft]) is None

    def test_consultar_retorna_none_sem_regra_correspondente(self) -> None:
        catalogo = CatalogoDeRegrasComoBaseConhecimento([])
        ponto = DecisionPoint(
            pergunta="pergunta sem regra",
            opcoes=[DecisionOption(id="a", descricao="A")],
            escalation_policy=_politica(),
        )

        assert catalogo.consultar(ponto) is None


class TestDecisionPointDadosMilestone4:
    """Prova o fechamento da limitação documentada no adaptador: antes,
    `dados={}` era hardcoded e só regras com `condition` vazio casavam.
    Agora `DecisionPoint.dados` é repassado de verdade."""

    def _regra_com_condition(self, pergunta: str) -> RuleDefinition:
        return RuleDefinition(
            id=RuleId("R-condicional"),
            version="1.0.0",
            applies_to=DecisionPointSignature(pergunta_padrao=pergunta),
            condition=[RuleCondition(campo="ambiente", operador="eq", valor="staging")],
            resolution=DecisionOption(id="opcao-staging", descricao="Opção de staging"),
            confidence_base=0.9,
            provenance=RulePromotion(
                source_candidate_signature="sig-2", reviewed_by=HumanReviewRef("review-2")
            ),
            status=StatusRegra.ACTIVE,
        )

    def test_regra_com_condition_casa_quando_dados_do_ponto_satisfazem(self) -> None:
        regra = self._regra_com_condition("qual ambiente?")
        catalogo = CatalogoDeRegrasComoBaseConhecimento([regra])
        ponto = DecisionPoint(
            pergunta="qual ambiente?",
            opcoes=[DecisionOption(id="opcao-staging", descricao="Opção de staging")],
            escalation_policy=_politica(),
            dados={"ambiente": "staging"},
        )

        resolucao = catalogo.consultar(ponto)

        assert resolucao is not None
        assert resolucao.opcao.id == "opcao-staging"

    def test_regra_com_condition_nao_casa_quando_dados_do_ponto_nao_satisfazem(self) -> None:
        regra = self._regra_com_condition("qual ambiente?")
        catalogo = CatalogoDeRegrasComoBaseConhecimento([regra])
        ponto = DecisionPoint(
            pergunta="qual ambiente?",
            opcoes=[DecisionOption(id="opcao-staging", descricao="Opção de staging")],
            escalation_policy=_politica(),
            dados={"ambiente": "producao"},
        )

        assert catalogo.consultar(ponto) is None

    def test_ponto_sem_dados_usa_dict_vazio_por_padrao(self) -> None:
        ponto = DecisionPoint(
            pergunta="x",
            opcoes=[DecisionOption(id="a", descricao="A")],
            escalation_policy=_politica(),
        )
        assert ponto.dados == {}
