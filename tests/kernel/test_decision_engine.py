"""Testes da Decision Engine (Vol.II Cap.8) — AT-8.1 a AT-8.4."""

from __future__ import annotations

import threading
from typing import Literal

import pytest

from batman_os.foundation.types import (
    DecisionOption,
    EscalationPolicy,
    Evidence,
    MissionId,
    Reversibilidade,
)
from batman_os.governance.llm_escalation import LLMEscalationPolicy, PolicyId, RatePolicy
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
    llm_escalation_policy: LLMEscalationPolicy | None = None,
) -> DecisionEngine:
    return DecisionEngine(
        base_conhecimento=ConhecimentoFake(conhecimento),
        llm_gateway=LlmFake(llm_respostas or []),
        validador=validador or ValidadorSempreAprova(),
        llm_escalation_policy=llm_escalation_policy,
    )


def _politica_llm(
    max_retries_per_decision_point: int = 3,
    requires_human_co_approval: Literal["always", "irreversible-only", "never"] = (
        "irreversible-only"
    ),
) -> LLMEscalationPolicy:
    return LLMEscalationPolicy(
        id=PolicyId("policy-1"),
        version="1.0.0",
        scope="global",
        max_retries_per_decision_point=max_retries_per_decision_point,
        circuit_breaker_threshold=RatePolicy(taxa_maxima=0.5, tamanho_janela=100),
        requires_human_co_approval=requires_human_co_approval,
        output_validation_level="schema-only",
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


class TestFase2Estagio24ContadoresSobConcorrencia:
    """Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-wondering-
    hearth.md`), Estagio 2.4 — achado ao habilitar processamento concorrente
    de Missoes em `cli/scan_command.py`: `_total_decisoes`/`_decisoes_via_
    llm` usavam `+=` sem lock, um read-modify-write nao atomico que perdia
    incrementos sob chamadas concorrentes ao MESMO DecisionEngine
    (compartilhado entre Missoes no scan)."""

    def test_resolve_concorrente_nao_perde_nenhum_incremento(self) -> None:
        engine = _engine(
            conhecimento=ResolucaoConhecimento(
                opcao=DecisionOption(id="a", descricao="A"),
                confidence=0.99,
                evidencia=[Evidence(origem="r", evidencias=["e"])],
            )
        )
        n_threads = 20

        def _resolver() -> None:
            engine.resolve(_ponto(confidence_threshold=0.5), MISSAO)

        threads = [threading.Thread(target=_resolver) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(engine._decisoes) == n_threads
        assert engine._total_decisoes == n_threads


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


class TestMilestone4LlmEscalationPolicyConsultadaDeVerdade:
    """Achado de revisão fechado na Milestone 4: antes, `max_llm_retries`/
    reversibilidade vinham só de `EscalationPolicy` (ad-hoc, por
    DecisionPoint) — nenhuma `LLMEscalationPolicy` real (Cap.29) era
    consultada. A política só pode RESTRINGIR, nunca afrouxar."""

    def test_politica_reduz_o_teto_de_retries_abaixo_do_da_escalation_policy(self) -> None:
        engine = _engine(
            conhecimento=None,
            llm_respostas=[
                RespostaLlmCandidata(
                    opcao=DecisionOption(id="a", descricao="A"), confidence=0.9, evidencia_bruta="x"
                )
                for _ in range(5)
            ],
            validador=ValidadorSempreReprova(),
            llm_escalation_policy=_politica_llm(max_retries_per_decision_point=2),
        )
        resultado = engine.resolve(_ponto(preferred_escalation="llm", max_llm_retries=5), MISSAO)

        assert resultado.decision is None
        assert resultado.escalonado_para == "human"

    def test_politica_nao_aumenta_o_teto_de_retries_alem_da_escalation_policy(self) -> None:
        """`EscalationPolicy.max_llm_retries=1` continua sendo o teto real
        mesmo se a politica de governanca permitisse mais - a politica so
        restringe, nunca afrouxa."""
        engine = _engine(
            conhecimento=None,
            llm_respostas=[
                RespostaLlmCandidata(
                    opcao=DecisionOption(id="a", descricao="A"), confidence=0.9, evidencia_bruta="x"
                )
            ],
            validador=ValidadorSempreAprova(),
            llm_escalation_policy=_politica_llm(max_retries_per_decision_point=10),
        )
        resultado = engine.resolve(_ponto(preferred_escalation="llm", max_llm_retries=1), MISSAO)

        assert resultado.decision is not None
        assert resultado.decision.resolved_by == "llm"

    def test_requires_human_co_approval_always_escala_mesmo_decisao_reversivel(self) -> None:
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
            llm_escalation_policy=_politica_llm(requires_human_co_approval="always"),
        )
        resultado = engine.resolve(
            _ponto(
                preferred_escalation="llm",
                reversibility=Reversibilidade.REVERSIVEL,
                max_llm_retries=1,
            ),
            MISSAO,
        )

        assert resultado.decision is None
        assert resultado.escalonado_para == "human"

    def test_sem_politica_de_governanca_comportamento_e_identico_ao_anterior(self) -> None:
        engine = _engine(
            conhecimento=None,
            llm_respostas=[
                RespostaLlmCandidata(
                    opcao=DecisionOption(id="a", descricao="A"), confidence=0.9, evidencia_bruta="x"
                )
            ],
            validador=ValidadorSempreAprova(),
            llm_escalation_policy=None,
        )
        resultado = engine.resolve(_ponto(preferred_escalation="llm", max_llm_retries=1), MISSAO)

        assert resultado.decision is not None
        assert resultado.decision.resolved_by == "llm"

    def test_irreversivel_continua_escalando_mesmo_com_requires_human_co_approval_never(
        self,
    ) -> None:
        """AT-8.3 e incondicional - uma politica de governanca 'never' nao
        pode afrouxar a garantia arquitetural ja existente."""
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
            llm_escalation_policy=_politica_llm(requires_human_co_approval="never"),
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
