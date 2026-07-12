"""Testes da Planning Engine (Vol.II Cap.7) — AT-7.1, AT-7.2, AT-7.3."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    DecisionOption,
    EscalationPolicy,
    MissionId,
    PlaybookId,
    RecoveryStrategy,
    Reversibilidade,
    StepId,
    TenantId,
)
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.mission_runtime import MissionIntent
from batman_os.kernel.planning_engine import (
    DecisionPoint,
    PlanningFailure,
    PlanStep,
    PlanStepTemplate,
    RegistroCapacidades,
    _encontrar_ciclo,
    hidratar_plano,
    plan,
)

MISSAO_EXEMPLO = MissionId("m-1")
TENANT_EXEMPLO = TenantId("tenant-1")


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


@dataclass
class PlaybookFake:
    """Satisfaz `PlaybookCandidato` (Protocol) estruturalmente — mesma
    doutrina de `RegistroFake` acima: testes do Kernel nunca importam
    `workflow/playbooks.py::PlaybookDefinition` (Vol.VIII Cap.32, secao
    32.3 — kernel nunca depende de workflow), mesmo em teste."""

    id: PlaybookId
    steps_template: list[PlanStepTemplate]
    recovery_defaults: dict[int, RecoveryStrategy] = field(default_factory=dict)
    decision_points_template: dict[int, DecisionPoint] = field(default_factory=dict)


class _RepositorioComUmPlaybook:
    def __init__(self, playbook: PlaybookFake) -> None:
        self._playbook = playbook

    def encontrar_correspondente(self, intent: MissionIntent) -> PlaybookFake | None:
        del intent
        return self._playbook


def _ponto_decisao(pergunta: str = "aprovar?") -> DecisionPoint:
    return DecisionPoint(
        pergunta=pergunta,
        opcoes=[DecisionOption(id="sim", descricao="Aprovar")],
        escalation_policy=EscalationPolicy(
            confidence_threshold=0.8,
            preferred_escalation="human",
            max_llm_retries=1,
            reversibility=Reversibilidade.REVERSIVEL,
        ),
    )


class TestAT71PlanHashDeterministico:
    def test_mesmo_intent_e_mesma_versao_produzem_mesmo_hash(self) -> None:
        registro = _registro_como_protocolo(RegistroFake([_ref("detect-sql-injection")]))
        intent = MissionIntent(dados={"alvo": "servico-x"})

        plano_1 = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, intent, registro)
        plano_2 = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, intent, registro)

        assert plano_1.plan_hash == plano_2.plan_hash

    def test_intents_diferentes_produzem_hashes_diferentes(self) -> None:
        registro = _registro_como_protocolo(RegistroFake([_ref("detect-sql-injection")]))

        plano_1 = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, MissionIntent(dados={"alvo": "a"}), registro)
        plano_2 = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, MissionIntent(dados={"alvo": "b"}), registro)

        assert plano_1.plan_hash != plano_2.plan_hash

    def test_versao_de_registro_diferente_muda_o_hash(self) -> None:
        intent = MissionIntent(dados={"alvo": "servico-x"})
        registro_v1 = _registro_como_protocolo(RegistroFake([_ref("cap-a")], versao="v1"))
        registro_v2 = _registro_como_protocolo(RegistroFake([_ref("cap-a")], versao="v2"))

        plano_1 = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, intent, registro_v1)
        plano_2 = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, intent, registro_v2)

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
        plano = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, MissionIntent(dados={}), registro)

        assert plano.steps == []


class TestComposicaoViaGrafo:
    def test_steps_encadeados_sequencialmente_na_ordem_dos_candidatos(self) -> None:
        registro = _registro_como_protocolo(
            RegistroFake([_ref("passo-1"), _ref("passo-2"), _ref("passo-3")])
        )

        plano = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, MissionIntent(dados={}), registro)

        assert len(plano.steps) == 3
        assert plano.steps[0].depende_de == []
        assert plano.steps[1].depende_de == [plano.steps[0].id]
        assert plano.steps[2].depende_de == [plano.steps[1].id]


class TestFase2Estagio22PersistirExecutionPlanConcreto:
    """Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-wondering-
    hearth.md`), Estagio 2.2 — `PlanStep.id` e aleatorio a cada chamada de
    `plan()` (so `plan_hash` e deterministico); retomar precisa do plano
    CONCRETO ja gerado, nunca de rechamar `plan()`."""

    def test_hidratar_plano_reproduz_os_mesmos_step_ids(self) -> None:
        event_bus = EventBus()
        registro = _registro_como_protocolo(
            RegistroFake([_ref("passo-1"), _ref("passo-2"), _ref("passo-3")])
        )

        original = plan(
            MISSAO_EXEMPLO, TENANT_EXEMPLO, MissionIntent(dados={}), registro, event_bus=event_bus
        )
        hidratado = hidratar_plano(event_bus, MISSAO_EXEMPLO)

        assert hidratado is not None
        assert [s.id for s in hidratado.steps] == [s.id for s in original.steps]
        assert hidratado.plan_hash == original.plan_hash
        assert hidratado.id == original.id

    def test_replanejar_geraria_ids_diferentes_dos_ja_gravados(self) -> None:
        """Contraste explicito: rechamar plan() (em vez de hidratar) produz
        StepId novos mesmo com o mesmo intent — por isso retomada nunca pode
        replanejar."""
        registro = _registro_como_protocolo(RegistroFake([_ref("passo-1")]))
        intent = MissionIntent(dados={})

        plano_1 = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, intent, registro)
        plano_2 = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, intent, registro)

        assert plano_1.plan_hash == plano_2.plan_hash
        assert plano_1.steps[0].id != plano_2.steps[0].id

    def test_sem_event_bus_nenhum_evento_e_publicado(self) -> None:
        registro = _registro_como_protocolo(RegistroFake([_ref("passo-1")]))

        plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, MissionIntent(dados={}), registro)  # sem event_bus

        event_bus = EventBus()
        assert hidratar_plano(event_bus, MISSAO_EXEMPLO) is None

    def test_hidratar_plano_de_missao_sem_plano_retorna_none(self) -> None:
        event_bus = EventBus()

        assert hidratar_plano(event_bus, MissionId("nunca-planejada")) is None


class TestFase9Estagio92DecisionPointsReaisDePlaybook:
    """Fase 9 do roadmap de plataforma (`.claude/plans/peaceful-wondering-
    hearth.md`), Estagio 9.2 — antes desta fase, `_extrair_decision_points()`
    sempre retornava `[]`, mesmo para Playbooks reais com `decision_points_
    template` declarado (a justificativa "bloqueado ate Volume V" estava
    desatualizada — Volume V esta completo desde a Fase 3). Estes testes
    provam a extracao de verdade, sem monkeypatch de `plan()` (o padrao
    usado desde a Fase 7 exatamente por essa limitacao nao existir mais)."""

    def test_step_com_decision_point_declarado_aparece_no_plano(self) -> None:
        ponto = _ponto_decisao()
        playbook = PlaybookFake(
            id=PlaybookId("pb-1"),
            steps_template=[PlanStepTemplate(capability=_ref("cap-a"))],
            decision_points_template={0: ponto},
        )
        registro = _registro_como_protocolo(RegistroFake([]))
        repo = _RepositorioComUmPlaybook(playbook)

        plano = plan(
            MISSAO_EXEMPLO,
            TENANT_EXEMPLO,
            MissionIntent(dados={}),
            registro,
            repositorio_playbooks=repo,
        )

        assert plano.decision_points == [ponto]
        assert plano.steps[0].decision_point_id == ponto.id

    def test_step_sem_decision_point_nao_gera_nenhum(self) -> None:
        playbook = PlaybookFake(
            id=PlaybookId("pb-2"),
            steps_template=[PlanStepTemplate(capability=_ref("cap-a"))],
        )
        registro = _registro_como_protocolo(RegistroFake([]))
        repo = _RepositorioComUmPlaybook(playbook)

        plano = plan(
            MISSAO_EXEMPLO,
            TENANT_EXEMPLO,
            MissionIntent(dados={}),
            registro,
            repositorio_playbooks=repo,
        )

        assert plano.decision_points == []
        assert plano.steps[0].decision_point_id is None

    def test_playbook_com_varios_steps_so_o_indice_declarado_gera_decision_point(self) -> None:
        ponto = _ponto_decisao("aprovar o step do meio?")
        playbook = PlaybookFake(
            id=PlaybookId("pb-3"),
            steps_template=[
                PlanStepTemplate(capability=_ref("cap-a")),
                PlanStepTemplate(capability=_ref("cap-b")),
                PlanStepTemplate(capability=_ref("cap-c")),
            ],
            decision_points_template={1: ponto},
        )
        registro = _registro_como_protocolo(RegistroFake([]))
        repo = _RepositorioComUmPlaybook(playbook)

        plano = plan(
            MISSAO_EXEMPLO,
            TENANT_EXEMPLO,
            MissionIntent(dados={}),
            registro,
            repositorio_playbooks=repo,
        )

        assert plano.decision_points == [ponto]
        assert plano.steps[0].decision_point_id is None
        assert plano.steps[1].decision_point_id == ponto.id
        assert plano.steps[2].decision_point_id is None

    def test_composicao_via_grafo_nunca_gera_decision_point(self) -> None:
        """Sem Playbook (`repositorio_playbooks=None`), a composicao via
        grafo de Capabilities continua sem gerar nenhum DecisionPoint —
        mesmo comportamento de antes desta fase, nao uma regressao."""
        registro = _registro_como_protocolo(RegistroFake([_ref("cap-a"), _ref("cap-b")]))

        plano = plan(MISSAO_EXEMPLO, TENANT_EXEMPLO, MissionIntent(dados={}), registro)

        assert plano.decision_points == []
