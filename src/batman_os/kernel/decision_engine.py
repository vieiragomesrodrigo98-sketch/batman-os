"""Vol. II, Cap. 8 — Decision Engine.

Resolve `DecisionPoint`s gerados pelo Planning Engine, formalizando em código
a hierarquia Knowledge First → Human Last → LLM Last (Cap.2, secao 2.5). O
componente mais crítico do Kernel do ponto de vista filosófico: é aqui que a
promessa "Batman não depende continuamente de LLM" se torna verificável.

Fonte da verdade: docs/spec/02-kernel/04-decision-engine.md
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from batman_os.foundation.types import (
    DecisionId,
    DecisionOption,
    DecisionPointId,
    Evidence,
    MissionId,
    Reversibilidade,
    Timestamp,
    agora,
    novo_uuid7,
)
from batman_os.kernel.planning_engine import DecisionPoint

ResolvedBy = Literal["knowledge", "human", "llm"]


class KnowledgeAssetDraft(BaseModel):
    """Vol.II Cap.8, secao 8.3 (`Decision.knowledgeAssetCandidate`) — rascunho
    minimo; o formato completo de promocao a Knowledge Asset e do Learning
    Engine (Volume VI, fora de escopo desta construcao)."""

    descricao: str
    dados: dict[str, Any] = Field(default_factory=dict)


class Decision(BaseModel):
    """Vol.II Cap.8, secao 8.3."""

    id: DecisionId = Field(default_factory=lambda: DecisionId(novo_uuid7()))
    decision_point_id: DecisionPointId
    mission_id: MissionId
    resolved_by: ResolvedBy
    chosen_option: DecisionOption
    confidence: float
    evidence: list[Evidence]
    resolved_at: Timestamp = Field(default_factory=agora)
    knowledge_asset_candidate: KnowledgeAssetDraft | None = None


class EvidenciaObrigatoria(Exception):
    """AT-8.1 — nenhuma Decision pode existir com `evidence: []`, mesmo
    quando resolvida por conhecimento estruturado com alta confiança."""


class ResolucaoConhecimento(BaseModel):
    """Vol.II Cap.8, secao 8.2 — resultado de consultar a Knowledge Base
    (regras ativas) para um DecisionPoint."""

    opcao: DecisionOption
    confidence: float
    evidencia: list[Evidence]


class RespostaLlmCandidata(BaseModel):
    """Vol.II Cap.8, secao 8.5 — resposta crua do LLM Gateway, ainda nao
    validada contra contrato."""

    opcao: DecisionOption
    confidence: float
    evidencia_bruta: str


class LlmGatewayIndisponivel(Exception):
    """Vol.II Cap.8, secao 8.7 — infraestrutura do LLM Gateway fora do ar.
    Tratamento: escalar direto para humano, independente de `preferredEscalation`."""


class BaseConhecimento(Protocol):
    """Vol.II Cap.8, secao 8.2. Implementada de verdade pelo Rule Evolution/
    Knowledge Base (Volume VI, Cap.24 — fora de escopo desta construcao);
    aqui apenas o contrato que o Decision Engine consome."""

    def consultar(self, ponto: DecisionPoint) -> ResolucaoConhecimento | None: ...


class LlmGateway(Protocol):
    """Vol.II Cap.8, secao 8.5 / Vol.III Cap.12 — LLM Gateway isolado e
    periferico (ADR-0001, Volume I). Levanta `LlmGatewayIndisponivel` quando
    a infraestrutura estiver fora do ar."""

    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata: ...


class ValidadorContrato(Protocol):
    """Vol.II Cap.8, secao 8.2, nota critica — toda resposta de LLM passa por
    este validador antes de poder virar uma Decision."""

    def validar(self, ponto: DecisionPoint, resposta: RespostaLlmCandidata) -> bool: ...


class ResultadoResolucao(BaseModel):
    """Ou a Decision foi resolvida (autonomamente ou via LLM validado), ou o
    DecisionPoint precisa ser escalado — cabe ao Mission Runtime (Cap.6)
    transicionar a Missao para `AwaitingHuman`/`AwaitingLLM` a partir daqui."""

    decision: Decision | None = None
    escalonado_para: Literal["human"] | None = None


class DecisionEngine:
    """Vol.II Cap.8 — implementa o fluxograma da secao 8.2."""

    def __init__(
        self,
        base_conhecimento: BaseConhecimento,
        llm_gateway: LlmGateway,
        validador: ValidadorContrato,
    ) -> None:
        self._base_conhecimento = base_conhecimento
        self._llm_gateway = llm_gateway
        self._validador = validador
        self._decisoes: dict[DecisionId, Decision] = {}
        self._total_decisoes = 0
        self._decisoes_via_llm = 0

    def resolve(self, ponto: DecisionPoint, mission_id: MissionId) -> ResultadoResolucao:
        """Vol.II Cap.8, secao 8.2 — tenta resolver via conhecimento
        estruturado primeiro (Knowledge First); se a confianca for
        insuficiente, escala conforme `escalation_policy.preferred_escalation`.
        """
        resolucao = self._base_conhecimento.consultar(ponto)
        if (
            resolucao is not None
            and resolucao.confidence >= ponto.escalation_policy.confidence_threshold
        ):
            decision = self._registrar_decision(
                ponto,
                mission_id,
                resolved_by="knowledge",
                opcao=resolucao.opcao,
                confidence=resolucao.confidence,
                evidencia=resolucao.evidencia,
            )
            return ResultadoResolucao(decision=decision)

        if ponto.escalation_policy.preferred_escalation == "llm":
            decisao_llm = self._tentar_llm(ponto, mission_id)
            if decisao_llm is not None:
                return ResultadoResolucao(decision=decisao_llm)

        # LLM esgotado/indisponivel/reprovado, ou politica preferia humano
        # desde o inicio — Human Last continua sendo o fundo do poco, nunca
        # "sem resolucao" (secao 8.7).
        return ResultadoResolucao(escalonado_para="human")

    def resolver_com_resposta_humana(
        self,
        ponto: DecisionPoint,
        mission_id: MissionId,
        opcao_escolhida: DecisionOption,
        evidencia: list[Evidence],
    ) -> Decision:
        """Vol.II Cap.8, secao 8.2 — quando a resposta humana chega (Mission
        Runtime: `AwaitingHuman` -> `Deciding`), a decisao e registrada e
        marcada como candidata a Knowledge Asset (Principio 7, Learn Forever:
        toda escalacao humana e evento de aquisicao de conhecimento)."""
        return self._registrar_decision(
            ponto,
            mission_id,
            resolved_by="human",
            opcao=opcao_escolhida,
            confidence=1.0,
            evidencia=evidencia,
        )

    def taxa_llm(self) -> float:
        """Vol.II Cap.8, secao 8.6 (AT-8.4) — dado bruto monitoravel de
        quanto o sistema depende de LLM. A decisao de alarmar/notificar o
        Governance Engine a partir deste numero e do Volume VII (fora de
        escopo desta construcao) — aqui apenas o numero em si, sempre
        disponivel e recalculavel."""
        if self._total_decisoes == 0:
            return 0.0
        return self._decisoes_via_llm / self._total_decisoes

    def _tentar_llm(self, ponto: DecisionPoint, mission_id: MissionId) -> Decision | None:
        """Vol.II Cap.8, secao 8.6 — ate `maxLlmRetries` tentativas; nunca
        insiste indefinidamente. Secao 8.7 — Gateway indisponivel escala
        direto para humano. AT-8.3 — decisao irreversivel nunca e aplicada
        via LLM, mesmo validada, sem aprovacao humana intermediaria."""
        politica = ponto.escalation_policy
        for _ in range(politica.max_llm_retries):
            try:
                resposta = self._llm_gateway.consultar(ponto)
            except LlmGatewayIndisponivel:
                return None

            if not self._validador.validar(ponto, resposta):
                continue

            if politica.reversibility == Reversibilidade.IRREVERSIVEL:
                return None

            return self._registrar_decision(
                ponto,
                mission_id,
                resolved_by="llm",
                opcao=resposta.opcao,
                confidence=resposta.confidence,
                evidencia=[
                    Evidence(
                        origem="llm-gateway",
                        evidencias=[resposta.evidencia_bruta],
                        confianca=resposta.confidence,
                    )
                ],
            )
        return None

    def _registrar_decision(
        self,
        ponto: DecisionPoint,
        mission_id: MissionId,
        resolved_by: ResolvedBy,
        opcao: DecisionOption,
        confidence: float,
        evidencia: list[Evidence],
    ) -> Decision:
        if not evidencia:
            raise EvidenciaObrigatoria(
                f"Decision para DecisionPoint {ponto.id} nao pode ser "
                "registrada sem evidencia (AT-8.1, Evidence First)"
            )

        decision = Decision(
            decision_point_id=ponto.id,
            mission_id=mission_id,
            resolved_by=resolved_by,
            chosen_option=opcao,
            confidence=confidence,
            evidence=evidencia,
            knowledge_asset_candidate=(
                KnowledgeAssetDraft(
                    descricao=f"Decisao '{ponto.pergunta}' resolvida por {resolved_by}"
                )
                if resolved_by != "knowledge"
                else None
            ),
        )
        self._decisoes[decision.id] = decision
        self._total_decisoes += 1
        if resolved_by == "llm":
            self._decisoes_via_llm += 1
        return decision
