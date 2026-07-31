"""Testes do ObserveWatcher — run_once (conjunto exato + entrega via sink),
heartbeat (emite limpo + self-heartbeat a cada N ciclos), run_forever
(best-effort: excecao num ciclo nao derruba o loop)."""

from __future__ import annotations

from collections import Counter

from batman_os.foundation.types import TenantId
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceAlert,
    GovernanceEngine,
    SeveridadeAlerta,
)
from batman_os.observe.snapshot import (
    AmostraAuth,
    AmostraEndpoint,
    AmostraInfra,
    AmostraPortas,
    ContagemNginx,
    ObserveSnapshot,
    PortaEscuta,
)
from batman_os.observe.watcher import ObserveWatcher


class _SinkFake:
    """Registra cada GovernanceAlert entregue (prova de entrega via sink)."""

    def __init__(self) -> None:
        self.entregues: list[GovernanceAlert] = []

    def enviar(self, alert: GovernanceAlert) -> None:
        self.entregues.append(alert)


def _snapshot_rico() -> ObserveSnapshot:
    return ObserveSnapshot(
        tenant_id=TenantId("acme"),
        infra=AmostraInfra(cpu_percent=95.0, ram_percent=50.0, disk_percent=85.0),
        endpoints=[
            AmostraEndpoint(url="https://x/health", ok=False, status=None, error="timeout"),
            AmostraEndpoint(
                url="https://x/api",
                ok=True,
                status=200,
                latencias_janela_ms=[600.0, 700.0, 1200.0],
                headers_presentes=["Strict-Transport-Security"],
            ),
        ],
        portas=AmostraPortas(inesperadas=[PortaEscuta(port=6379, bind="0.0.0.0", service="redis")]),
        processos_rodando=["bash", "xmrig"],
        processos_esperados=["nginx", "gunicorn"],
        nginx=ContagemNginx(total=100, status_5xx=8, por_ip_404={"1.2.3.4": 40}, auth_401_403=20),
        auth=AmostraAuth(
            total_linhas=200, falhas=25, ip_top="9.9.9.9", falhas_por_ip={"9.9.9.9": 25}
        ),
        nginx_config_valida=False,
        nginx_config_detalhe="nginx -t falhou",
    )


class TestRunOnceConjuntoExato:
    def test_produz_exatamente_o_conjunto_esperado(self) -> None:
        gov = GovernanceEngine()
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"))

        alertas = watcher.run_once(_snapshot_rico())

        contagem = Counter((a.source.value, a.severity.value) for a in alertas)
        assert contagem == Counter(
            {
                ("endpoint-down", "critical"): 1,  # /health timeout (✗→✓)
                ("endpoint-latency", "critical"): 1,  # p95=1200 >= 1000
                ("endpoint-error-rate", "critical"): 1,  # nginx 8% >= 5%
                ("infra-saturation", "critical"): 1,  # cpu 95 >= 90
                ("infra-saturation", "warning"): 1,  # disk 85 (banda unica, sem crit junto)
                (
                    "security-intrusion",
                    "critical",
                ): 4,  # redis externo, xmrig, nginx invalido, ssh 25 falhas
                ("security-intrusion", "warning"): 3,  # 404 scanner, 401/403, headers
                ("service-down", "critical"): 2,  # nginx + gunicorn ausentes (✗→✓)
            }
        )

    def test_cada_alerta_foi_entregue_no_sink(self) -> None:
        sink = _SinkFake()
        gov = GovernanceEngine(sink=sink)
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"))

        alertas = watcher.run_once(_snapshot_rico())

        ids_retornados = {a.id for a in alertas}
        ids_entregues = {a.id for a in sink.entregues}
        assert ids_retornados == ids_entregues
        assert len(sink.entregues) == len(alertas)

    def test_metrica_nao_gera_warning_e_critical_juntos(self) -> None:
        # CPU=95 deve gerar SO um CRITICAL de infra, nunca WARNING+CRITICAL.
        gov = GovernanceEngine()
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"))
        snap = ObserveSnapshot(tenant_id=TenantId("acme"), infra=AmostraInfra(cpu_percent=95.0))
        alertas = watcher.run_once(snap)
        infra = [a for a in alertas if a.source == FonteAlerta.INFRA_SATURATION]
        assert len(infra) == 1
        assert infra[0].severity == SeveridadeAlerta.CRITICAL

    def test_snapshot_limpo_nao_gera_alertas(self) -> None:
        gov = GovernanceEngine()
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"))
        snap = ObserveSnapshot(
            tenant_id=TenantId("acme"),
            infra=AmostraInfra(cpu_percent=10.0, ram_percent=20.0, disk_percent=30.0),
            endpoints=[
                AmostraEndpoint(url="https://x", ok=True, status=200, latencias_janela_ms=[50.0])
            ],
            nginx=ContagemNginx(total=100, status_5xx=0),
        )
        assert watcher.run_once(snap) == []

    def test_run_once_deterministico_entre_ciclos(self) -> None:
        gov = GovernanceEngine()
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"))
        snap = _snapshot_rico()
        c1 = Counter((a.source.value, a.severity.value) for a in watcher.run_once(snap))
        c2 = Counter((a.source.value, a.severity.value) for a in watcher.run_once(snap))
        assert c1 == c2  # nenhum ponto obsoleto acumulado entre ciclos


class TestHeartbeat:
    def test_emite_mesmo_quando_limpo(self) -> None:
        sink = _SinkFake()
        gov = GovernanceEngine(sink=sink)
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"))

        alerta = watcher.heartbeat(ObserveSnapshot(tenant_id=TenantId("acme")), houve_alerta=False)

        assert alerta.source == FonteAlerta.OBSERVE_HEARTBEAT
        assert alerta.severity == SeveridadeAlerta.INFO
        assert any("status=tudo-limpo" in linha for linha in alerta.evidence[0].evidencias)
        assert len(sink.entregues) == 1

    def test_heartbeat_de_atencao_quando_ha_alerta(self) -> None:
        gov = GovernanceEngine()
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"))
        alerta = watcher.heartbeat(ObserveSnapshot(tenant_id=TenantId("acme")), houve_alerta=True)
        assert any("status=atencao" in linha for linha in alerta.evidence[0].evidencias)

    def test_self_heartbeat_a_cada_n_ciclos(self) -> None:
        sink = _SinkFake()
        gov = GovernanceEngine(sink=sink)
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"), ciclos_por_heartbeat=3)

        def coletar() -> ObserveSnapshot:
            return ObserveSnapshot(tenant_id=TenantId("acme"))  # limpo

        watcher.run_forever(intervalo=0.0, coletar=coletar, max_ciclos=6, dormir=lambda s: None)

        hb = [a for a in sink.entregues if a.source == FonteAlerta.OBSERVE_HEARTBEAT]
        assert len(hb) == 2  # ciclos 3 e 6
        # o self-heartbeat prova liveness mesmo com o daemon 100% limpo


class TestRunForeverBestEffort:
    def test_excecao_num_ciclo_nao_derruba_o_loop(self) -> None:
        gov = GovernanceEngine()
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"), ciclos_por_heartbeat=100)
        chamadas: list[int] = []

        def coletar() -> ObserveSnapshot:
            chamadas.append(1)
            if len(chamadas) == 2:
                raise RuntimeError("coleta falhou neste ciclo")
            return ObserveSnapshot(
                tenant_id=TenantId("acme"),
                endpoints=[AmostraEndpoint(url="https://x", ok=False, error="down")],
            )

        ciclos = watcher.run_forever(
            intervalo=0.0, coletar=coletar, max_ciclos=3, dormir=lambda s: None
        )

        assert ciclos == 3  # rodou os 3, apesar da excecao no 2o
        assert len(chamadas) == 3
        # os ciclos 1 e 3 (validos) emitiram endpoint-down; o 2o falhou e foi ignorado
        down = gov.get_open_alerts(source=FonteAlerta.ENDPOINT_DOWN)
        assert len(down) == 2

    def test_evento_de_parada_encerra_o_loop(self) -> None:
        gov = GovernanceEngine()
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"))

        class _Parada:
            def __init__(self) -> None:
                self._contador = 0

            def is_set(self) -> bool:
                self._contador += 1
                return self._contador > 2

        ciclos = watcher.run_forever(
            intervalo=0.0,
            coletar=lambda: ObserveSnapshot(tenant_id=TenantId("acme")),
            parar=_Parada(),
            dormir=lambda s: None,
        )
        assert ciclos <= 2

    def test_dormir_e_chamado_entre_ciclos(self) -> None:
        gov = GovernanceEngine()
        watcher = ObserveWatcher(gov, tenant_id=TenantId("acme"), ciclos_por_heartbeat=100)
        sonos: list[float] = []
        watcher.run_forever(
            intervalo=1.5,
            coletar=lambda: ObserveSnapshot(tenant_id=TenantId("acme")),
            max_ciclos=2,
            dormir=lambda s: sonos.append(s),
        )
        # dorme entre ciclos, mas nao apos o ultimo
        assert sonos == [1.5]
