"""Testes da Planning Engine (Vol.II Cap.7) — AT-7.1, AT-7.2, AT-7.3."""

from __future__ import annotations

import pytest

from batman_os.foundation.types import CapabilityId, CapabilityRef, MissionId, StepId
from batman_os.kernel.mission_runtime import MissionIntent
from batman_os.kernel.planning_engine import (
    PlanningFailure,
    PlanStep,
    RegistroCapacidades,
    _encontrar_ciclo,
    plan,
)

MISSAO_EXEMPLO = MissionId("m-1")


class RegistroFake:
    """Implementa `RegistroCapacidades` (Protocol) para teste — nao depende
    do Capability Engine real (Cap.11, ainda nao construido)."""

    def __init__(self, candidatos: list[CapabilityRef], versao: str = "v1") -> None:
        self._candidatos = candidatos
        self._versao = versao

    def buscar_candidatos(self, intent: MissionIntent) -> list[CapabilityRef]:
        del intent
        return self._candidatos

    def versao(self) -> str:
        return self._versao


def _ref(nome: str) -> CapabilityRef:
    return CapabilityRef(capability_id=CapabilityId(nome), versao="1.0.0")


def _registro_como_protocolo(registro: RegistroFake) -> RegistroCapacidades:
    return registro


class TestAT71PlanHashDeterministico:
    def test_mesmo_intent_e_mesma_versao_produzem_mesmo_hash(self) -> None:
        registro = _registro_como_protocolo(RegistroFake([_ref("detect-sql-injection")]))
        intent = MissionIntent(dados={"alvo": "servico-x"})

        plano_1 = plan(MISSAO_EXEMPLO, intent, registro)
        plano_2 = plan(MISSAO_EXEMPLO, intent, registro)

        assert plano_1.plan_hash == plano_2.plan_hash

    def test_intents_diferentes_produzem_hashes_diferentes(self) -> None:
        registro = _registro_como_protocolo(RegistroFake([_ref("detect-sql-injection")]))

        plano_1 = plan(MISSAO_EXEMPLO, MissionIntent(dados={"alvo": "a"}), registro)
        plano_2 = plan(MISSAO_EXEMPLO, MissionIntent(dados={"alvo": "b"}), registro)

        assert plano_1.plan_hash != plano_2.plan_hash

    def test_versao_de_registro_diferente_muda_o_hash(self) -> None:
        intent = MissionIntent(dados={"alvo": "servico-x"})
        registro_v1 = _registro_como_protocolo(RegistroFake([_ref("cap-a")], versao="v1"))
        registro_v2 = _registro_como_protocolo(RegistroFake([_ref("cap-a")], versao="v2"))

        plano_1 = plan(MISSAO_EXEMPLO, intent, registro_v1)
        plano_2 = plan(MISSAO_EXEMPLO, intent, registro_v2)

        assert plano_1.plan_hash != plano_2.plan_hash


class TestAT72NuncaValidaComCiclo:
    def test_plano_com_ciclo_nunca_e_retornado_como_valido(self) -> None:
        a = PlanStep(id=StepId("a"), capability=_ref("cap-a"), depende_de=[StepId("b")])
        b = PlanStep(id=StepId("b"), capability=_ref("cap-b"), depende_de=[StepId("a")])

        assert _encontrar_ciclo([a, b]) is not None

    def test_grafo_sem_ciclo_retorna_none(self) -> None:
        a = PlanStep(id=StepId("a"), capability=_ref("cap-a"))
        b = PlanStep(id=StepId("b"), capability=_ref("cap-b"), depende_de=[StepId("a")])

        assert _encontrar_ciclo([a, b]) is None

    def test_dependencia_para_step_inexistente_levanta_planning_failure(self) -> None:
        # _compor_via_grafo_capacidades nunca gera dependencia invalida
        # sozinha (encadeia so IDs que ela mesma acabou de criar) — a funcao
        # de validacao e testada diretamente, construindo o caso orfao a mao.
        from batman_os.kernel.planning_engine import _validar

        step_orfao = PlanStep(capability=_ref("cap-a"), depende_de=[StepId("inexistente")])
        with pytest.raises(PlanningFailure):
            _validar([step_orfao])


class TestAT73GapDeConhecimentoRastreavel:
    def test_planning_failure_carrega_evidencia(self) -> None:
        step_orfao = PlanStep(capability=_ref("cap-a"), depende_de=[StepId("inexistente")])

        from batman_os.kernel.planning_engine import _validar

        with pytest.raises(PlanningFailure) as excinfo:
            _validar([step_orfao])

        assert excinfo.value.evidencia
        assert "dependencias_invalidas" in excinfo.value.evidencia

    def test_composicao_sem_candidatos_gera_plano_vazio_nao_falha(self) -> None:
        """Ausencia de candidatos nao e, por si so, uma PlanningFailure — um
        plano com zero steps e valido (grafo vazio nao tem ciclo nem
        dependencia orfa); a decisao de tratar isso como gap de conhecimento
        e do chamador (Kernel), nao da Planning Engine."""
        registro = _registro_como_protocolo(RegistroFake([]))
        plano = plan(MISSAO_EXEMPLO, MissionIntent(dados={}), registro)

        assert plano.steps == []


class TestComposicaoViaGrafo:
    def test_steps_encadeados_sequencialmente_na_ordem_dos_candidatos(self) -> None:
        registro = _registro_como_protocolo(
            RegistroFake([_ref("passo-1"), _ref("passo-2"), _ref("passo-3")])
        )

        plano = plan(MISSAO_EXEMPLO, MissionIntent(dados={}), registro)

        assert len(plano.steps) == 3
        assert plano.steps[0].depende_de == []
        assert plano.steps[1].depende_de == [plano.steps[0].id]
        assert plano.steps[2].depende_de == [plano.steps[1].id]
