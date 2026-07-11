"""Testes da Workflow Engine (Vol.II Cap.9) — AT-9.1 a AT-9.3."""

from __future__ import annotations

import threading
import time

import pytest

from batman_os.foundation.types import (
    CapabilityId,
    CapabilityRef,
    MissionId,
    PlanId,
    RecoveryStrategy,
    TenantId,
    TipoRecoveryStrategy,
    WorkflowRunId,
)
from batman_os.kernel.event_bus import EventBus
from batman_os.kernel.planning_engine import ExecutionPlan, PlanStep
from batman_os.kernel.workflow_engine import (
    ErrorEvidence,
    ResultadoInvocacao,
    WorkflowEngine,
    WorkflowRunDesconhecido,
)

MISSAO = MissionId("m-1")
TENANT = TenantId("tenant-1")


def _ref(nome: str) -> CapabilityRef:
    return CapabilityRef(capability_id=CapabilityId(nome), versao="1.0.0")


def _plano(steps: list[PlanStep]) -> ExecutionPlan:
    return ExecutionPlan(
        id=PlanId("p-1"),
        mission_id=MISSAO,
        tenant_id=TENANT,
        steps=steps,
        decision_points=[],
        plan_hash="hash-x",
    )


class InvocadorControlavel:
    """Mock de InvocadorDeStep — resultados configuraveis por capability_id,
    e contador de chamadas para verificar idempotencia (AT-9.3)."""

    def __init__(self, resultados: dict[str, list[ResultadoInvocacao]]) -> None:
        self._resultados = {k: list(v) for k, v in resultados.items()}
        self.chamadas: dict[str, int] = dict.fromkeys(resultados, 0)

    def invocar(self, step: PlanStep) -> ResultadoInvocacao:
        chave = step.capability.capability_id
        self.chamadas[chave] = self.chamadas.get(chave, 0) + 1
        fila = self._resultados[chave]
        return fila.pop(0) if len(fila) > 1 else fila[0]


class InvocadorControlavelComAtraso(InvocadorControlavel):
    """Variante de `InvocadorControlavel` com um pequeno atraso antes de
    retornar — usada para aumentar a chance real de interleaving de
    threads nos testes de concorrencia do Estagio 2.4 (a correcao em si
    nao depende de timing, mas o teste fica mais honesto exercitando
    entrelacamento de fato)."""

    def __init__(
        self, resultados: dict[str, list[ResultadoInvocacao]], atraso_segundos: float = 0.0
    ) -> None:
        super().__init__(resultados)
        self._atraso_segundos = atraso_segundos

    def invocar(self, step: PlanStep) -> ResultadoInvocacao:
        time.sleep(self._atraso_segundos)
        return super().invocar(step)


class TestAT91NuncaReexecutaStepComSucesso:
    def test_step_ja_sucesso_nao_aparece_mais_em_passos_prontos(self) -> None:
        step_a = PlanStep(capability=_ref("cap-a"))
        step_b = PlanStep(capability=_ref("cap-b"), depende_de=[step_a.id])
        invocador = InvocadorControlavel({"cap-a": [ResultadoInvocacao(sucesso=True, output="ok")]})
        engine = WorkflowEngine(invocador)
        run = engine.iniciar(MISSAO, _plano([step_a, step_b]))

        assert step_a in engine.passos_prontos(run.id)

        engine.executar_passo(run.id, step_a)

        assert step_a not in engine.passos_prontos(run.id)
        assert invocador.chamadas["cap-a"] == 1

        # reexecutar explicitamente o mesmo step nao reinvoca a Capability
        engine.executar_passo(run.id, step_a)
        assert invocador.chamadas["cap-a"] == 1

    def test_step_b_fica_pronto_somente_apos_a_concluir(self) -> None:
        step_a = PlanStep(capability=_ref("cap-a"))
        step_b = PlanStep(capability=_ref("cap-b"), depende_de=[step_a.id])
        invocador = InvocadorControlavel(
            {
                "cap-a": [ResultadoInvocacao(sucesso=True)],
                "cap-b": [ResultadoInvocacao(sucesso=True)],
            }
        )
        engine = WorkflowEngine(invocador)
        run = engine.iniciar(MISSAO, _plano([step_a, step_b]))

        assert step_b not in engine.passos_prontos(run.id)
        engine.executar_passo(run.id, step_a)
        assert step_b in engine.passos_prontos(run.id)


class TestAT92FalhaSemRecuperacaoResultaEmFailed:
    def test_falha_sem_recovery_strategy_marca_run_como_failed(self) -> None:
        step_a = PlanStep(capability=_ref("cap-a"))
        invocador = InvocadorControlavel(
            {"cap-a": [ResultadoInvocacao(sucesso=False, erro=ErrorEvidence(mensagem="boom"))]}
        )
        engine = WorkflowEngine(invocador)
        run = engine.iniciar(MISSAO, _plano([step_a]))

        resultado = engine.executar_passo(run.id, step_a)

        assert resultado.estado == "failed"
        assert resultado.completed_steps[0].status == "failed"

    def test_retry_esgotado_tambem_marca_run_como_failed(self) -> None:
        step_a = PlanStep(
            capability=_ref("cap-a"),
            recovery_strategy=RecoveryStrategy(
                tipo=TipoRecoveryStrategy.RETRY, max_tentativas=3, backoff="fixed"
            ),
        )
        invocador = InvocadorControlavel(
            {"cap-a": [ResultadoInvocacao(sucesso=False, erro=ErrorEvidence(mensagem="boom"))]}
        )
        engine = WorkflowEngine(invocador)
        run = engine.iniciar(MISSAO, _plano([step_a]))

        resultado = engine.executar_passo(run.id, step_a)

        assert resultado.estado == "failed"
        assert invocador.chamadas["cap-a"] == 3

    def test_skip_if_optional_recupera_e_run_completa(self) -> None:
        step_a = PlanStep(
            capability=_ref("cap-a"),
            recovery_strategy=RecoveryStrategy(tipo=TipoRecoveryStrategy.SKIP_IF_OPTIONAL),
        )
        invocador = InvocadorControlavel(
            {"cap-a": [ResultadoInvocacao(sucesso=False, erro=ErrorEvidence(mensagem="boom"))]}
        )
        engine = WorkflowEngine(invocador)
        run = engine.iniciar(MISSAO, _plano([step_a]))

        resultado = engine.executar_passo(run.id, step_a)

        assert resultado.completed_steps[0].status == "recovered"
        assert resultado.estado == "completed"


class TestAT93CompensacaoIdempotente:
    def test_compensacao_e_invocada_exatamente_uma_vez_por_falha(self) -> None:
        step_principal = PlanStep(
            capability=_ref("aplicar-mudanca"),
        )
        step_compensacao = PlanStep(capability=_ref("reverter-mudanca"))
        step_principal.recovery_strategy = RecoveryStrategy(
            tipo=TipoRecoveryStrategy.COMPENSATE, compensation_step_id=step_compensacao.id
        )
        invocador = InvocadorControlavel(
            {
                "aplicar-mudanca": [
                    ResultadoInvocacao(sucesso=False, erro=ErrorEvidence(mensagem="falhou"))
                ],
                "reverter-mudanca": [ResultadoInvocacao(sucesso=True)],
            }
        )
        engine = WorkflowEngine(invocador)
        run = engine.iniciar(MISSAO, _plano([step_principal, step_compensacao]))

        resultado = engine.executar_passo(run.id, step_principal)

        assert invocador.chamadas["reverter-mudanca"] == 1
        assert resultado.completed_steps[0].status == "recovered"

    def test_compensacao_que_tambem_falha_marca_run_failed(self) -> None:
        step_principal = PlanStep(capability=_ref("aplicar-mudanca"))
        step_compensacao = PlanStep(capability=_ref("reverter-mudanca"))
        step_principal.recovery_strategy = RecoveryStrategy(
            tipo=TipoRecoveryStrategy.COMPENSATE, compensation_step_id=step_compensacao.id
        )
        invocador = InvocadorControlavel(
            {
                "aplicar-mudanca": [
                    ResultadoInvocacao(sucesso=False, erro=ErrorEvidence(mensagem="falhou"))
                ],
                "reverter-mudanca": [
                    ResultadoInvocacao(sucesso=False, erro=ErrorEvidence(mensagem="tambem falhou"))
                ],
            }
        )
        engine = WorkflowEngine(invocador)
        run = engine.iniciar(MISSAO, _plano([step_principal, step_compensacao]))

        resultado = engine.executar_passo(run.id, step_principal)

        assert resultado.estado == "failed"


def test_checkpoint_criado_apos_cada_passo_bem_sucedido() -> None:
    step_a = PlanStep(capability=_ref("cap-a"))
    invocador = InvocadorControlavel({"cap-a": [ResultadoInvocacao(sucesso=True)]})
    engine = WorkflowEngine(invocador)
    run = engine.iniciar(MISSAO, _plano([step_a]))

    resultado = engine.executar_passo(run.id, step_a)

    assert len(resultado.checkpoints) == 1
    assert resultado.checkpoints[0].apos_step_id == step_a.id


def test_cancelamento_cooperativo_so_afeta_run_em_execucao() -> None:
    step_a = PlanStep(capability=_ref("cap-a"))
    invocador = InvocadorControlavel({"cap-a": [ResultadoInvocacao(sucesso=True)]})
    engine = WorkflowEngine(invocador)
    run = engine.iniciar(MISSAO, _plano([step_a]))

    cancelado = engine.cancelar(run.id)
    assert cancelado.estado == "cancelled"

    # run ja concluido nao "descancela"/reabre
    run2 = engine.iniciar(MISSAO, _plano([step_a]))
    engine.executar_passo(run2.id, step_a)
    ainda_completo = engine.cancelar(run2.id)
    assert ainda_completo.estado == "completed"


class TestFase2Estagio21PersistenciaHibridaDoWorkflowRun:
    """Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-wondering-
    hearth.md`), Estagio 2.1 — sem `event_bus`, comportamento identico ao
    anterior (ja coberto pelos testes acima); com `event_bus`, uma segunda
    instancia de `WorkflowEngine` reconstroi o `WorkflowRun` via replay em
    cache-miss."""

    def test_cache_miss_reconstroi_completed_steps_e_checkpoints(self) -> None:
        event_bus = EventBus()
        step_a = PlanStep(capability=_ref("cap-a"))
        step_b = PlanStep(capability=_ref("cap-b"), depende_de=[step_a.id])
        invocador = InvocadorControlavel(
            {
                "cap-a": [ResultadoInvocacao(sucesso=True)],
                "cap-b": [ResultadoInvocacao(sucesso=True)],
            }
        )
        engine_a = WorkflowEngine(invocador, event_bus=event_bus)
        run = engine_a.iniciar(MISSAO, _plano([step_a, step_b]))
        engine_a.executar_passo(run.id, step_a)
        final = engine_a.executar_passo(run.id, step_b)

        engine_b = WorkflowEngine(invocador, event_bus=event_bus)
        hidratado = engine_b.get_run(run.id, mission_id=MISSAO)

        assert hidratado.estado == final.estado == "completed"
        assert [r.step_id for r in hidratado.completed_steps] == [
            r.step_id for r in final.completed_steps
        ]
        assert len(hidratado.checkpoints) == len(final.checkpoints) == 2
        assert hidratado.plan_id == run.plan_id
        assert hidratado.tenant_id == run.tenant_id

    def test_sem_event_bus_cache_miss_ainda_levanta_erro_conhecido(self) -> None:
        invocador = InvocadorControlavel({"cap-a": [ResultadoInvocacao(sucesso=True)]})
        engine = WorkflowEngine(invocador)  # sem event_bus — comportamento anterior

        with pytest.raises(WorkflowRunDesconhecido):
            engine.get_run(WorkflowRunId("inexistente"), mission_id=MISSAO)

    def test_hidratacao_nao_e_chamada_no_caminho_quente(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        event_bus = EventBus()
        step_a = PlanStep(capability=_ref("cap-a"))
        invocador = InvocadorControlavel({"cap-a": [ResultadoInvocacao(sucesso=True)]})
        engine = WorkflowEngine(invocador, event_bus=event_bus)
        run = engine.iniciar(MISSAO, _plano([step_a]))

        def _falhar(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("_hidratar_de nao deveria rodar com WorkflowRun em cache")

        monkeypatch.setattr(engine, "_hidratar_de", _falhar)

        assert engine.get_run(run.id).id == run.id


class TestFase2Estagio24ExecucaoConcorrente:
    """Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-wondering-
    hearth.md`), Estagio 2.4 — pre-requisito para o dispatcher real
    (`runtime/dispatcher.py`) despachar passos independentes do MESMO
    WorkflowRun em paralelo: `executar_passo` precisa ser seguro sob
    chamada concorrente, e a falha de um passo nunca pode ser
    sobrescrita de volta a "completed" por um passo irmao bem-sucedido
    que termina depois (a race que a versao sequencial nunca expunha)."""

    def test_falha_de_um_passo_nunca_e_sobrescrita_por_sucesso_concorrente(self) -> None:
        passos = [PlanStep(capability=_ref(f"cap-{i}")) for i in range(6)]
        resultados = {f"cap-{i}": [ResultadoInvocacao(sucesso=(i != 3))] for i in range(6)}
        invocador = InvocadorControlavelComAtraso(resultados, atraso_segundos=0.01)
        engine = WorkflowEngine(invocador)
        run = engine.iniciar(MISSAO, _plano(passos))

        threads = [
            threading.Thread(target=engine.executar_passo, args=(run.id, passo)) for passo in passos
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final = engine.get_run(run.id)
        assert final.estado == "failed"
        assert len(final.completed_steps) == 6

    def test_todos_bem_sucedidos_concorrentes_completa_corretamente(self) -> None:
        passos = [PlanStep(capability=_ref(f"cap-{i}")) for i in range(6)]
        resultados = {f"cap-{i}": [ResultadoInvocacao(sucesso=True)] for i in range(6)}
        invocador = InvocadorControlavelComAtraso(resultados, atraso_segundos=0.01)
        engine = WorkflowEngine(invocador)
        run = engine.iniciar(MISSAO, _plano(passos))

        threads = [
            threading.Thread(target=engine.executar_passo, args=(run.id, passo)) for passo in passos
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final = engine.get_run(run.id)
        assert final.estado == "completed"
        assert len(final.completed_steps) == 6
        assert len(final.checkpoints) == 6
