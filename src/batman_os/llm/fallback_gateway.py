"""Composição de gateways: fallback local-first e shadow mode (ADR-0011).

Três peças, todas satisfazendo o MESMO `LlmGateway` Protocol — o Decision
Engine consome qualquer uma sem saber a diferença:

- `FallbackLlmGateway`: tenta o primário; `LlmGatewayIndisponivel` aciona
  o secundário. Toda chamada vira uma linha de telemetria JSONL
  (best-effort, padrão `CostTracker.registrar`): quando o secundário
  (Anthropic) responde, o registro carrega o DecisionPoint e a resposta
  completos — é o flywheel de dados de treino do modelo local (cada
  fallback é um exemplo futuro rotulado pelo professor).
- `ShadowLlmGateway`: o oficial decide; a sombra roda best-effort só para
  medir concordância (`LlmShadowRecord`) — nunca propaga falha própria.
  Espelho consciente de `ShadowEvaluation` (`learning/rule_evolution.py`),
  que não é reutilizável aqui por ser acoplada a `RuleId`.
- `construir_llm_gateway`: mapeia `Settings.llm_provider` para a
  composição — o único lugar que os pontos de fiação (API, patrol futuro)
  devem chamar em vez de instanciar gateways diretamente.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from batman_os.foundation.types import Timestamp, agora
from batman_os.kernel.decision_engine import (
    LlmGateway,
    LlmGatewayIndisponivel,
    RespostaLlmCandidata,
)
from batman_os.kernel.planning_engine import DecisionPoint
from batman_os.llm.anthropic_gateway import (
    AnthropicLlmGateway,
    _ClienteAnthropicComoAssinatura,
)
from batman_os.llm.cost_tracker import CostTracker
from batman_os.llm.local_gateway import LocalLlmGateway, MotorLlmLocalComoAssinatura
from batman_os.llm.settings import Settings

ProvedorQueRespondeu = Literal["primario", "secundario", "nenhum"]


class RegistroChamadaLlm(BaseModel):
    """Uma linha de telemetria por chamada ao `FallbackLlmGateway`."""

    decision_point_id: str
    pergunta_hash: str
    provedor_respondeu: ProvedorQueRespondeu
    motivo_fallback: str | None = None
    opcao_id: str | None = None
    confidence: float | None = None
    latency_ms: float
    # Preenchidos apenas quando o secundário respondeu — insumo bruto do
    # flywheel de treino (Fonte C do plano).
    ponto: dict[str, Any] | None = None
    resposta: dict[str, Any] | None = None
    recorded_at: Timestamp = Field(default_factory=agora)


class LlmShadowRecord(BaseModel):
    """Uma linha por chamada em shadow mode: decisão oficial vs. sombra.
    `agreement is None` significa que a sombra falhou (ver `erro_sombra`)."""

    decision_point_id: str
    opcao_oficial: str
    opcao_sombra: str | None = None
    agreement: bool | None = None
    confidence_sombra: float | None = None
    erro_sombra: str | None = None
    latency_ms_sombra: float
    recorded_at: Timestamp = Field(default_factory=agora)


def _hash_pergunta(ponto: DecisionPoint) -> str:
    return hashlib.sha256(ponto.pergunta.encode("utf-8")).hexdigest()[:16]


def _gravar_jsonl(path: Path | None, registro: BaseModel) -> None:
    """Best-effort: telemetria nunca é motivo para uma consulta falhar."""
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(registro.model_dump_json() + "\n")
    except OSError:
        return


class FallbackLlmGateway:
    """Satisfaz `LlmGateway`. Sem secundário configurado, é um passthrough
    com telemetria."""

    def __init__(
        self,
        primario: LlmGateway,
        secundario: LlmGateway | None = None,
        telemetria_path: Path | None = None,
    ) -> None:
        self._primario = primario
        self._secundario = secundario
        self._telemetria_path = telemetria_path

    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        inicio = time.monotonic()
        try:
            resposta = self._primario.consultar(ponto)
        except LlmGatewayIndisponivel as exc_primario:
            if self._secundario is None:
                raise
            try:
                resposta = self._secundario.consultar(ponto)
            except LlmGatewayIndisponivel:
                self._registrar(ponto, None, "nenhum", str(exc_primario), inicio)
                raise
            self._registrar(ponto, resposta, "secundario", str(exc_primario), inicio)
            return resposta
        self._registrar(ponto, resposta, "primario", None, inicio)
        return resposta

    def _registrar(
        self,
        ponto: DecisionPoint,
        resposta: RespostaLlmCandidata | None,
        provedor: ProvedorQueRespondeu,
        motivo_fallback: str | None,
        inicio: float,
    ) -> None:
        registro = RegistroChamadaLlm(
            decision_point_id=str(ponto.id),
            pergunta_hash=_hash_pergunta(ponto),
            provedor_respondeu=provedor,
            motivo_fallback=motivo_fallback,
            opcao_id=resposta.opcao.id if resposta else None,
            confidence=resposta.confidence if resposta else None,
            latency_ms=(time.monotonic() - inicio) * 1000,
            ponto=(json.loads(ponto.model_dump_json()) if provedor == "secundario" else None),
            resposta=(
                json.loads(resposta.model_dump_json())
                if provedor == "secundario" and resposta
                else None
            ),
        )
        _gravar_jsonl(self._telemetria_path, registro)


class ShadowLlmGateway:
    """Satisfaz `LlmGateway`. Na composição `local-shadow`: oficial =
    Anthropic (fonte da verdade), sombra = local (só medição). Falha do
    oficial propaga normalmente; falha da sombra vira registro, nunca
    exceção."""

    def __init__(
        self,
        oficial: LlmGateway,
        sombra: LlmGateway,
        shadow_path: Path | None = None,
    ) -> None:
        self._oficial = oficial
        self._sombra = sombra
        self._shadow_path = shadow_path

    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        resposta = self._oficial.consultar(ponto)

        inicio = time.monotonic()
        try:
            resposta_sombra = self._sombra.consultar(ponto)
            registro = LlmShadowRecord(
                decision_point_id=str(ponto.id),
                opcao_oficial=resposta.opcao.id,
                opcao_sombra=resposta_sombra.opcao.id,
                agreement=resposta_sombra.opcao.id == resposta.opcao.id,
                confidence_sombra=resposta_sombra.confidence,
                latency_ms_sombra=(time.monotonic() - inicio) * 1000,
            )
        except Exception as exc:  # sombra jamais derruba a consulta
            registro = LlmShadowRecord(
                decision_point_id=str(ponto.id),
                opcao_oficial=resposta.opcao.id,
                erro_sombra=str(exc),
                latency_ms_sombra=(time.monotonic() - inicio) * 1000,
            )
        _gravar_jsonl(self._shadow_path, registro)
        return resposta


def construir_llm_gateway(
    settings: Settings,
    cost_tracker: CostTracker,
    client_anthropic: _ClienteAnthropicComoAssinatura | None = None,
    telemetria_dir: Path | None = None,
    motor_local: MotorLlmLocalComoAssinatura | None = None,
) -> LlmGateway:
    """Ponto único de composição, dirigido por `Settings.llm_provider`:

    - `"anthropic"` (default): comportamento atual, intocado.
    - `"local-first"`: local primeiro; `LlmGatewayIndisponivel` (timeout,
      JSON inválido, confiança baixa, GGUF ausente...) cai para Anthropic.
    - `"local-shadow"`: Anthropic decide; local roda em sombra e grava
      `LlmShadowRecord` para o relatório de promoção (ADR-0011).
    - `"local-only"`: SEM Anthropic na cadeia — o modelo local é o único
      LLM; falha vira `LlmGatewayIndisponivel` e o Decision Engine escala
      para humano (Vol.II Cap.8, secao 8.7). Nenhum cliente Anthropic é
      criado neste modo (roda em máquina sem chave).

    `client_anthropic` e `motor_local` são injetáveis para teste; em
    produção, omiti-los cria o cliente real (a chave vem de `Settings`) e
    o motor llama.cpp lazy."""

    def _anthropic() -> AnthropicLlmGateway:
        client = client_anthropic
        if client is None:
            import anthropic

            client = cast(
                _ClienteAnthropicComoAssinatura,
                anthropic.Anthropic(api_key=settings.anthropic_api_key),
            )
        return AnthropicLlmGateway(settings=settings, cost_tracker=cost_tracker, client=client)

    if settings.llm_provider == "anthropic":
        return _anthropic()

    local = LocalLlmGateway(settings=settings, cost_tracker=cost_tracker, motor=motor_local)
    if settings.llm_provider == "local-only":
        return FallbackLlmGateway(
            primario=local,
            secundario=None,
            telemetria_path=(telemetria_dir / "gateway_calls.jsonl" if telemetria_dir else None),
        )
    if settings.llm_provider == "local-first":
        return FallbackLlmGateway(
            primario=local,
            secundario=_anthropic(),
            telemetria_path=(telemetria_dir / "gateway_calls.jsonl" if telemetria_dir else None),
        )
    return ShadowLlmGateway(
        oficial=_anthropic(),
        sombra=local,
        shadow_path=(telemetria_dir / "shadow_records.jsonl" if telemetria_dir else None),
    )
