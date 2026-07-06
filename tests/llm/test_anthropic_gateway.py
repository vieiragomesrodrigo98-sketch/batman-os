"""Testes do AnthropicLlmGateway (Milestone 6) — 100% com fakes, ZERO
chamada real à API Anthropic, ZERO custo. Nenhum teste deste módulo
requer `ANTHROPIC_API_KEY` real."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from batman_os.foundation.types import DecisionOption, EscalationPolicy, Reversibilidade
from batman_os.kernel.decision_engine import LlmGatewayIndisponivel
from batman_os.kernel.planning_engine import DecisionPoint
from batman_os.llm.anthropic_gateway import AnthropicLlmGateway
from batman_os.llm.cost_tracker import CostTracker
from batman_os.llm.settings import Settings


def _ponto() -> DecisionPoint:
    return DecisionPoint(
        pergunta="qual acao tomar para o timeout do Gunicorn?",
        opcoes=[
            DecisionOption(id="aumentar-timeout", descricao="Aumentar worker timeout"),
            DecisionOption(id="reiniciar", descricao="Reiniciar o processo"),
        ],
        escalation_policy=EscalationPolicy(
            confidence_threshold=0.8,
            preferred_escalation="llm",
            max_llm_retries=2,
            reversibility=Reversibilidade.REVERSIVEL,
        ),
    )


class _FakeUsage:
    def __init__(
        self,
        input_tokens: int = 100,
        output_tokens: int = 50,
        cache_creation_input_tokens: int | None = 0,
        cache_read_input_tokens: int | None = 0,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens
        self.cache_read_input_tokens = cache_read_input_tokens


class _FakeContentBlock:
    def __init__(self, type_: str, input_: dict[str, Any] | None = None) -> None:
        self.type = type_
        self.input = input_ or {}


class _FakeResponse:
    def __init__(self, content: list[_FakeContentBlock], usage: _FakeUsage | None = None) -> None:
        self.content = content
        self.usage = usage


def _resposta_tool_use_valida() -> _FakeResponse:
    return _FakeResponse(
        content=[
            _FakeContentBlock(
                "tool_use",
                {
                    "opcao": {"id": "aumentar-timeout", "descricao": "Aumentar worker timeout"},
                    "confidence": 0.92,
                    "evidencia_bruta": "Padrao recorrente de timeout sob carga alta",
                },
            )
        ],
        usage=_FakeUsage(input_tokens=500, output_tokens=80),
    )


class _FakeMessages:
    def __init__(self, respostas: list[_FakeResponse | Exception]) -> None:
        self._respostas = list(respostas)
        self.chamadas: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeResponse:
        self.chamadas.append(kwargs)
        item = self._respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _FakeAnthropicClient:
    def __init__(self, respostas: list[_FakeResponse | Exception]) -> None:
        self.messages = _FakeMessages(respostas)


def _tracker(tmp_path: Path, max_daily_llm_cost_usd: float = 10.0) -> CostTracker:
    return CostTracker(
        ledger_path=tmp_path / "llm_cost.jsonl",
        settings=Settings(max_daily_llm_cost_usd=max_daily_llm_cost_usd),
    )


def _gateway(
    tmp_path: Path,
    client: _FakeAnthropicClient,
    max_daily_llm_cost_usd: float = 10.0,
) -> AnthropicLlmGateway:
    return AnthropicLlmGateway(
        settings=Settings(max_daily_llm_cost_usd=max_daily_llm_cost_usd),
        cost_tracker=_tracker(tmp_path, max_daily_llm_cost_usd),
        client=client,  # type: ignore[arg-type]
        tentativas_max=2,
        espera_minima=0.0,
        espera_maxima=0.01,
    )


class TestConsultaBemSucedida:
    def test_retorna_resposta_llm_candidata_valida(self, tmp_path: Path) -> None:
        client = _FakeAnthropicClient([_resposta_tool_use_valida()])
        gateway = _gateway(tmp_path, client)

        resultado = gateway.consultar(_ponto())

        assert resultado.opcao.id == "aumentar-timeout"
        assert resultado.confidence == 0.92
        assert resultado.evidencia_bruta

    def test_forca_tool_choice_e_schema(self, tmp_path: Path) -> None:
        client = _FakeAnthropicClient([_resposta_tool_use_valida()])
        gateway = _gateway(tmp_path, client)

        gateway.consultar(_ponto())

        chamada = client.messages.chamadas[0]
        assert chamada["tool_choice"] == {"type": "tool", "name": "resolver_decision_point"}
        assert chamada["tools"][0]["input_schema"].get("$defs") is None  # $refs resolvidos

    def test_aplica_cache_control_no_bloco_system(self, tmp_path: Path) -> None:
        client = _FakeAnthropicClient([_resposta_tool_use_valida()])
        gateway = _gateway(tmp_path, client)

        gateway.consultar(_ponto())

        chamada = client.messages.chamadas[0]
        assert chamada["system"][0]["cache_control"] == {"type": "ephemeral"}

    def test_registra_custo_no_cost_tracker(self, tmp_path: Path) -> None:
        client = _FakeAnthropicClient([_resposta_tool_use_valida()])
        gateway = _gateway(tmp_path, client)

        gateway.consultar(_ponto())

        assert (tmp_path / "llm_cost.jsonl").exists()


class TestRetryTransitorio:
    def test_erro_transitorio_seguido_de_sucesso_retorna_resposta(self, tmp_path: Path) -> None:
        client = _FakeAnthropicClient(
            [ConnectionError("timeout de rede"), _resposta_tool_use_valida()]
        )
        gateway = _gateway(tmp_path, client)

        resultado = gateway.consultar(_ponto())

        assert resultado.opcao.id == "aumentar-timeout"
        assert len(client.messages.chamadas) == 2

    def test_erro_transitorio_esgota_retries_levanta_indisponivel(self, tmp_path: Path) -> None:
        client = _FakeAnthropicClient([ConnectionError("timeout 1"), ConnectionError("timeout 2")])
        gateway = _gateway(tmp_path, client)

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())


class TestErroDeLimiteDeConta:
    def test_erro_de_limite_nao_e_re_tentado(self, tmp_path: Path) -> None:
        client = _FakeAnthropicClient(
            [RuntimeError("You have reached your specified API usage limits.")]
        )
        gateway = _gateway(tmp_path, client)

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

        assert len(client.messages.chamadas) == 1  # nao re-tentou

    def test_apos_limite_detectado_proxima_chamada_nao_faz_round_trip(self, tmp_path: Path) -> None:
        client = _FakeAnthropicClient(
            [
                RuntimeError("You have reached your specified API usage limits."),
                _resposta_tool_use_valida(),  # nunca deveria ser consumida
            ]
        )
        gateway = _gateway(tmp_path, client)

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

        assert len(client.messages.chamadas) == 1  # segunda chamada nunca tocou o client


class TestOrcamentoExcedido:
    def test_orcamento_excedido_bloqueia_sem_tocar_o_client(self, tmp_path: Path) -> None:
        client = _FakeAnthropicClient([_resposta_tool_use_valida()])
        gateway = AnthropicLlmGateway(
            settings=Settings(max_daily_llm_cost_usd=0.0000001),
            cost_tracker=_tracker(tmp_path, max_daily_llm_cost_usd=0.0000001),
            client=client,  # type: ignore[arg-type]
        )
        # simula gasto ja acima do teto
        gateway._cost_tracker.registrar(  # noqa: SLF001
            model="claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=1_000_000
        )

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

        assert client.messages.chamadas == []


class TestRespostaSemToolUse:
    def test_resposta_sem_bloco_tool_use_levanta_indisponivel(self, tmp_path: Path) -> None:
        client = _FakeAnthropicClient(
            [_FakeResponse(content=[_FakeContentBlock("text", None)], usage=_FakeUsage())]
        )
        gateway = _gateway(tmp_path, client)

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())


class TestSatisfazLlmGatewayProtocol:
    def test_gateway_e_utilizavel_pelo_decision_engine(self, tmp_path: Path) -> None:
        from batman_os.kernel.decision_engine import DecisionEngine

        client = _FakeAnthropicClient([_resposta_tool_use_valida()])
        gateway = _gateway(tmp_path, client)

        class _ConhecimentoVazio:
            def consultar(self, ponto: DecisionPoint) -> None:
                del ponto
                return None

        class _ValidadorSempreAprova:
            def validar(self, ponto: DecisionPoint, resposta: Any) -> bool:
                del ponto, resposta
                return True

        from batman_os.foundation.types import MissionId

        engine = DecisionEngine(
            base_conhecimento=_ConhecimentoVazio(),
            llm_gateway=gateway,
            validador=_ValidadorSempreAprova(),
        )
        resultado = engine.resolve(_ponto(), MissionId("m-1"))

        assert resultado.decision is not None
        assert resultado.decision.resolved_by == "llm"
