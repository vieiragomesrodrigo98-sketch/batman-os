"""Testes do `batman observe` — daemon de observabilidade de infra.

`executar_observe` roda UM ciclo com coletores fake + sink fake (emite e
entrega alertas, best-effort quando um coletor levanta, tenant propagado); o
wiring da CLI `batman observe` roda sem rede/psutil (coletores fake via
`monkeypatch` + `--max-ciclos 1`). Zero rede, zero psutil real."""

from __future__ import annotations

import pytest

from batman_os.cli import observe_command
from batman_os.cli.batman import main
from batman_os.cli.observe_command import Coletores, coletar_snapshot, executar_observe
from batman_os.foundation.types import TenantId
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceAlert,
    GovernanceEngine,
)
from batman_os.observe.snapshot import (
    AmostraAuth,
    AmostraEndpoint,
    AmostraInfra,
    AmostraPortas,
    ContagemNginx,
)

TENANT = TenantId("acme")


# ---------------------------------------------------------------------------
# Fakes das cinco bordas de coleta (satisfazem os Protocols de collectors.py)
# ---------------------------------------------------------------------------
class _InfraFake:
    def __init__(self, amostra: AmostraInfra) -> None:
        self._amostra = amostra

    def coletar(self) -> AmostraInfra:
        return self._amostra


class _EndpointFake:
    def __init__(self, por_url: dict[str, AmostraEndpoint]) -> None:
        self._por_url = por_url

    def coletar(self, url: str) -> AmostraEndpoint:
        return self._por_url[url]


class _PortasFake:
    def __init__(self, amostra: AmostraPortas) -> None:
        self._amostra = amostra

    def coletar(self) -> AmostraPortas:
        return self._amostra


class _LogFake:
    def __init__(self, nginx: ContagemNginx, auth: AmostraAuth) -> None:
        self._nginx = nginx
        self._auth = auth

    def coletar_nginx(self) -> ContagemNginx:
        return self._nginx

    def coletar_auth(self) -> AmostraAuth:
        return self._auth


class _ProcessoFake:
    def __init__(self, nomes: list[str]) -> None:
        self._nomes = nomes

    def coletar(self) -> list[str]:
        return self._nomes


class _InfraQueLevanta:
    def coletar(self) -> AmostraInfra:
        raise RuntimeError("psutil explodiu neste ciclo")


class _SinkFake:
    """Registra cada GovernanceAlert entregue (prova de entrega via sink)."""

    def __init__(self) -> None:
        self.entregues: list[GovernanceAlert] = []

    def enviar(self, alert: GovernanceAlert) -> None:
        self.entregues.append(alert)


def _coletores_limpos() -> Coletores:
    """Coletores fake de um ambiente saudavel (nenhum alerta)."""
    return Coletores(
        infra=_InfraFake(AmostraInfra(cpu_percent=10.0, ram_percent=20.0, disk_percent=30.0)),
        endpoint=_EndpointFake({}),
        portas=_PortasFake(AmostraPortas()),
        log=_LogFake(ContagemNginx(total=100, status_5xx=0), AmostraAuth()),
        processo=_ProcessoFake(["nginx", "gunicorn"]),
    )


# ---------------------------------------------------------------------------
# executar_observe — um ciclo
# ---------------------------------------------------------------------------
class TestExecutarObserve:
    def test_um_ciclo_emite_e_entrega_alertas(self) -> None:
        sink = _SinkFake()
        gov = GovernanceEngine(sink=sink)
        coletores = Coletores(
            infra=_InfraFake(AmostraInfra(cpu_percent=10.0)),
            endpoint=_EndpointFake(
                {
                    "https://x/health": AmostraEndpoint(
                        url="https://x/health", ok=False, status=None, error="timeout"
                    )
                }
            ),
            portas=_PortasFake(AmostraPortas()),
            log=_LogFake(ContagemNginx(total=0), AmostraAuth()),
            processo=_ProcessoFake(["nginx"]),
        )

        alertas = executar_observe(
            TENANT,
            coletores=coletores,
            urls_endpoints=["https://x/health"],
            processos_esperados=[],
            governance=gov,
        )

        assert any(a.source == FonteAlerta.ENDPOINT_DOWN for a in alertas)
        # cada alerta do ciclo foi entregue no sink (run_once entrega)
        assert {a.id for a in alertas} == {a.id for a in sink.entregues}
        assert len(sink.entregues) == len(alertas)

    def test_tenant_propagado_para_todos_os_alertas(self) -> None:
        coletores = Coletores(
            infra=_InfraFake(AmostraInfra(cpu_percent=95.0)),  # infra-saturation
            endpoint=_EndpointFake(
                {"https://x": AmostraEndpoint(url="https://x", ok=False, error="down")}
            ),
            portas=_PortasFake(AmostraPortas()),
            log=_LogFake(ContagemNginx(total=0), AmostraAuth()),
            processo=_ProcessoFake([]),
        )

        alertas = executar_observe(
            TENANT,
            coletores=coletores,
            urls_endpoints=["https://x"],
            processos_esperados=["nginx"],  # servico-caido
            governance=GovernanceEngine(),
        )

        assert alertas  # houve alertas de fato
        assert all(a.related_tenant_id == TENANT for a in alertas)
        fontes = {a.source for a in alertas}
        assert FonteAlerta.ENDPOINT_DOWN in fontes
        assert FonteAlerta.SERVICE_DOWN in fontes

    def test_best_effort_coletor_que_levanta_nao_derruba_o_ciclo(self) -> None:
        # infra levanta; o ciclo ainda roda e detecta o endpoint down real.
        coletores = Coletores(
            infra=_InfraQueLevanta(),
            endpoint=_EndpointFake(
                {"https://x": AmostraEndpoint(url="https://x", ok=False, error="down")}
            ),
            portas=_PortasFake(AmostraPortas()),
            log=_LogFake(ContagemNginx(total=0), AmostraAuth()),
            processo=_ProcessoFake([]),
        )

        alertas = executar_observe(
            TENANT,
            coletores=coletores,
            urls_endpoints=["https://x"],
            processos_esperados=[],
            governance=GovernanceEngine(),
        )

        assert any(a.source == FonteAlerta.ENDPOINT_DOWN for a in alertas)

    def test_ambiente_limpo_nao_gera_alertas(self) -> None:
        alertas = executar_observe(
            TENANT,
            coletores=_coletores_limpos(),
            urls_endpoints=[],
            processos_esperados=[],
            governance=GovernanceEngine(),
        )
        assert alertas == []


class TestColetarSnapshot:
    def test_coletor_de_endpoint_que_levanta_e_pulado(self) -> None:
        class _EndpointExplode:
            def coletar(self, url: str) -> AmostraEndpoint:
                raise RuntimeError("conexao recusada")

        coletores = Coletores(
            infra=_InfraFake(AmostraInfra(cpu_percent=10.0)),
            endpoint=_EndpointExplode(),
            portas=_PortasFake(AmostraPortas()),
            log=_LogFake(ContagemNginx(total=0), AmostraAuth()),
            processo=_ProcessoFake(["nginx"]),
        )

        snap = coletar_snapshot(
            TENANT, coletores, urls_endpoints=["https://x"], processos_esperados=["nginx"]
        )

        # o endpoint que explodiu foi pulado; o resto do snapshot esta intacto
        assert snap.endpoints == []
        assert snap.tenant_id == TENANT
        assert snap.processos_esperados == ["nginx"]
        assert snap.processos_rodando == ["nginx"]


# ---------------------------------------------------------------------------
# Wiring da CLI `batman observe` — sem rede/psutil (coletores fake)
# ---------------------------------------------------------------------------
class TestWiringCli:
    def test_main_observe_roda_ciclo_limitado_sem_rede(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(observe_command, "montar_coletores", _coletores_limpos)
        # sem env de webhook/endpoints => sink None, zero rede, zero psutil real

        codigo = main(["observe", "--tenant", "acme", "--intervalo", "0", "--max-ciclos", "1"])

        assert codigo == 0
        saida = capsys.readouterr().out
        assert "1 ciclo(s)" in saida
        assert "tenant=acme" in saida

    def test_observe_exige_tenant(self) -> None:
        try:
            main(["observe"])
        except SystemExit as exc:
            assert exc.code != 0
        else:
            raise AssertionError("esperava SystemExit sem --tenant")
