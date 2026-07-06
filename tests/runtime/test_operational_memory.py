"""Testes da Operational Memory (Vol.III Cap.13) — AT-13.1 a AT-13.3."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from batman_os.foundation.types import (
    CognitiveDebtFlag,
    DecisionPointId,
    MissionId,
    MissionTypeId,
    TenantId,
)
from batman_os.kernel.mission_runtime import MissionState
from batman_os.runtime.operational_memory import (
    DecisionSummary,
    OperationalMemory,
    OperationalRecord,
    PatternQuery,
    calcular_confidence_combinada,
    find_promotion_candidates,
)

MISSAO = MissionId("m-1")
TENANT = TenantId("tenant-1")
TIPO = MissionTypeId("investigate-incident")


def _record(
    resumos: list[DecisionSummary] | None = None,
    final_state: MissionState = MissionState.COMPLETED,
    cognitive_debt_flag: CognitiveDebtFlag = CognitiveDebtFlag.AUTONOMOUS,
    tenant_id: TenantId = TENANT,
) -> OperationalRecord:
    return OperationalRecord(
        mission_id=MISSAO,
        tenant_id=tenant_id,
        mission_type=TIPO,
        decision_points_resolved=tuple(resumos or []),
        final_state=final_state,
        cognitive_debt_flag=cognitive_debt_flag,
    )


class TestAT131AppendOnly:
    def test_record_e_imutavel_apos_criado(self) -> None:
        record = _record()
        with pytest.raises(ValidationError):
            record.final_state = MissionState.FAILED  # type: ignore[misc]

    def test_memory_so_expoe_registrar_sem_metodo_de_edicao_ou_remocao(self) -> None:
        memory = OperationalMemory()
        assert not hasattr(memory, "editar")
        assert not hasattr(memory, "remover")
        assert not hasattr(memory, "atualizar")

    def test_registros_acumulam_sem_substituir(self) -> None:
        memory = OperationalMemory()
        memory.registrar(_record())
        memory.registrar(_record())

        assert len(memory.all_records()) == 2


class TestAT132NuncaAlteraComportamentoSozinha:
    def test_find_promotion_candidates_nao_muta_a_memoria(self) -> None:
        memory = OperationalMemory()
        resumo = DecisionSummary(
            decision_point_id=DecisionPointId("dp-1"),
            resolved_by="human",
            chosen_option_id="opcao-a",
            confidence=1.0,
        )
        for _ in range(3):
            memory.registrar(_record(resumos=[resumo]))

        antes = memory.all_records()
        candidatos = find_promotion_candidates(memory, threshold=3)
        depois = memory.all_records()

        assert antes == depois  # nenhuma mutacao provocada pela consulta
        assert len(candidatos) == 1
        assert candidatos[0].assinatura == "dp-1"

    def test_candidato_e_so_dado_retornado_nunca_aplicado(self) -> None:
        """Nao existe nenhum metodo em OperationalMemory nem no retorno de
        find_promotion_candidates que promova uma regra ou altere o Decision
        Engine - a promocao e sempre um passo externo (Learning Engine +
        Human Review, fora de escopo)."""
        memory = OperationalMemory()
        resumo = DecisionSummary(
            decision_point_id=DecisionPointId("dp-1"),
            resolved_by="llm",
            chosen_option_id="a",
            confidence=0.9,
        )
        for _ in range(5):
            memory.registrar(_record(resumos=[resumo]))

        candidatos = find_promotion_candidates(memory, threshold=5)
        assert not hasattr(candidatos[0], "aplicar")
        assert not hasattr(candidatos[0], "promover")

    def test_resolvido_por_conhecimento_nao_e_candidato(self) -> None:
        memory = OperationalMemory()
        resumo = DecisionSummary(
            decision_point_id=DecisionPointId("dp-2"),
            resolved_by="knowledge",
            chosen_option_id="a",
            confidence=1.0,
        )
        for _ in range(5):
            memory.registrar(_record(resumos=[resumo]))

        assert find_promotion_candidates(memory, threshold=5) == []

    def test_resultado_inconsistente_nao_e_candidato(self) -> None:
        memory = OperationalMemory()
        memory.registrar(
            _record(
                resumos=[
                    DecisionSummary(
                        decision_point_id=DecisionPointId("dp-3"),
                        resolved_by="human",
                        chosen_option_id="a",
                        confidence=1.0,
                    )
                ]
            )
        )
        memory.registrar(
            _record(
                resumos=[
                    DecisionSummary(
                        decision_point_id=DecisionPointId("dp-3"),
                        resolved_by="human",
                        chosen_option_id="b",  # divergente da primeira
                        confidence=1.0,
                    )
                ]
            )
        )

        assert find_promotion_candidates(memory, threshold=2) == []


class TestAT133IndisponibilidadeDegradaGraciosamente:
    def test_memory_none_degrada_para_confidence_base(self) -> None:
        resultado = calcular_confidence_combinada(0.7, None, TENANT, "dp-1")
        assert resultado == 0.7

    def test_consulta_que_lanca_excecao_degrada_para_confidence_base(self) -> None:
        class MemoriaQuebrada(OperationalMemory):
            def get_decision_history(
                self, tenant_id: TenantId, decision_point_signature: str
            ) -> list[DecisionSummary]:
                raise RuntimeError("indisponivel")

        resultado = calcular_confidence_combinada(0.7, MemoriaQuebrada(), TENANT, "dp-1")
        assert resultado == 0.7

    def test_sem_historico_degrada_para_confidence_base(self) -> None:
        memory = OperationalMemory()
        resultado = calcular_confidence_combinada(0.7, memory, TENANT, "dp-inexistente")
        assert resultado == 0.7

    def test_com_historico_combina_confiancas(self) -> None:
        memory = OperationalMemory()
        memory.registrar(
            _record(
                resumos=[
                    DecisionSummary(
                        decision_point_id=DecisionPointId("dp-1"),
                        resolved_by="human",
                        chosen_option_id="a",
                        confidence=1.0,
                    )
                ]
            )
        )

        resultado = calcular_confidence_combinada(0.5, memory, TENANT, "dp-1")
        assert resultado == pytest.approx(0.75)


def test_get_frequency_filtra_por_tipo_e_estado_final() -> None:
    memory = OperationalMemory()
    memory.registrar(_record(final_state=MissionState.COMPLETED))
    memory.registrar(_record(final_state=MissionState.FAILED))

    assert memory.get_frequency(PatternQuery(mission_type=TIPO)) == 2
    assert (
        memory.get_frequency(PatternQuery(mission_type=TIPO, final_state=MissionState.FAILED)) == 1
    )


class TestMilestone5PersistenciaRealViaSqlite:
    """Achado de revisão fechado na Milestone 5: os registros deixam de
    viver só em memória Python — precisam sobreviver a destruir e recriar
    o objeto apontando para o MESMO arquivo, não só rodar em `:memory:`."""

    def test_registros_sobrevivem_a_destruir_e_recriar_a_memory(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "memoria.db")

        memory1 = OperationalMemory(db_path=db_path)
        memory1.registrar(_record(final_state=MissionState.COMPLETED))
        memory1.registrar(_record(final_state=MissionState.FAILED))
        del memory1

        memory2 = OperationalMemory(db_path=db_path)
        registros = memory2.all_records()

        assert len(registros) == 2
        assert [r.final_state for r in registros] == [
            MissionState.COMPLETED,
            MissionState.FAILED,
        ]

    def test_duas_memories_memory_nao_compartilham_estado(self) -> None:
        memory_a = OperationalMemory()
        memory_b = OperationalMemory()

        memory_a.registrar(_record())

        assert len(memory_a.all_records()) == 1
        assert memory_b.all_records() == []

    def test_decision_summaries_sao_preservados_apos_reabrir(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "memoria2.db")
        resumo = DecisionSummary(
            decision_point_id=DecisionPointId("dp-1"),
            resolved_by="human",
            chosen_option_id="opcao-a",
            confidence=0.87,
        )

        memory1 = OperationalMemory(db_path=db_path)
        memory1.registrar(_record(resumos=[resumo]))
        del memory1

        memory2 = OperationalMemory(db_path=db_path)
        recuperado = memory2.all_records()[0]

        assert recuperado.decision_points_resolved == (resumo,)
        assert recuperado.tenant_id == TENANT

    def test_metodos_de_consulta_funcionam_apos_reabrir(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "memoria3.db")
        resumo = DecisionSummary(
            decision_point_id=DecisionPointId("dp-1"),
            resolved_by="human",
            chosen_option_id="opcao-a",
            confidence=1.0,
        )

        memory1 = OperationalMemory(db_path=db_path)
        memory1.registrar(_record(resumos=[resumo]))
        del memory1

        memory2 = OperationalMemory(db_path=db_path)

        assert memory2.get_decision_history(TENANT, "dp-1") == [resumo]
        assert memory2.get_frequency(PatternQuery(mission_type=TIPO)) == 1
