"""Testes do Event Bus (Vol.II Cap.10) — cobre AT-10.1 e o contrato de
publish/subscribe/replay da secao 10.2-10.5 da especificacao."""

from __future__ import annotations

import threading
from pathlib import Path

from batman_os.foundation.types import EventId, MissionId, TenantId
from batman_os.kernel.event_bus import EmissorKernel, EventBus, KernelEvent


def _evento(mission_id: str, tipo: str, causado_por: str | None = None) -> KernelEvent:
    return KernelEvent(
        mission_id=MissionId(mission_id),
        tenant_id=TenantId("tenant-1"),
        tipo=tipo,
        emitido_por=EmissorKernel.MISSION_RUNTIME,
        causado_por=EventId(causado_por) if causado_por else None,
    )


def test_at_10_1_replay_reconstroi_historia_completa_de_uma_missao() -> None:
    bus = EventBus()
    bus.publish(_evento("m-1", "MissionCreated"))
    bus.publish(_evento("m-1", "MissionPlanned"))
    bus.publish(_evento("m-1", "MissionCompleted"))

    historia = bus.replay(MissionId("m-1"))

    assert [e.tipo for e in historia] == [
        "MissionCreated",
        "MissionPlanned",
        "MissionCompleted",
    ]


def test_replay_isola_eventos_de_missoes_diferentes() -> None:
    bus = EventBus()
    bus.publish(_evento("m-1", "MissionCreated"))
    bus.publish(_evento("m-2", "MissionCreated"))
    bus.publish(_evento("m-1", "MissionCompleted"))

    historia_m1 = bus.replay(MissionId("m-1"))
    historia_m2 = bus.replay(MissionId("m-2"))

    assert [e.tipo for e in historia_m1] == ["MissionCreated", "MissionCompleted"]
    assert [e.tipo for e in historia_m2] == ["MissionCreated"]


def test_replay_preserva_ordenacao_causal_de_publicacao() -> None:
    bus = EventBus()
    for i in range(5):
        bus.publish(_evento("m-1", f"Evento{i}"))

    historia = bus.replay(MissionId("m-1"))

    assert [e.tipo for e in historia] == [f"Evento{i}" for i in range(5)]


def test_replay_retorna_copia_nao_afeta_log_interno() -> None:
    bus = EventBus()
    bus.publish(_evento("m-1", "MissionCreated"))

    historia = bus.replay(MissionId("m-1"))
    historia.append(_evento("m-1", "EventoFalso"))

    assert [e.tipo for e in bus.replay(MissionId("m-1"))] == ["MissionCreated"]


def test_evento_e_imutavel() -> None:
    evento = _evento("m-1", "MissionCreated")

    with __import__("pytest").raises(Exception):
        evento.tipo = "Outro"  # type: ignore[misc]


def test_subscribe_recebe_apenas_eventos_que_passam_no_filtro() -> None:
    bus = EventBus()
    recebidos: list[str] = []

    bus.subscribe(
        filtro=lambda e: e.tipo == "MissionCompleted",
        handler=lambda e: recebidos.append(e.tipo),
    )

    bus.publish(_evento("m-1", "MissionCreated"))
    bus.publish(_evento("m-1", "MissionCompleted"))

    assert recebidos == ["MissionCompleted"]


def test_cancelar_inscricao_para_de_receber_eventos() -> None:
    bus = EventBus()
    recebidos: list[str] = []

    assinatura = bus.subscribe(
        filtro=lambda _e: True,
        handler=lambda e: recebidos.append(e.tipo),
    )
    bus.publish(_evento("m-1", "Antes"))
    assinatura.cancelar_inscricao()
    bus.publish(_evento("m-1", "Depois"))

    assert recebidos == ["Antes"]


class TestMilestone5PersistenciaRealViaSqlite:
    """Achado de revisão fechado na Milestone 5: o log deixa de viver só em
    memória Python — precisa sobreviver a destruir e recriar o objeto
    apontando para o MESMO arquivo, não só rodar em `:memory:`."""

    def test_eventos_sobrevivem_a_destruir_e_recriar_o_eventbus(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "eventos.db")

        bus1 = EventBus(db_path=db_path)
        bus1.publish(_evento("m-1", "MissionCreated"))
        bus1.publish(_evento("m-1", "MissionCompleted"))
        del bus1

        bus2 = EventBus(db_path=db_path)
        historia = bus2.replay(MissionId("m-1"))

        assert [e.tipo for e in historia] == ["MissionCreated", "MissionCompleted"]

    def test_dois_eventbus_memory_nao_compartilham_estado(self) -> None:
        bus_a = EventBus()
        bus_b = EventBus()

        bus_a.publish(_evento("m-1", "SoNoA"))

        assert [e.tipo for e in bus_a.replay(MissionId("m-1"))] == ["SoNoA"]
        assert bus_b.replay(MissionId("m-1")) == []

    def test_payload_e_metadados_sao_preservados_apos_reabrir(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "eventos2.db")

        bus1 = EventBus(db_path=db_path)
        original = KernelEvent(
            mission_id=MissionId("m-1"),
            tenant_id=TenantId("tenant-x"),
            tipo="MissionCreated",
            payload={"chave": "valor", "numero": 42},
            emitido_por=EmissorKernel.MISSION_RUNTIME,
        )
        bus1.publish(original)
        del bus1

        bus2 = EventBus(db_path=db_path)
        recuperado = bus2.replay(MissionId("m-1"))[0]

        assert recuperado.tenant_id == original.tenant_id
        assert recuperado.payload == {"chave": "valor", "numero": 42}
        assert recuperado.emitido_por == EmissorKernel.MISSION_RUNTIME


class TestFase2Estagio23ThreadSafety:
    """Fase 2 do roadmap de plataforma (`.claude/plans/peaceful-wondering-
    hearth.md`), Estagio 2.3 — pre-requisito para o Scheduler real
    (Estagio 2.4) rodar Missoes em threads diferentes compartilhando o
    mesmo `EventBus`. Antes desta mudanca, `sqlite3.connect()` sem
    `check_same_thread=False` crasharia assim que uma segunda thread
    tocasse a conexao."""

    def test_publish_concorrente_de_varias_threads_nao_perde_nenhum_evento(self) -> None:
        bus = EventBus()
        n_threads = 8
        eventos_por_thread = 20

        def _publicar(indice_thread: int) -> None:
            for i in range(eventos_por_thread):
                bus.publish(_evento(f"m-{indice_thread}", f"Evento{i}"))

        threads = [threading.Thread(target=_publicar, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for indice_thread in range(n_threads):
            historia = bus.replay(MissionId(f"m-{indice_thread}"))
            assert [e.tipo for e in historia] == [f"Evento{i}" for i in range(eventos_por_thread)]

    def test_replay_concorrente_com_publish_nao_crasha(self) -> None:
        bus = EventBus()
        bus.publish(_evento("m-1", "MissionCreated"))
        erros: list[Exception] = []

        def _publicar() -> None:
            for i in range(50):
                bus.publish(_evento("m-1", f"Evento{i}"))

        def _ler() -> None:
            for _ in range(50):
                try:
                    bus.replay(MissionId("m-1"))
                except Exception as exc:  # noqa: BLE001 - queremos capturar qualquer falha
                    erros.append(exc)

        escritor = threading.Thread(target=_publicar)
        leitor = threading.Thread(target=_ler)
        escritor.start()
        leitor.start()
        escritor.join()
        leitor.join()

        assert erros == []


class TestRetencaoDoLog:
    """`GOV_BATMANOS_ESTADO_DB_16GB01` — o log crescia SEM TETO.

    Medido em 2026-08-12 na máquina do DEV: `.batman-os/estado.db` com
    **18,3 GB** e 7.108.502 linhas em `events`, contra 493 em
    `inbox_achados`. Um único scan do radar-preditivo acrescentou ~748 mil
    eventos e ~1,9 GB — o achado (o que se quer guardar) é minúsculo e o
    rastro de execução (o que ninguém relê) é que ocupa o disco. Medido
    também: **2.770 bytes por evento**, e é dessa constante que sai o teto.

    Por que podar no `__init__` é seguro: `replay()` é sempre chamado com o
    `mission_id` da execução CORRENTE (`mission_runtime`, `planning_engine`,
    `workflow_engine`, `playbook_driver` — conferido por grep, não presumido),
    então a poda no início do processo só alcança execuções anteriores, nunca
    uma missão em voo. O único leitor entre execuções é a CLI de
    observabilidade, que também recebe um `mission_id` — é forense, não
    correção.

    Duas travas de segurança: `:memory:` nunca poda (é o default e não ocupa
    disco), e `BATMAN_EVENTS_MAX=0` desliga a retenção inteira, para quem
    precisa do log completo numa investigação.
    """

    def test_poda_mantem_os_mais_recentes_e_descarta_os_antigos(self, tmp_path: Path) -> None:
        caminho = str(tmp_path / "estado.db")
        bus = EventBus(db_path=caminho, max_eventos=0)  # sem poda ao encher
        for i in range(50):
            bus.publish(_evento(f"m-{i}", "MissionCreated"))

        # nova execução do processo, com teto de 10
        bus2 = EventBus(db_path=caminho, max_eventos=10)
        assert bus2.total_de_eventos() == 10
        # os que sobraram são os ÚLTIMOS, não os primeiros
        assert bus2.replay(MissionId("m-49")) != []
        assert bus2.replay(MissionId("m-0")) == []

    def test_nao_poda_quando_o_total_cabe_no_teto(self, tmp_path: Path) -> None:
        caminho = str(tmp_path / "estado.db")
        bus = EventBus(db_path=caminho, max_eventos=0)
        for i in range(5):
            bus.publish(_evento(f"m-{i}", "MissionCreated"))

        bus2 = EventBus(db_path=caminho, max_eventos=100)
        assert bus2.total_de_eventos() == 5
        assert bus2.replay(MissionId("m-0")) != []

    def test_teto_zero_desliga_a_retencao(self, tmp_path: Path) -> None:
        caminho = str(tmp_path / "estado.db")
        bus = EventBus(db_path=caminho, max_eventos=0)
        for i in range(30):
            bus.publish(_evento(f"m-{i}", "MissionCreated"))

        bus2 = EventBus(db_path=caminho, max_eventos=0)
        assert bus2.total_de_eventos() == 30

    def test_a_missao_em_voo_nao_perde_historia(self, tmp_path: Path) -> None:
        """A poda roda no `__init__`; depois dela o log volta a ser
        append-only. Uma missão que publica 40 eventos com teto de 10 mantém
        os 40 — senão `replay()` devolveria história truncada no meio da
        execução, que é pior que disco cheio."""
        caminho = str(tmp_path / "estado.db")
        bus = EventBus(db_path=caminho, max_eventos=10)
        for _ in range(40):
            bus.publish(_evento("m-viva", "MissionExecuting"))

        assert len(bus.replay(MissionId("m-viva"))) == 40

    def test_memoria_nunca_poda(self) -> None:
        bus = EventBus(max_eventos=1)
        for i in range(20):
            bus.publish(_evento(f"m-{i}", "MissionCreated"))
        assert bus.total_de_eventos() == 20

    def test_arquivo_encolhe_de_fato_apos_a_poda(self, tmp_path: Path) -> None:
        """Sem VACUUM o SQLite só marca páginas como livres e o arquivo NÃO
        encolhe — era metade do card: podar sem VACUUM não devolve disco
        nenhum, e o sintoma (18 GB) continuaria idêntico."""
        caminho = tmp_path / "estado.db"
        bus = EventBus(db_path=str(caminho), max_eventos=0)
        for i in range(4000):
            bus.publish(_evento(f"m-{i}", "MissionCreated"))
        bus.fechar()
        tamanho_cheio = caminho.stat().st_size

        EventBus(db_path=str(caminho), max_eventos=50)
        assert caminho.stat().st_size < tamanho_cheio
