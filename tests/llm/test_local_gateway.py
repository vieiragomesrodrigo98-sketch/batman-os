"""Testes do LocalLlmGateway — 100% com motor fake, ZERO GGUF/GPU/rede.
Nenhum teste deste módulo requer llama-cpp-python instalado."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from batman_os.foundation.types import DecisionOption, EscalationPolicy, Reversibilidade
from batman_os.kernel.decision_engine import LlmGatewayIndisponivel
from batman_os.kernel.planning_engine import DecisionPoint
from batman_os.llm.cost_tracker import CostTracker
from batman_os.llm.local_gateway import (
    MODELO_LOCAL,
    LocalLlmGateway,
    ResultadoMotorLocal,
)
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


def _texto_valido(opcao_id: str = "aumentar-timeout", confidence: float = 0.92) -> str:
    return json.dumps(
        {
            "opcao": {"id": opcao_id, "descricao": "Aumentar worker timeout"},
            "confidence": confidence,
            "evidencia_bruta": "Padrao recorrente de timeout sob carga alta",
        }
    )


class _FakeMotor:
    """Espelho de `_FakeMessages` do teste do gateway Anthropic: fila de
    resultados/exceções + captura das chamadas para asserções."""

    def __init__(self, respostas: list[ResultadoMotorLocal | Exception]) -> None:
        self._respostas = list(respostas)
        self.chamadas: list[dict[str, Any]] = []

    def gerar(
        self, system: str, usuario: str, schema: dict[str, Any], timeout: float
    ) -> ResultadoMotorLocal:
        self.chamadas.append(
            {"system": system, "usuario": usuario, "schema": schema, "timeout": timeout}
        )
        item = self._respostas.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _settings(**kwargs: Any) -> Settings:
    return Settings(llm_local_gguf_path="modelo-fake.gguf", **kwargs)


def _gateway(
    tmp_path: Path, motor: _FakeMotor, settings: Settings | None = None
) -> LocalLlmGateway:
    settings = settings or _settings()
    return LocalLlmGateway(
        settings=settings,
        cost_tracker=CostTracker(ledger_path=tmp_path / "llm_cost.jsonl", settings=settings),
        motor=motor,
    )


class TestConsultaBemSucedida:
    def test_retorna_resposta_llm_candidata_valida(self, tmp_path: Path) -> None:
        motor = _FakeMotor([ResultadoMotorLocal(texto=_texto_valido())])
        gateway = _gateway(tmp_path, motor)

        resultado = gateway.consultar(_ponto())

        assert resultado.opcao.id == "aumentar-timeout"
        assert resultado.confidence == 0.92
        assert resultado.evidencia_bruta

    def test_schema_restringe_opcao_id_por_enum(self, tmp_path: Path) -> None:
        motor = _FakeMotor([ResultadoMotorLocal(texto=_texto_valido())])
        gateway = _gateway(tmp_path, motor)

        gateway.consultar(_ponto())

        schema = motor.chamadas[0]["schema"]
        assert schema.get("$defs") is None  # $refs resolvidos
        assert schema["properties"]["opcao"]["properties"]["id"]["enum"] == [
            "aumentar-timeout",
            "reiniciar",
        ]

    def test_usa_prompt_canonico_compartilhado(self, tmp_path: Path) -> None:
        from batman_os.llm.prompts import SYSTEM_PROMPT, mensagem_usuario

        motor = _FakeMotor([ResultadoMotorLocal(texto=_texto_valido())])
        gateway = _gateway(tmp_path, motor)
        ponto = _ponto()

        gateway.consultar(ponto)

        assert motor.chamadas[0]["system"] == SYSTEM_PROMPT
        assert motor.chamadas[0]["usuario"] == mensagem_usuario(ponto)

    def test_registra_no_ledger_com_custo_zero(self, tmp_path: Path) -> None:
        motor = _FakeMotor(
            [ResultadoMotorLocal(texto=_texto_valido(), tokens_entrada=500, tokens_saida=80)]
        )
        gateway = _gateway(tmp_path, motor)

        gateway.consultar(_ponto())

        linhas = (tmp_path / "llm_cost.jsonl").read_text(encoding="utf-8").strip().splitlines()
        entrada = json.loads(linhas[0])
        assert entrada["model"] == MODELO_LOCAL
        assert entrada["cost"] == 0.0  # prefixo "local-" tem preco zero, nao o padrao Haiku


class TestTimeoutEBreaker:
    def test_timeout_levanta_indisponivel_e_desarma_a_instancia(self, tmp_path: Path) -> None:
        motor = _FakeMotor(
            [TimeoutError("geracao presa"), ResultadoMotorLocal(texto=_texto_valido())]
        )
        gateway = _gateway(tmp_path, motor)

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

        # segunda chamada e pulada sem tocar o motor (breaker de instancia)
        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

        assert len(motor.chamadas) == 1

    def test_erro_generico_do_motor_nao_desarma(self, tmp_path: Path) -> None:
        motor = _FakeMotor(
            [RuntimeError("falha pontual"), ResultadoMotorLocal(texto=_texto_valido())]
        )
        gateway = _gateway(tmp_path, motor)

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

        resultado = gateway.consultar(_ponto())  # motor volta a ser consultado

        assert resultado.opcao.id == "aumentar-timeout"
        assert len(motor.chamadas) == 2


class TestPosValidacao:
    def test_json_fora_do_contrato_levanta_indisponivel(self, tmp_path: Path) -> None:
        motor = _FakeMotor([ResultadoMotorLocal(texto="isto nao e json")])
        gateway = _gateway(tmp_path, motor)

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

    def test_opcao_fora_da_lista_levanta_indisponivel(self, tmp_path: Path) -> None:
        motor = _FakeMotor([ResultadoMotorLocal(texto=_texto_valido(opcao_id="opcao-inventada"))])
        gateway = _gateway(tmp_path, motor)

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

    def test_confianca_abaixo_do_minimo_levanta_indisponivel(self, tmp_path: Path) -> None:
        motor = _FakeMotor([ResultadoMotorLocal(texto=_texto_valido(confidence=0.5))])
        gateway = _gateway(tmp_path, motor)  # default llm_local_min_confidence=0.75

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

    def test_confianca_no_limiar_passa(self, tmp_path: Path) -> None:
        motor = _FakeMotor([ResultadoMotorLocal(texto=_texto_valido(confidence=0.75))])
        gateway = _gateway(tmp_path, motor)

        resultado = gateway.consultar(_ponto())

        assert resultado.confidence == 0.75


class TestMotorRealIndisponivel:
    def test_sem_gguf_configurado_levanta_indisponivel(self, tmp_path: Path) -> None:
        settings = Settings()  # llm_local_gguf_path vazio
        gateway = LocalLlmGateway(
            settings=settings,
            cost_tracker=CostTracker(ledger_path=tmp_path / "c.jsonl", settings=settings),
        )

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())

    def test_gguf_inexistente_levanta_indisponivel(self, tmp_path: Path) -> None:
        settings = Settings(llm_local_gguf_path=str(tmp_path / "nao-existe.gguf"))
        gateway = LocalLlmGateway(
            settings=settings,
            cost_tracker=CostTracker(ledger_path=tmp_path / "c.jsonl", settings=settings),
        )

        with pytest.raises(LlmGatewayIndisponivel):
            gateway.consultar(_ponto())


class TestSatisfazLlmGatewayProtocol:
    def test_gateway_e_utilizavel_pelo_decision_engine(self, tmp_path: Path) -> None:
        from batman_os.foundation.types import MissionId
        from batman_os.kernel.decision_engine import DecisionEngine

        motor = _FakeMotor([ResultadoMotorLocal(texto=_texto_valido())])
        gateway = _gateway(tmp_path, motor)

        class _ConhecimentoVazio:
            def consultar(self, ponto: DecisionPoint) -> None:
                del ponto
                return None

        class _ValidadorSempreAprova:
            def validar(self, ponto: DecisionPoint, resposta: Any) -> bool:
                del ponto, resposta
                return True

        engine = DecisionEngine(
            base_conhecimento=_ConhecimentoVazio(),
            llm_gateway=gateway,
            validador=_ValidadorSempreAprova(),
        )
        resultado = engine.resolve(_ponto(), MissionId("m-1"))

        assert resultado.decision is not None
        assert resultado.decision.resolved_by == "llm"
