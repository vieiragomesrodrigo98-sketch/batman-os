"""Testes de Contrato/Certificação de Capability (Vol.IV Cap.16) — AT-16.1 a AT-16.3."""

from __future__ import annotations

from typing import Any

import pytest

from batman_os.capabilities.capability_contract import (
    AcceptanceTest,
    CapabilityImplementation,
    FalhaDeIdempotencia,
    GapDeChecklist,
    ResultadoEsperado,
    RevisaoHumanaObrigatoria,
    certificar,
)
from batman_os.capabilities.operator import ExecutionContext
from batman_os.foundation.types import CapabilityId, MissionId, StepId, TenantId, agora
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects, StatusCapability


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _definicao(
    side_effects: SideEffects = SideEffects.NONE,
    idempotent: bool = True,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=CapabilityId("cap-a"),
        name="cap-a",
        version="1.0.0",
        input_schema=input_schema if input_schema is not None else {"properties": {"x": {}}},
        output_schema=output_schema if output_schema is not None else {"properties": {"y": {}}},
        deterministic=True,
        side_effects=side_effects,
        idempotent=idempotent,
    )


def _handler_ok(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    if entrada is None or "invalida" in entrada:
        raise ValueError("entrada invalida")
    if "trava" in entrada:
        raise TimeoutError("timeout simulado")
    return {"y": "ok"}


def _testes_completos() -> list[AcceptanceTest]:
    return [
        AcceptanceTest(
            name="caminho-feliz", entrada={"x": 1}, resultado_esperado=ResultadoEsperado.SUCCESS
        ),
        AcceptanceTest(
            name="entrada-invalida",
            entrada={"invalida": True},
            resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
        ),
        AcceptanceTest(
            name="timeout-dependencia",
            entrada={"trava": True},
            resultado_esperado=ResultadoEsperado.TIMEOUT,
        ),
    ]


def _implementacao(
    side_effects: SideEffects = SideEffects.NONE,
    idempotent: bool = True,
    handler: Any = _handler_ok,
    acceptance_tests: list[AcceptanceTest] | None = None,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> CapabilityImplementation:
    return CapabilityImplementation(
        definition=_definicao(
            side_effects=side_effects,
            idempotent=idempotent,
            input_schema=input_schema,
            output_schema=output_schema,
        ),
        handler=handler,
        acceptance_tests=acceptance_tests if acceptance_tests is not None else _testes_completos(),
    )


class TestAT161ChecklistCompleto:
    def test_sem_output_schema_e_rejeitada(self) -> None:
        implementacao = _implementacao(output_schema={})
        with pytest.raises(GapDeChecklist):
            certificar(
                implementacao,
                revisao_humana_obtida=True,
                contexto_para_teste_idempotencia=_contexto(),
            )

    def test_sem_input_schema_e_rejeitada(self) -> None:
        implementacao = _implementacao(input_schema={})
        with pytest.raises(GapDeChecklist):
            certificar(
                implementacao,
                revisao_humana_obtida=True,
                contexto_para_teste_idempotencia=_contexto(),
            )

    def test_sem_cobertura_de_schema_rejection_e_rejeitada(self) -> None:
        testes_incompletos = [
            AcceptanceTest(
                name="so-feliz", entrada={"x": 1}, resultado_esperado=ResultadoEsperado.SUCCESS
            )
        ]
        implementacao = _implementacao(acceptance_tests=testes_incompletos)
        with pytest.raises(GapDeChecklist):
            certificar(
                implementacao,
                revisao_humana_obtida=True,
                contexto_para_teste_idempotencia=_contexto(),
            )

    def test_checklist_completo_com_todos_os_testes_passa(self) -> None:
        implementacao = _implementacao()
        definicao_ativa = certificar(
            implementacao,
            revisao_humana_obtida=True,
            entrada_para_teste_idempotencia={"x": 1},
            contexto_para_teste_idempotencia=_contexto(),
        )
        assert definicao_ativa.status == StatusCapability.ACTIVE

    def test_teste_de_aceitacao_reprovado_impede_certificacao(self) -> None:
        testes_com_expectativa_errada = [
            AcceptanceTest(
                name="espera-sucesso-mas-e-erro",
                entrada={"invalida": True},
                resultado_esperado=ResultadoEsperado.SUCCESS,
            ),
            AcceptanceTest(
                name="entrada-invalida",
                entrada={"invalida": True},
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
            AcceptanceTest(
                name="timeout-dependencia",
                entrada={"trava": True},
                resultado_esperado=ResultadoEsperado.TIMEOUT,
            ),
        ]
        implementacao = _implementacao(acceptance_tests=testes_com_expectativa_errada)
        with pytest.raises(GapDeChecklist):
            certificar(
                implementacao,
                revisao_humana_obtida=True,
                contexto_para_teste_idempotencia=_contexto(),
            )


class TestAT162IrreversibleExigeRevisaoHumana:
    def test_irreversible_sem_revisao_humana_e_rejeitada(self) -> None:
        implementacao = _implementacao(side_effects=SideEffects.IRREVERSIBLE)
        with pytest.raises(RevisaoHumanaObrigatoria):
            certificar(
                implementacao,
                revisao_humana_obtida=False,
                entrada_para_teste_idempotencia={"x": 1},
                contexto_para_teste_idempotencia=_contexto(),
            )

    def test_irreversible_com_revisao_humana_e_certificada(self) -> None:
        implementacao = _implementacao(side_effects=SideEffects.IRREVERSIBLE)
        definicao_ativa = certificar(
            implementacao,
            revisao_humana_obtida=True,
            entrada_para_teste_idempotencia={"x": 1},
            contexto_para_teste_idempotencia=_contexto(),
        )
        assert definicao_ativa.status == StatusCapability.ACTIVE

    def test_reversible_nao_exige_revisao_humana(self) -> None:
        implementacao = _implementacao(side_effects=SideEffects.REVERSIBLE)
        definicao_ativa = certificar(
            implementacao,
            revisao_humana_obtida=False,
            entrada_para_teste_idempotencia={"x": 1},
            contexto_para_teste_idempotencia=_contexto(),
        )
        assert definicao_ativa.status == StatusCapability.ACTIVE


class TestAT163IdempotenciaVerificadaAntesDaCertificacao:
    def test_handler_nao_idempotente_reprova_certificacao(self) -> None:
        contador = {"chamadas": 0}

        def handler_nao_idempotente(entrada: Any, contexto: ExecutionContext) -> Any:
            del contexto
            if entrada is None or "invalida" in entrada:
                raise ValueError("entrada invalida")
            if "trava" in entrada:
                raise TimeoutError("timeout simulado")
            contador["chamadas"] += 1
            return {"y": contador["chamadas"]}  # saida diferente a cada chamada valida

        implementacao = _implementacao(handler=handler_nao_idempotente)
        with pytest.raises(FalhaDeIdempotencia):
            certificar(
                implementacao,
                revisao_humana_obtida=True,
                entrada_para_teste_idempotencia={"x": 1},
                contexto_para_teste_idempotencia=_contexto(),
            )

    def test_handler_idempotente_passa(self) -> None:
        implementacao = _implementacao()
        definicao_ativa = certificar(
            implementacao,
            revisao_humana_obtida=True,
            entrada_para_teste_idempotencia={"x": 1},
            contexto_para_teste_idempotencia=_contexto(),
        )
        assert definicao_ativa.status == StatusCapability.ACTIVE

    def test_idempotent_false_pula_a_verificacao(self) -> None:
        contador = {"chamadas": 0}

        def handler_nao_idempotente(entrada: Any, contexto: ExecutionContext) -> Any:
            del contexto
            if entrada is None or "invalida" in entrada:
                raise ValueError("entrada invalida")
            if "trava" in entrada:
                raise TimeoutError("timeout simulado")
            contador["chamadas"] += 1
            return {"y": contador["chamadas"]}

        implementacao = _implementacao(idempotent=False, handler=handler_nao_idempotente)
        definicao_ativa = certificar(implementacao, revisao_humana_obtida=True)
        assert definicao_ativa.status == StatusCapability.ACTIVE
