"""Testes da Execution Engine (Vol.III Cap.12) — AT-12.1 a AT-12.3."""

from __future__ import annotations

import time
from typing import Any

from batman_os.foundation.types import CapabilityId, OperatorRef
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects
from batman_os.runtime.execution_engine import (
    ExecutionEngine,
    LimitadorDeRecurso,
    LimitadorDeRecursoPorOperador,
    LimitadorPermissivo,
    ValidadorContratoNaoDeterministico,
)


def _capability(deterministic: bool = True) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=CapabilityId("cap-a"),
        name="cap-a",
        version="1.0.0",
        input_schema={},
        output_schema={"properties": {"resultado": {}}},
        deterministic=deterministic,
        side_effects=SideEffects.NONE,
    )


class ValidadorSchemaChaves:
    """Aprova se todas as chaves de `output_schema["properties"]` estao
    presentes no output — proxy simples de compatibilidade estrutural."""

    def validar(self, output: Any, output_schema: dict[str, Any]) -> bool:
        propriedades = output_schema.get("properties") or {}
        if not isinstance(output, dict):
            return not propriedades
        return all(chave in output for chave in propriedades)


class ValidadorContratoSempreAprova:
    def validar(self, capability: CapabilityDefinition, output: Any) -> bool:
        del capability, output
        return True


class ValidadorContratoSempreReprova:
    def validar(self, capability: CapabilityDefinition, output: Any) -> bool:
        del capability, output
        return False


class OperadorRetornaFixo:
    def __init__(self, saida: Any) -> None:
        self._saida = saida

    def executar(self, capability_id: CapabilityId, entrada: Any) -> Any:
        del capability_id, entrada
        return self._saida


class OperadorLento:
    def __init__(self, segundos: float) -> None:
        self._segundos = segundos

    def executar(self, capability_id: CapabilityId, entrada: Any) -> Any:
        del capability_id, entrada
        time.sleep(self._segundos)
        return {"resultado": "ok"}


def _engine(
    validador_contrato: ValidadorContratoNaoDeterministico | None = None,
    limitador: LimitadorDeRecurso | None = None,
) -> ExecutionEngine:
    return ExecutionEngine(
        validador_schema=ValidadorSchemaChaves(),
        validador_contrato_nao_deterministico=validador_contrato or ValidadorContratoSempreAprova(),
        limitador=limitador,
    )


class TestAT121NuncaSucessoComOutputInvalido:
    def test_output_compativel_com_schema_gera_sucesso(self) -> None:
        engine = _engine()
        resultado = engine.invoke(
            _capability(),
            OperadorRetornaFixo({"resultado": "ok"}),
            OperatorRef(operator_id="op-1"),
            entrada={},
            timeout_segundos=1.0,
        )
        assert resultado.status == "success"
        engine.fechar()

    def test_output_que_viola_schema_nunca_vira_sucesso(self) -> None:
        engine = _engine()
        resultado = engine.invoke(
            _capability(),
            OperadorRetornaFixo({"campo_errado": "x"}),
            OperatorRef(operator_id="op-1"),
            entrada={},
            timeout_segundos=1.0,
        )
        assert resultado.status == "failure"
        assert resultado.output is None
        engine.fechar()

    def test_capability_nao_deterministica_reprovada_no_contrato_nunca_e_sucesso(self) -> None:
        engine = _engine(validador_contrato=ValidadorContratoSempreReprova())
        resultado = engine.invoke(
            _capability(deterministic=False),
            OperadorRetornaFixo({"resultado": "ok"}),
            OperatorRef(operator_id="op-1"),
            entrada={},
            timeout_segundos=1.0,
        )
        assert resultado.status == "failure"
        engine.fechar()


class TestAT122TimeoutSempreEmTempoFinito:
    def test_operador_lento_retorna_timeout_sem_bloquear_alem_do_limite(self) -> None:
        engine = _engine()
        inicio = time.monotonic()
        resultado = engine.invoke(
            _capability(),
            OperadorLento(segundos=5.0),
            OperatorRef(operator_id="op-lento"),
            entrada={},
            timeout_segundos=0.2,
        )
        decorrido = time.monotonic() - inicio

        assert resultado.status == "timeout"
        assert decorrido < 2.0  # bem abaixo dos 5s do operador — nunca bloqueia o chamador
        engine.fechar()


class TestAT123BulkheadIsolaOperadoresInstaveis:
    def test_operador_sem_orcamento_falha_sem_afetar_outro_operador(self) -> None:
        limitador = LimitadorDeRecursoPorOperador(limite_concorrente_por_operador=1)
        op_instavel = OperatorRef(operator_id="instavel")
        op_saudavel = OperatorRef(operator_id="saudavel")

        # Esgota o orcamento do operador instavel manualmente (simula uma
        # invocacao em andamento que nunca libera).
        assert limitador.reservar(op_instavel) is True

        engine = _engine(limitador=limitador)

        resultado_instavel = engine.invoke(
            _capability(),
            OperadorRetornaFixo({"resultado": "ok"}),
            op_instavel,
            entrada={},
            timeout_segundos=1.0,
        )
        resultado_saudavel = engine.invoke(
            _capability(),
            OperadorRetornaFixo({"resultado": "ok"}),
            op_saudavel,
            entrada={},
            timeout_segundos=1.0,
        )

        assert resultado_instavel.status == "failure"
        assert resultado_saudavel.status == "success"
        engine.fechar()

    def test_limitador_permissivo_nunca_bloqueia(self) -> None:
        limitador = LimitadorPermissivo()
        ref = OperatorRef(operator_id="op-1")
        assert limitador.reservar(ref) is True
        assert limitador.reservar(ref) is True  # sem limite real
        limitador.liberar(ref)


class TestFase2Estagio23SubmitNaoBloqueante:
    """Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-wondering-
    hearth.md`), Estagio 2.3 — `submit()` retorna imediatamente; `invoke()`
    e um wrapper sincrono sobre ele, comportamento inalterado (ja coberto
    pelas classes acima, que chamam `invoke()` diretamente)."""

    def test_submit_retorna_future_antes_do_operador_concluir(self) -> None:
        engine = _engine()
        futuro = engine.submit(
            _capability(),
            OperadorLento(segundos=0.5),
            OperatorRef(operator_id="op-1"),
            entrada={},
            timeout_segundos=2.0,
        )

        assert not futuro.done()  # OperadorLento ainda dorme — submit() nao esperou
        resultado = futuro.result(timeout=2.0)
        assert resultado.status == "success"
        engine.fechar()

    def test_varias_chamadas_concorrentes_nao_deadlockam(self) -> None:
        """Achado do Explorador 2 (investigacao Fase 2): enfileirar a espera
        bloqueante no MESMO pool que executa o Operador arriscaria deadlock
        assim que houver mais chamadas concorrentes que `max_workers` — cada
        worker externo ficaria bloqueado esperando um worker interno que
        nunca sobraria. `max_workers=2` com 5 chamadas simultaneas prova que
        isso nao acontece mais (pool `_supervisor` separado de `_executor`)."""
        engine = ExecutionEngine(
            validador_schema=ValidadorSchemaChaves(),
            validador_contrato_nao_deterministico=ValidadorContratoSempreAprova(),
            max_workers=2,
        )
        futuros = [
            engine.submit(
                _capability(),
                OperadorLento(segundos=0.2),
                OperatorRef(operator_id=f"op-{i}"),
                entrada={},
                timeout_segundos=5.0,
            )
            for i in range(5)
        ]

        resultados = [f.result(timeout=5.0) for f in futuros]

        assert all(r.status == "success" for r in resultados)
        engine.fechar()
