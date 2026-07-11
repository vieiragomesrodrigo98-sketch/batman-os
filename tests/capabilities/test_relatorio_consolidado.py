"""Testes da Capability "relatório consolidado" (Fase 3 do roadmap de
plataforma, `.claude/plans/peaceful-wondering-hearth.md`, Estágio 3.1)."""

from __future__ import annotations

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.relatorio_consolidado import (
    EntradaInvalida,
    avaliar_relatorio_consolidado,
    construir_implementacao,
)
from batman_os.foundation.types import CapabilityId, MissionId, StepId, TenantId, agora


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


class TestAvaliarRelatorioConsolidado:
    def test_zero_achados_produz_relatorio_vazio_valido(self) -> None:
        saida = avaliar_relatorio_consolidado({"achados": []}, _contexto())

        assert saida["total_achados"] == 0
        assert saida["resumo_por_severidade"] == {}
        assert saida["resumo_por_codigo"] == {}
        assert "nenhum achado" in saida["texto"]

    def test_contagens_por_severidade_e_codigo(self) -> None:
        entrada = {
            "titulo_missao": "Auditoria X",
            "achados": [
                {"codigo": "CLOUD-001", "severidade": "high"},
                {"codigo": "DEP-003", "severidade": "medium"},
                {"codigo": "CLOUD-001", "severidade": "high"},
                {"codigo": "DEVOPS-003", "severidade": "high"},
            ],
        }

        saida = avaliar_relatorio_consolidado(entrada, _contexto())

        assert saida["total_achados"] == 4
        assert saida["resumo_por_severidade"] == {"high": 3, "medium": 1}
        assert saida["resumo_por_codigo"] == {"CLOUD-001": 2, "DEP-003": 1, "DEVOPS-003": 1}
        assert saida["titulo"] == "Auditoria X"
        assert len(saida["achados"]) == 4

    def test_achado_nao_dict_levanta_excecao(self) -> None:
        try:
            avaliar_relatorio_consolidado({"achados": "nao-e-lista"}, _contexto())
        except EntradaInvalida:
            pass
        else:
            raise AssertionError("deveria ter levantado EntradaInvalida")


def test_construir_implementacao_certifica() -> None:
    impl = construir_implementacao()
    definicao_ativa = certificar(
        impl,
        entrada_para_teste_idempotencia=impl.acceptance_tests[0].entrada,
        contexto_para_teste_idempotencia=_contexto(),
    )
    assert definicao_ativa.id == CapabilityId("relatorio-consolidado-de-achados")
