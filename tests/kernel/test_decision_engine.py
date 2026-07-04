"""Testes da Decision Engine (Vol.II Cap.8) — AT-8.1 a AT-8.4."""

from __future__ import annotations

from typing import Literal

import pytest

from batman_os.foundation.types import (
    DecisionOption,
    EscalationPolicy,
    Evidence,
    MissionId,
    Reversibilidade,
)
from batman_os.kernel.decision_engine import (
    DecisionEngine,
    EvidenciaObrigatoria,
    LlmGatewayIndisponivel,
    ResolucaoConhecimento,
    RespostaLlmCandidata,
    ValidadorContrato,
)
from batman_os.kernel.planning_engine import DecisionPoint

MISSAO = MissionId("m-1")


def _ponto(
    confidence_threshold: float = 0.8,
    preferred_escalation: Literal["human", "llm"] = "llm",
    max_llm_retries: int = 3,
    reversibility: Reversibilidade = Reversibilidade.REVERSIVEL,
) -> DecisionPoint:
    return DecisionPoint(
        pergunta="qual estrategia aplicar?",
        opcoes=[DecisionOption(id="a", descricao="opcao A")],
        escalation_policy=EscalationPolicy(
            confidence_threshold=confidence_threshold,
            preferred_escalation=preferred_escalation,
            max_llm_retries=max_llm_retries,
            reversibility=reversibility,
        ),
    )


class ConhecimentoFake:
    def __init__(self, resolucao: ResolucaoConhecimento | None) -> None:
        self._resolucao = resolucao

    def consultar(self, ponto: DecisionPoint) -> ResolucaoConhecimento | None:
        del ponto
        return self._resolucao


class LlmFake:
    def __init__(self, respostas: list[RespostaLlmCandidata | Exception]) -> None:
        self._respostas = list(respostas)

    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        del ponto
        item = self._respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class ValidadorSempreAprova:
    def validar(self, ponto: DecisionPoint, resposta: RespostaLlmCandidata) -> bool:
        del ponto, resposta
        return True


class ValidadorSempreReprova:
    def validar(self, ponto: DecisionPoint, resposta: RespostaLlmCandidata) -> bool:
        del ponto, resposta
        return False


def _engine(
    conhecimento: ResolucaoConhecimento | None = None,
    llm_respostas: list[RespostaLlmCandidata | Exception] | None = None,
    validador: ValidadorContrato | None = None,
) -> DecisionEngine:
    return DecisionEngine(
        base_conhecimento=ConhecimentoFake(conhecimento),
        llm_gateway=LlmFake(llm_respostas or []),
        validador=validador or ValidadorSempreAprova(),
    )


class TestAT81EvidenciaObrigatoria:
    def test_conhecimento_com_confianca_alta_mas_sem_evidencia_falha(self) -> None:
        engine = _engine(
            conhecimento=ResolucaoConhecimento(
                opcao=DecisionOption(id="a", descricao="A"), confidence=0.99, evidencia=[]
            )
        )
        with pytest.raises(EvidenciaObrigatoria):
            engine.resolve(_ponto(), MISSAO)

    def test_resolucao_com_evidencia_funciona(self) -> None:
        engine = _engine(
            conhecimento=ResolucaoConhecimento(
                opcao=DecisionOption(id="a", descricao="A"),
                confidence=0.99,
                evidencia=[Evidence(origem="regra-r17", evidencias=["incidente #4821"])],
            )
        )
        resultado = engine.resolve(_ponto(), MISSAO)

        assert resultado.decision is not None
        assert resultado.decision.evidence


class TestAT82DecisionLlmSempreValidada:
    def test_decision_llm_so_existe_apos_validacao_aprovada(self) -> None:
        engine = _engine(
            conhecimento=None,
            llm_respostas=[
                RespostaLlmCandidata(
                    opcao=DecisionOption(id="a", descricao="A"),
                    confidence=0.9,
                    evidencia_bruta="raciocinio",
                )
            ],
            validador=ValidadorSempreAprova(),
        )
        resultado = engine.resolve(_ponto(preferred_escalation="llm"), MISSAO)

        assert resultado.decision is not None
        assert resultado.decision.resolved_by == "llm"

    def test_resposta_reprovada_na_validacao_nao_vira_decision_llm(self) -> None:
        engine = _engine(
            conhecimento=None,
            llm_respostas=[
                RespostaLlmCandidata(
                    opcao=DecisionOption(id="a", descricao="A"), confidence=0.9, evidencia_bruta="x"
                )
                for _ in range(3)
            ],
            validador=ValidadorSempreReprova(),
        )
        resultado = engine.resolve(_ponto(preferred_escalation="llm", max_llm_retries=3), MISSAO)

        assert resultado.decision is None
        assert resultado.escalonado_para == "human"


class TestAT83IrreversivelNuncaViaLlmSemHumano:
    def test_decisao_irreversivel_nunca_resolvida_por_llm_mesmo_validada(self) -> None:
        engine = _engine(
            conhecimento=None,
            llm_respostas=[
                RespostaLlmCandidata(
                    opcao=DecisionOption(id="a", descricao="A"),
                    confidence=0.95,
                    evidencia_bruta="x",
                )
            ],
            validador=ValidadorSempreAprova(),
        )
        resultado = engine.resolve(
            _ponto(
                preferred_escalation="llm",
                reversibility=Reversibilidade.IRREVERSIVEL,
                max_llm_retries=1,
            ),
            MISSAO,
        )

        assert resultado.decision is None
        assert resultado.escalonado_para == "human"


class TestAT84TaxaDeEscalonamentoMonitoravel:
    def test_taxa_llm_reflete_proporcao_de_decisoes_via_llm(self) -> None:
        engine = _engine(
            conhecimento=ResolucaoConhecimento(
                opcao=DecisionOption(id="a", descricao="A"),
                confidence=0.99,
                evidencia=[Evidence(origem="r", evidencias=["e"])],
            )
        )
        engine.resolve(_ponto(confidence_threshold=0.5), MISSAO)
        engine.resolve(_ponto(confidence_threshold=0.5), MISSAO)

        assert engine.taxa_llm() == 0.0

    def test_taxa_llm_zero_sem_nenhuma_decisao(self) -> None:
        engine = _engine()
        assert engine.taxa_llm() == 0.0


class TestGatewayIndisponivel:
    def test_gateway_indisponivel_escala_direto_para_humano(self) -> None:
        engine = _engine(
            conhecimento=None,
            llm_respostas=[LlmGatewayIndisponivel("fora do ar")],
        )
        resultado = engine.resolve(_ponto(preferred_escalation="llm"), MISSAO)

        assert resultado.decision is None
        assert resultado.escalonado_para == "human"


class TestResolverComRespostaHumana:
    def test_resposta_humana_gera_decision_marcada_como_candidata(self) -> None:
        engine = _engine()
        ponto = _ponto()
        decision = engine.resolver_com_resposta_humana(
            ponto,
            MISSAO,
            opcao_escolhida=DecisionOption(id="a", descricao="A"),
            evidencia=[Evidence(origem="humano", evidencias=["decisao manual"])],
        )

        assert decision.resolved_by == "human"
        assert decision.knowledge_asset_candidate is not None

    def test_resposta_humana_sem_evidencia_falha(self) -> None:
        engine = _engine()
        with pytest.raises(EvidenciaObrigatoria):
            engine.resolver_com_resposta_humana(
                _ponto(),
                MISSAO,
                opcao_escolhida=DecisionOption(id="a", descricao="A"),
                evidencia=[],
            )
