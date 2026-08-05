"""Testes de FallbackLlmGateway/ShadowLlmGateway/construir_llm_gateway —
100% com gateways/motores fake, ZERO rede, ZERO GGUF."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from batman_os.foundation.types import DecisionOption, EscalationPolicy, Reversibilidade
from batman_os.kernel.decision_engine import LlmGatewayIndisponivel, RespostaLlmCandidata
from batman_os.kernel.planning_engine import DecisionPoint
from batman_os.llm.anthropic_gateway import AnthropicLlmGateway
from batman_os.llm.cost_tracker import CostTracker
from batman_os.llm.fallback_gateway import (
    FallbackLlmGateway,
    ShadowLlmGateway,
    construir_llm_gateway,
)
from batman_os.llm.local_gateway import LocalLlmGateway, ResultadoMotorLocal
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


def _resposta(opcao_id: str = "aumentar-timeout", confidence: float = 0.9) -> RespostaLlmCandidata:
    return RespostaLlmCandidata(
        opcao=DecisionOption(id=opcao_id, descricao="Aumentar worker timeout"),
        confidence=confidence,
        evidencia_bruta="raciocinio",
    )


class _GatewayFake:
    def __init__(self, respostas: list[RespostaLlmCandidata | Exception]) -> None:
        self._respostas = list(respostas)
        self.chamadas = 0

    def consultar(self, ponto: DecisionPoint) -> RespostaLlmCandidata:
        del ponto
        self.chamadas += 1
        item = self._respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _linhas(path: Path) -> list[dict[str, Any]]:
    return [json.loads(linha) for linha in path.read_text(encoding="utf-8").strip().splitlines()]


class TestFallback:
    def test_primario_ok_nao_toca_o_secundario(self, tmp_path: Path) -> None:
        primario = _GatewayFake([_resposta()])
        secundario = _GatewayFake([_resposta("reiniciar")])
        telemetria = tmp_path / "gateway_calls.jsonl"
        gateway = FallbackLlmGateway(primario, secundario, telemetria)

        resultado = gateway.consultar(_ponto())

        assert resultado.opcao.id == "aumentar-timeout"
        assert secundario.chamadas == 0
        registro = _linhas(telemetria)[0]
        assert registro["provedor_respondeu"] == "primario"
        assert registro["motivo_fallback"] is None
        assert registro["ponto"] is None  # flywheel so grava o ponto no fallback

    def test_primario_indisponivel_cai_para_o_secundario(self, tmp_path: Path) -> None:
        primario = _GatewayFake([LlmGatewayIndisponivel("confianca local insuficiente")])
        secundario = _GatewayFake([_resposta("reiniciar")])
        telemetria = tmp_path / "gateway_calls.jsonl"
        gateway = FallbackLlmGateway(primario, secundario, telemetria)

        resultado = gateway.consultar(_ponto())

        assert resultado.opcao.id == "reiniciar"
        registro = _linhas(telemetria)[0]
        assert registro["provedor_respondeu"] == "secundario"
        assert "confianca local insuficiente" in registro["motivo_fallback"]
        # insumo do flywheel de treino: ponto e resposta completos
        assert registro["ponto"]["pergunta"] == "qual acao tomar para o timeout do Gunicorn?"
        assert registro["resposta"]["opcao"]["id"] == "reiniciar"

    def test_ambos_indisponiveis_re_levanta_e_registra(self, tmp_path: Path) -> None:
        primario = _GatewayFake([LlmGatewayIndisponivel("local fora")])
        secundario = _GatewayFake([LlmGatewayIndisponivel("anthropic fora")])
        telemetria = tmp_path / "gateway_calls.jsonl"
        gateway = FallbackLlmGateway(primario, secundario, telemetria)

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

        assert _linhas(telemetria)[0]["provedor_respondeu"] == "nenhum"

    def test_sem_secundario_re_levanta_a_falha_original(self, tmp_path: Path) -> None:
        del tmp_path
        primario = _GatewayFake([LlmGatewayIndisponivel("local fora")])
        gateway = FallbackLlmGateway(primario)

        with pytest.raises(LlmGatewayIndisponivel, match="local fora"):
            gateway.consultar(_ponto())

    def test_sem_telemetria_path_funciona_normalmente(self) -> None:
        gateway = FallbackLlmGateway(_GatewayFake([_resposta()]))

        assert gateway.consultar(_ponto()).opcao.id == "aumentar-timeout"

    def test_falha_de_io_na_telemetria_nao_derruba_a_consulta(self, tmp_path: Path) -> None:
        # telemetria apontando para um DIRETORIO: open("a") falha com OSError
        gateway = FallbackLlmGateway(_GatewayFake([_resposta()]), telemetria_path=tmp_path)

        assert gateway.consultar(_ponto()).opcao.id == "aumentar-timeout"


class TestShadow:
    def test_oficial_decide_e_sombra_concordante_e_registrada(self, tmp_path: Path) -> None:
        shadow_path = tmp_path / "shadow_records.jsonl"
        gateway = ShadowLlmGateway(
            oficial=_GatewayFake([_resposta()]),
            sombra=_GatewayFake([_resposta(confidence=0.8)]),
            shadow_path=shadow_path,
        )

        resultado = gateway.consultar(_ponto())

        assert resultado.confidence == 0.9  # resposta do oficial, nao da sombra
        registro = _linhas(shadow_path)[0]
        assert registro["agreement"] is True
        assert registro["confidence_sombra"] == 0.8

    def test_sombra_discordante_e_registrada(self, tmp_path: Path) -> None:
        shadow_path = tmp_path / "shadow_records.jsonl"
        gateway = ShadowLlmGateway(
            oficial=_GatewayFake([_resposta()]),
            sombra=_GatewayFake([_resposta("reiniciar")]),
            shadow_path=shadow_path,
        )

        gateway.consultar(_ponto())

        registro = _linhas(shadow_path)[0]
        assert registro["agreement"] is False
        assert registro["opcao_oficial"] == "aumentar-timeout"
        assert registro["opcao_sombra"] == "reiniciar"

    def test_falha_da_sombra_nunca_propaga(self, tmp_path: Path) -> None:
        shadow_path = tmp_path / "shadow_records.jsonl"
        gateway = ShadowLlmGateway(
            oficial=_GatewayFake([_resposta()]),
            sombra=_GatewayFake([RuntimeError("sombra quebrou")]),
            shadow_path=shadow_path,
        )

        resultado = gateway.consultar(_ponto())

        assert resultado.opcao.id == "aumentar-timeout"
        registro = _linhas(shadow_path)[0]
        assert registro["agreement"] is None
        assert "sombra quebrou" in registro["erro_sombra"]

    def test_falha_do_oficial_propaga_sem_consultar_a_sombra(self, tmp_path: Path) -> None:
        del tmp_path
        sombra = _GatewayFake([_resposta()])
        gateway = ShadowLlmGateway(
            oficial=_GatewayFake([LlmGatewayIndisponivel("anthropic fora")]),
            sombra=sombra,
        )

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

        assert sombra.chamadas == 0


class _FakeMessages:
    def create(self, **kwargs: Any) -> Any:
        raise AssertionError("composicao nao deveria chamar a API")


class _FakeAnthropicClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


class _FakeMotor:
    def gerar(
        self, system: str, usuario: str, schema: dict[str, Any], timeout: float
    ) -> ResultadoMotorLocal:
        raise AssertionError("composicao nao deveria gerar")


class TestConstruirLlmGateway:
    def _construir(self, tmp_path: Path, provider: str) -> Any:
        settings = Settings(llm_provider=provider, llm_local_gguf_path="fake.gguf")
        return construir_llm_gateway(
            settings=settings,
            cost_tracker=CostTracker(ledger_path=tmp_path / "c.jsonl", settings=settings),
            client_anthropic=_FakeAnthropicClient(),
            telemetria_dir=tmp_path,
            motor_local=_FakeMotor(),
        )

    def test_provider_anthropic_compoe_gateway_anthropic_puro(self, tmp_path: Path) -> None:
        assert isinstance(self._construir(tmp_path, "anthropic"), AnthropicLlmGateway)

    def test_provider_local_first_compoe_fallback(self, tmp_path: Path) -> None:
        gateway = self._construir(tmp_path, "local-first")

        assert isinstance(gateway, FallbackLlmGateway)
        assert isinstance(gateway._primario, LocalLlmGateway)  # noqa: SLF001
        assert isinstance(gateway._secundario, AnthropicLlmGateway)  # noqa: SLF001

    def test_provider_local_shadow_compoe_shadow(self, tmp_path: Path) -> None:
        gateway = self._construir(tmp_path, "local-shadow")

        assert isinstance(gateway, ShadowLlmGateway)
        assert isinstance(gateway._oficial, AnthropicLlmGateway)  # noqa: SLF001
        assert isinstance(gateway._sombra, LocalLlmGateway)  # noqa: SLF001

    def test_provider_local_only_compoe_sem_anthropic(self, tmp_path: Path) -> None:
        settings = Settings(llm_provider="local-only", llm_local_gguf_path="fake.gguf")
        gateway = construir_llm_gateway(
            settings=settings,
            cost_tracker=CostTracker(ledger_path=tmp_path / "c.jsonl", settings=settings),
            client_anthropic=None,  # local-only nunca deve precisar de cliente
            telemetria_dir=tmp_path,
            motor_local=_FakeMotor(),
        )

        assert isinstance(gateway, FallbackLlmGateway)
        assert isinstance(gateway._primario, LocalLlmGateway)  # noqa: SLF001
        assert gateway._secundario is None  # noqa: SLF001
