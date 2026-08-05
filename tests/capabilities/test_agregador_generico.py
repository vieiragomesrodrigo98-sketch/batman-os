"""Testes da Capability agregadora genérica (Fase 3 do roadmap de
plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estágio 3.1)."""

from __future__ import annotations

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.agregador_generico import (
    EntradaAgregadorGenerico,
    EntradaInvalida,
    SaidaAgregadorGenerico,
    construir_implementacao_agregador_dependencias,
    construir_implementacao_agregador_regex,
    construir_implementacao_agregadora,
)
from batman_os.foundation.types import CapabilityId, MissionId, StepId, TenantId, agora


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _handler_soma_um(item: object, contexto: ExecutionContext) -> dict[str, object]:
    del contexto
    if item == {"explode": True}:
        raise ValueError("item explodiu de proposito")
    return {"achados": [{"origem": item}]}


class TestConstruirImplementacaoAgregadora:
    def test_agrega_achados_de_varios_itens(self) -> None:
        impl = construir_implementacao_agregadora(
            capability_id=CapabilityId("teste-agregador"),
            nome="teste",
            handler_por_item=_handler_soma_um,
            acceptance_tests=[],
        )
        entrada = EntradaAgregadorGenerico(
            capability_alvo="x", itens=[{"a": 1}, {"b": 2}, {"c": 3}]
        ).model_dump()

        saida = SaidaAgregadorGenerico.model_validate(impl.handler(entrada, _contexto()))

        assert len(saida.achados) == 3
        assert saida.itens_processados == 3
        assert saida.itens_com_erro == []

    def test_item_com_erro_nao_derruba_o_step_e_fica_isolado(self) -> None:
        impl = construir_implementacao_agregadora(
            capability_id=CapabilityId("teste-agregador"),
            nome="teste",
            handler_por_item=_handler_soma_um,
            acceptance_tests=[],
        )
        entrada = EntradaAgregadorGenerico(
            capability_alvo="x", itens=[{"a": 1}, {"explode": True}, {"c": 3}]
        ).model_dump()

        saida = SaidaAgregadorGenerico.model_validate(impl.handler(entrada, _contexto()))

        assert len(saida.achados) == 2
        assert saida.itens_processados == 3
        assert len(saida.itens_com_erro) == 1
        assert "item[1]" in saida.itens_com_erro[0]

    def test_entrada_invalida_levanta_excecao_dedicada(self) -> None:
        impl = construir_implementacao_agregadora(
            capability_id=CapabilityId("teste-agregador"),
            nome="teste",
            handler_por_item=_handler_soma_um,
            acceptance_tests=[],
        )
        try:
            impl.handler({"itens": "nao-e-lista"}, _contexto())
        except EntradaInvalida:
            pass
        else:
            raise AssertionError("deveria ter levantado EntradaInvalida")


class TestAgregadoresConcretosCertificam:
    def test_agregador_regex_certifica(self) -> None:
        impl = construir_implementacao_agregador_regex()
        definicao_ativa = certificar(
            impl,
            entrada_para_teste_idempotencia=impl.acceptance_tests[0].entrada,
            contexto_para_teste_idempotencia=_contexto(),
        )
        assert definicao_ativa.id == CapabilityId("regex-sobre-conteudo-de-arquivo-agregador")

    def test_agregador_dependencias_certifica(self) -> None:
        impl = construir_implementacao_agregador_dependencias()
        definicao_ativa = certificar(
            impl,
            entrada_para_teste_idempotencia=impl.acceptance_tests[0].entrada,
            contexto_para_teste_idempotencia=_contexto(),
        )
        assert definicao_ativa.id == CapabilityId("toml-dependencias-agregador")
