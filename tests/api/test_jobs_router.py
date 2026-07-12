"""Prova ponta-a-ponta de `POST /missions/{id}/resume` + `GET /jobs/{id}`
(Fase 7 do roadmap de plataforma, `.claude/plans/peaceful-wondering-
hearth.md`, Estágio 7.3; autenticados desde a Fase 8, Estágio 8.2). Mesma
doutrina de zero mock de Kernel/Runtime/Capability — só `plan()` é
substituído (monkeypatch, dentro do módulo `playbook_driver`), já que o
motor real nunca produz `decision_points` para um Playbook real (achado
de investigação, fora de escopo até Volume V — mesmo padrão já usado em
`tests/orchestration/test_playbook_driver.py`, Estágio 7.1, agora
aplicado através do endpoint HTTP real, não só chamando a função
diretamente)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import batman_os.api.routers.auditoria_seguranca as auditoria_router_mod
import batman_os.orchestration.playbook_driver as driver_mod
from batman_os.api.app import criar_app
from batman_os.cli.auditoria_seguranca_command import CAP_REGEX_AGREGADOR, TIPO_MISSAO
from batman_os.foundation.types import (
    CapabilityRef,
    DecisionOption,
    EscalationPolicy,
    HumanReviewRef,
    PlaybookId,
    Reversibilidade,
    TenantId,
)
from batman_os.kernel.event_bus import EmissorKernel, EventBus, KernelEvent
from batman_os.kernel.mission_runtime import MissionIntent
from batman_os.kernel.planning_engine import (
    DecisionPoint,
    ExecutionPlan,
    PlanStep,
    PlanStepTemplate,
)
from batman_os.workflow.playbooks import (
    FieldCondition,
    IntentMatcher,
    PlaybookDefinition,
    PlaybookProvenance,
    StatusPlaybook,
)

PERGUNTA = "aprovar a auditoria?"
OPCAO = DecisionOption(id="sim", descricao="Aprovar")

_CHAVES_DE_TESTE = {"acme": "chave-teste-acme", "outro-tenant": "chave-teste-outro-tenant"}


def _cabecalho(tenant: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_CHAVES_DE_TESTE[tenant]}"}


def _fake_plan_com_escalada() -> Any:
    """Mesmo padrão de `tests/orchestration/test_playbook_driver.py::
    _fake_plan_com_escalada` (Estágio 7.1) — reusa `CAP_REGEX_AGREGADOR`
    (Capability REAL, já certificada no `lifespan` do app) para que o
    step exista de verdade no `CapabilityRegistry` compartilhado."""

    def _plan(
        mission_id: Any,
        tenant_id: Any,
        intent: Any,
        registro: Any,
        repositorio_playbooks: Any = None,
        event_bus: EventBus | None = None,
    ) -> ExecutionPlan:
        del intent, registro, repositorio_playbooks
        plano = ExecutionPlan(
            mission_id=mission_id,
            tenant_id=tenant_id,
            steps=[
                PlanStep(
                    capability=CapabilityRef(capability_id=CAP_REGEX_AGREGADOR, versao="1.0.0")
                )
            ],
            decision_points=[
                DecisionPoint(
                    pergunta=PERGUNTA,
                    opcoes=[OPCAO],
                    escalation_policy=EscalationPolicy(
                        confidence_threshold=0.8,
                        preferred_escalation="human",
                        max_llm_retries=1,
                        reversibility=Reversibilidade.REVERSIVEL,
                    ),
                )
            ],
            plan_hash="hash-escalada-jobs-router",
        )
        if event_bus is not None:
            event_bus.publish(
                KernelEvent(
                    mission_id=plano.mission_id,
                    tenant_id=plano.tenant_id,
                    tipo="PlanCreated",
                    emitido_por=EmissorKernel.PLANNING_ENGINE,
                    payload={"plano": plano.model_dump(mode="json")},
                )
            )
        return plano

    return _plan


@dataclass(frozen=True)
class _EntradaVaziaParaAgregador:
    """`ConstrutorDeEntrada` mínimo para o único step (índice 0,
    `CAP_REGEX_AGREGADOR`) do Playbook fake — `itens=[]` é aceito por
    `EntradaAgregadorGenerico` (default_factory=list) e certificado
    (idempotência trivial com 0 itens); o step real roda de verdade
    (0 achados), provando o caminho completo até `Completed` sem
    depender de arquivos plantados em `tmp_path`."""

    def construir(self, outputs_das_dependencias: dict[Any, Any]) -> dict[str, Any]:
        del outputs_das_dependencias
        return {
            "tipo": "agregador-generico",
            "capability_alvo": str(CAP_REGEX_AGREGADOR),
            "itens": [],
        }


def _fake_montar_playbook(root: Path) -> tuple[PlaybookDefinition, dict[int, Any]]:
    """`plan()` é substituído por `_fake_plan_com_escalada()` acima e
    IGNORA `repositorio_playbooks` inteiramente — o `PlaybookDefinition`
    devolvido aqui só precisa ser aceitável por `PlaybookRegistry.
    register()` (`status=ACTIVE`). O ponto real deste fake é devolver
    `especificacoes` com a MESMA cardinalidade do plano fake (1 step,
    índice 0): usar o `montar_playbook` REAL produziria 7 especificações
    (6 checks + 1 relatório do Playbook real de auditoria) para um plano
    fake de 1 step — `especs_por_step_id = {plano.steps[i].id: ... for i
    in especificacoes_por_indice}` (`playbook_driver.py`) então indexaria
    `plano.steps[1..6]` fora do range."""
    del root
    matcher = IntentMatcher(
        conditions=[FieldCondition(campo="tipo", operador="eq", valor="security-audit")]
    )
    playbook = PlaybookDefinition(
        id=PlaybookId("playbook-fake-jobs-router"),
        version="1.0.0",
        applies_to=matcher,
        mission_type_id=TIPO_MISSAO,
        priority=5,
        steps_template=[
            PlanStepTemplate(
                capability=CapabilityRef(capability_id=CAP_REGEX_AGREGADOR, versao="1.0.0")
            )
        ],
        provenance=PlaybookProvenance(
            origin="hand-authored", approved_by=HumanReviewRef("review-fake-jobs-router")
        ),
        status=StatusPlaybook.ACTIVE,
    )
    return playbook, {0: _EntradaVaziaParaAgregador()}


def _poll_ate_estado(
    client: TestClient,
    mission_id: str,
    tenant: str,
    estados_aceitos: set[str],
    timeout: float = 5.0,
) -> dict[str, Any]:
    prazo = time.monotonic() + timeout
    ultimo_corpo: dict[str, Any] | None = None
    while time.monotonic() < prazo:
        resposta = client.get(f"/jobs/{mission_id}", headers=_cabecalho(tenant))
        ultimo_corpo = resposta.json()
        if ultimo_corpo["estado"] in estados_aceitos:
            return ultimo_corpo
        time.sleep(0.01)
    raise AssertionError(
        f"job {mission_id} nao atingiu {estados_aceitos} em {timeout}s (ultimo: {ultimo_corpo})"
    )


class TestFluxoCompletoDeResumo:
    def test_submit_escala_resume_e_completa(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(driver_mod, "plan", _fake_plan_com_escalada())
        monkeypatch.setattr(auditoria_router_mod, "montar_playbook", _fake_montar_playbook)

        app = criar_app(api_keys=_CHAVES_DE_TESTE)
        with TestClient(app) as client:
            resposta_submit = client.post(
                "/missions/security-audit",
                json={"root": str(tmp_path)},
                headers=_cabecalho("acme"),
            )
            assert resposta_submit.status_code == 202
            mission_id = resposta_submit.json()["mission_id"]

            corpo_aguardando = _poll_ate_estado(client, mission_id, "acme", {"AwaitingHuman"})
            assert corpo_aguardando["decision_pendente"] is not None
            assert corpo_aguardando["decision_pendente"]["pergunta"] == PERGUNTA
            assert corpo_aguardando["achados"] == []
            assert corpo_aguardando["erro"] is None

            resposta_resume = client.post(
                f"/missions/{mission_id}/resume",
                json={
                    "ponto": corpo_aguardando["decision_pendente"],
                    "opcao_escolhida": OPCAO.model_dump(),
                    "evidencia": [{"origem": "humano", "evidencias": ["aprovado no teste"]}],
                },
                headers=_cabecalho("acme"),
            )
            assert resposta_resume.status_code == 202
            assert resposta_resume.json()["mission_id"] == mission_id

            corpo_final = _poll_ate_estado(client, mission_id, "acme", {"Completed", "Failed"})

        assert corpo_final["estado"] == "Completed"
        assert corpo_final["erro"] is None

    def test_resume_com_tenant_errado_e_negado(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Reaproveita o isolamento de tenant já validado na Fase 5 —
        `runtime.get_mission()` levanta a mesma exceção de "não
        encontrado" para tenant mismatch. Fase 8: o "tenant errado" agora
        é uma CHAVE de outro tenant autenticando a requisição, não mais
        um campo de corpo divergente (o campo não existe mais)."""
        monkeypatch.setattr(driver_mod, "plan", _fake_plan_com_escalada())
        monkeypatch.setattr(auditoria_router_mod, "montar_playbook", _fake_montar_playbook)

        app = criar_app(api_keys=_CHAVES_DE_TESTE)
        # raise_server_exceptions=False: o TestClient por padrao RE-LEVANTA
        # excecoes nao tratadas do servidor (util para depuracao), em vez de
        # devolve-las como resposta 500 -- aqui queremos provar o codigo de
        # status HTTP de verdade que um cliente real receberia.
        with TestClient(app, raise_server_exceptions=False) as client:
            resposta_submit = client.post(
                "/missions/security-audit",
                json={"root": str(tmp_path)},
                headers=_cabecalho("acme"),
            )
            mission_id = resposta_submit.json()["mission_id"]
            corpo_aguardando = _poll_ate_estado(client, mission_id, "acme", {"AwaitingHuman"})

            resposta_resume = client.post(
                f"/missions/{mission_id}/resume",
                json={
                    "ponto": corpo_aguardando["decision_pendente"],
                    "opcao_escolhida": OPCAO.model_dump(),
                    "evidencia": [{"origem": "humano", "evidencias": ["x"]}],
                },
                headers=_cabecalho("outro-tenant"),
            )

        assert resposta_resume.status_code == 500  # KeyError nao tratado -> 500 default

    def test_job_desconhecido_no_resume_retorna_409(self) -> None:
        """`mission_id` existe no `MissionRuntime` (criado direto, sem
        passar pelo endpoint de submit) mas nunca teve entrada no
        `JobStore` — não há `especificacoes_por_indice` para retomar."""
        app = criar_app(api_keys=_CHAVES_DE_TESTE)
        with TestClient(app) as client:
            mission = app.state.colaboradores.runtime.create(
                MissionIntent(dados={"tipo": "security-audit"}),
                TIPO_MISSAO,
                tenant_id=TenantId("acme"),
            )

            resposta_resume = client.post(
                f"/missions/{mission.id}/resume",
                json={
                    "ponto": {
                        "pergunta": PERGUNTA,
                        "opcoes": [OPCAO.model_dump()],
                        "escalation_policy": {
                            "confidence_threshold": 0.8,
                            "preferred_escalation": "human",
                            "max_llm_retries": 1,
                            "reversibility": "reversible",
                        },
                    },
                    "opcao_escolhida": OPCAO.model_dump(),
                    "evidencia": [{"origem": "humano", "evidencias": ["x"]}],
                },
                headers=_cabecalho("acme"),
            )

        assert resposta_resume.status_code == 409

    def test_sem_header_de_autenticacao_no_get_jobs_retorna_401(self) -> None:
        app = criar_app(api_keys=_CHAVES_DE_TESTE)
        with TestClient(app) as client:
            resposta = client.get("/jobs/019f5287-4bf5-7144-8367-3f6cbaa281b1")

        assert resposta.status_code == 401

    def test_sem_header_de_autenticacao_no_resume_retorna_401(self) -> None:
        app = criar_app(api_keys=_CHAVES_DE_TESTE)
        with TestClient(app) as client:
            resposta = client.post(
                "/missions/019f5287-4bf5-7144-8367-3f6cbaa281b1/resume",
                json={
                    "ponto": {
                        "pergunta": PERGUNTA,
                        "opcoes": [OPCAO.model_dump()],
                        "escalation_policy": {
                            "confidence_threshold": 0.8,
                            "preferred_escalation": "human",
                            "max_llm_retries": 1,
                            "reversibility": "reversible",
                        },
                    },
                    "opcao_escolhida": OPCAO.model_dump(),
                    "evidencia": [{"origem": "humano", "evidencias": ["x"]}],
                },
            )

        assert resposta.status_code == 401


class TestFase10Estagio101DecisaoPendenteSobreviveARestart:
    """Fase 10 do roadmap de plataforma (`.claude/plans/peaceful-
    wondering-hearth.md`), Estágio 10.1) — `db_path` real (não
    `":memory:"`) compartilhado entre 2 `criar_app()` simula um restart
    real do processo: mesmo `EventBus` (arquivo SQLite), mas `JobStore`
    NOVO e vazio na segunda instância (nunca persistido — só o `EventBus`
    sobrevive)."""

    def test_get_jobs_mostra_decision_pendente_apos_restart_simulado(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(driver_mod, "plan", _fake_plan_com_escalada())
        monkeypatch.setattr(auditoria_router_mod, "montar_playbook", _fake_montar_playbook)
        db_path = str(tmp_path / "eventos.db")

        app_antes_do_restart = criar_app(db_path=db_path, api_keys=_CHAVES_DE_TESTE)
        with TestClient(app_antes_do_restart) as client_antes:
            resposta_submit = client_antes.post(
                "/missions/security-audit",
                json={"root": str(tmp_path)},
                headers=_cabecalho("acme"),
            )
            mission_id = resposta_submit.json()["mission_id"]
            corpo_antes = _poll_ate_estado(client_antes, mission_id, "acme", {"AwaitingHuman"})
            assert corpo_antes["decision_pendente"] is not None

        # "Restart": nova instancia do app, MESMO arquivo SQLite (event_bus
        # persistido), mas JobStore novo e vazio -- simula o processo
        # reiniciando entre a escalada e a resposta humana chegar.
        app_depois_do_restart = criar_app(db_path=db_path, api_keys=_CHAVES_DE_TESTE)
        with TestClient(app_depois_do_restart) as client_depois:
            assert (
                app_depois_do_restart.state.colaboradores.job_store.consultar(mission_id) is None
            )  # confirma que o JobStore de fato nao sobreviveu

            corpo_depois = client_depois.get(
                f"/jobs/{mission_id}", headers=_cabecalho("acme")
            ).json()

        assert corpo_depois["estado"] == "AwaitingHuman"
        assert corpo_depois["decision_pendente"] is not None
        assert corpo_depois["decision_pendente"]["pergunta"] == PERGUNTA
