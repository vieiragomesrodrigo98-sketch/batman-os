"""Testes das watch_rules — cada regra: caso que dispara + caso que nao
dispara (com exclusoes/allowlist). As 5 regras ✗→✓ que o legado NUNCA
emitia sao provadas explicitamente na classe `TestRegrasQuebradasAgoraEmitem`.
Regras de metrica-limiar sao cobertas pelos helpers de banda/serie."""

from __future__ import annotations

from batman_os.foundation.types import TenantId, agora
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceAlert,
    SeveridadeAlerta,
)
from batman_os.observe import watch_rules as wr
from batman_os.observe.snapshot import (
    AmostraAuth,
    AmostraEndpoint,
    AmostraInfra,
    AmostraPortas,
    ContagemNginx,
    ObserveSnapshot,
    PortaEscuta,
)


def _snap(**kwargs: object) -> ObserveSnapshot:
    base: dict[str, object] = {"tenant_id": TenantId("acme")}
    base.update(kwargs)
    return ObserveSnapshot(**base)


def _severidade_origem(alerta: GovernanceAlert) -> str | None:
    for linha in alerta.evidence[0].evidencias:
        if linha.startswith("severidade_origem:"):
            return linha.split(":", 1)[1].strip()
    return None


# ---------------------------------------------------------------------------
# As 5 ✗→✓ (endpoint-down, processo suspeito, servico caido, nginx invalido,
# headers ausentes) — o contrato exige provar que passam a emitir.
# ---------------------------------------------------------------------------
class TestRegrasQuebradasAgoraEmitem:
    def test_endpoint_down_emite_critical(self) -> None:
        snap = _snap(endpoints=[AmostraEndpoint(url="https://x/health", ok=False, error="timeout")])
        alertas = wr.regra_endpoint_down(snap)
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.ENDPOINT_DOWN
        assert alertas[0].severity == SeveridadeAlerta.CRITICAL
        assert alertas[0].related_tenant_id == TenantId("acme")

    def test_processo_suspeito_emite_critical(self) -> None:
        snap = _snap(processos_rodando=["bash", "XMRIG", "nginx"])
        alertas = wr.regra_processo_suspeito(snap)
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.SECURITY_INTRUSION
        assert alertas[0].severity == SeveridadeAlerta.CRITICAL
        assert "xmrig" in alertas[0].evidence[0].evidencias[0]

    def test_servico_caido_emite_critical(self) -> None:
        snap = _snap(processos_rodando=["nginx"], processos_esperados=["nginx", "gunicorn"])
        alertas = wr.regra_processo_ausente(snap)
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.SERVICE_DOWN
        assert alertas[0].severity == SeveridadeAlerta.CRITICAL
        # granularidade legada preservada (dispatcher classificava HIGH)
        assert _severidade_origem(alertas[0]) == "HIGH"

    def test_nginx_invalido_emite_critical(self) -> None:
        snap = _snap(nginx_config_valida=False, nginx_config_detalhe="nginx -t falhou")
        alertas = wr.regra_nginx_config(snap)
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.SECURITY_INTRUSION
        assert alertas[0].severity == SeveridadeAlerta.CRITICAL

    def test_headers_ausentes_emite_warning(self) -> None:
        snap = _snap(
            endpoints=[
                AmostraEndpoint(
                    url="https://x",
                    ok=True,
                    status=200,
                    headers_presentes=["Strict-Transport-Security"],
                )
            ]
        )
        alertas = wr.regra_headers_ausentes(snap)
        assert len(alertas) == 1
        assert alertas[0].severity == SeveridadeAlerta.WARNING
        faltando = alertas[0].evidence[0].evidencias[1]
        assert "Content-Security-Policy" in faltando
        assert "X-Frame-Options" in faltando


# ---------------------------------------------------------------------------
# Cada regra: dispara vs nao dispara
# ---------------------------------------------------------------------------
class TestEndpointDown:
    def test_nao_dispara_quando_ok(self) -> None:
        snap = _snap(endpoints=[AmostraEndpoint(url="https://x", ok=True, status=200)])
        assert wr.regra_endpoint_down(snap) == []


class TestEndpointExposto:
    def test_dispara_quando_exposto(self) -> None:
        snap = _snap(
            endpoints=[AmostraEndpoint(url="https://x/admin", ok=True, status=200, exposto=True)]
        )
        alertas = wr.regra_endpoint_exposto(snap)
        assert len(alertas) == 1
        assert alertas[0].severity == SeveridadeAlerta.WARNING
        assert _severidade_origem(alertas[0]) == "HIGH"

    def test_nao_dispara_quando_nao_exposto(self) -> None:
        snap = _snap(endpoints=[AmostraEndpoint(url="https://x", ok=True, status=200)])
        assert wr.regra_endpoint_exposto(snap) == []


class TestPorta:
    def test_externa_e_critical(self) -> None:
        snap = _snap(
            portas=AmostraPortas(
                inesperadas=[PortaEscuta(port=6379, bind="0.0.0.0", service="redis")]
            )
        )
        alertas = wr.regra_porta(snap)
        assert len(alertas) == 1
        assert alertas[0].severity == SeveridadeAlerta.CRITICAL
        assert any("servico_perigoso" in linha for linha in alertas[0].evidence[0].evidencias)

    def test_loopback_e_warning(self) -> None:
        snap = _snap(
            portas=AmostraPortas(
                inesperadas=[PortaEscuta(port=9000, bind="127.0.0.1", service="app")]
            )
        )
        alertas = wr.regra_porta(snap)
        assert len(alertas) == 1
        assert alertas[0].severity == SeveridadeAlerta.WARNING

    def test_porta_de_manutencao_e_info(self) -> None:
        snap = _snap(portas=AmostraPortas(inesperadas=[PortaEscuta(port=5678, bind="127.0.0.1")]))
        alertas = wr.regra_porta(snap)
        assert len(alertas) == 1
        assert alertas[0].severity == SeveridadeAlerta.INFO
        assert _severidade_origem(alertas[0]) == "LOW"

    def test_allowlist_sem_inesperadas_nao_dispara(self) -> None:
        snap = _snap(portas=AmostraPortas(listening=[22, 80, 443], inesperadas=[]))
        assert wr.regra_porta(snap) == []

    def test_erro_de_coleta_nao_dispara(self) -> None:
        snap = _snap(portas=AmostraPortas(erro="sem permissao"))
        assert wr.regra_porta(snap) == []


class TestProcessoSuspeito:
    def test_nao_dispara_sem_suspeito(self) -> None:
        snap = _snap(processos_rodando=["bash", "nginx", "python"])
        assert wr.regra_processo_suspeito(snap) == []


class TestProcessoAusente:
    def test_nao_dispara_quando_todos_presentes(self) -> None:
        snap = _snap(
            processos_rodando=["nginx", "gunicorn"], processos_esperados=["nginx", "gunicorn"]
        )
        assert wr.regra_processo_ausente(snap) == []


class TestNginxConfig:
    def test_mudanca_valida_e_warning(self) -> None:
        snap = _snap(nginx_config_valida=True, nginx_config_detalhe="server_name alterado")
        alertas = wr.regra_nginx_config(snap)
        assert len(alertas) == 1
        assert alertas[0].severity == SeveridadeAlerta.WARNING

    def test_valida_sem_detalhe_nao_dispara(self) -> None:
        assert wr.regra_nginx_config(_snap(nginx_config_valida=True)) == []

    def test_nao_verificado_nao_dispara(self) -> None:
        assert wr.regra_nginx_config(_snap()) == []


class TestHeaders:
    def test_todos_presentes_nao_dispara(self) -> None:
        snap = _snap(
            endpoints=[
                AmostraEndpoint(
                    url="https://x",
                    ok=True,
                    status=200,
                    headers_presentes=[
                        "Strict-Transport-Security",
                        "Content-Security-Policy",
                        "X-Frame-Options",
                    ],
                )
            ]
        )
        assert wr.regra_headers_ausentes(snap) == []

    def test_nao_coletado_nao_dispara(self) -> None:
        snap = _snap(endpoints=[AmostraEndpoint(url="https://x", ok=True, status=200)])
        assert wr.regra_headers_ausentes(snap) == []


class TestSSHBruteForce:
    def test_dez_falhas_e_warning(self) -> None:
        snap = _snap(auth=AmostraAuth(total_linhas=100, falhas=10, ip_top="9.9.9.9"))
        alertas = wr.regra_ssh_bruteforce(snap)
        assert len(alertas) == 1
        assert alertas[0].severity == SeveridadeAlerta.WARNING
        assert _severidade_origem(alertas[0]) == "HIGH"

    def test_vinte_falhas_e_critical(self) -> None:
        snap = _snap(auth=AmostraAuth(total_linhas=100, falhas=22, ip_top="9.9.9.9"))
        alertas = wr.regra_ssh_bruteforce(snap)
        assert alertas[0].severity == SeveridadeAlerta.CRITICAL

    def test_auth_bypass_calculado_e_critical(self) -> None:
        # login aceito de um IP com muitas falhas = sucesso anomalo (o legado
        # hardcodava auth_bypass=False; aqui e calculado).
        snap = _snap(
            auth=AmostraAuth(
                total_linhas=100,
                falhas=12,
                ip_top="9.9.9.9",
                falhas_por_ip={"9.9.9.9": 12},
                sucessos_por_ip={"9.9.9.9": 1},
            )
        )
        alertas = wr.regra_ssh_bruteforce(snap)
        assert len(alertas) == 1
        assert alertas[0].severity == SeveridadeAlerta.CRITICAL
        assert any("auth_bypass=sim" in linha for linha in alertas[0].evidence[0].evidencias)

    def test_sucesso_sem_falhas_nao_e_bypass(self) -> None:
        snap = _snap(
            auth=AmostraAuth(
                total_linhas=100,
                falhas=2,
                falhas_por_ip={"9.9.9.9": 2},
                sucessos_por_ip={"9.9.9.9": 1},
            )
        )
        assert wr.regra_ssh_bruteforce(snap) == []

    def test_poucas_falhas_nao_dispara(self) -> None:
        snap = _snap(auth=AmostraAuth(total_linhas=100, falhas=3))
        assert wr.regra_ssh_bruteforce(snap) == []


class TestBruteForce404:
    def test_ip_acima_do_limiar_dispara(self) -> None:
        snap = _snap(nginx=ContagemNginx(total=200, por_ip_404={"1.2.3.4": 40, "5.6.7.8": 5}))
        alertas = wr.regra_bruteforce_404(snap)
        assert len(alertas) == 1
        assert "1.2.3.4" in alertas[0].evidence[0].evidencias[0]

    def test_abaixo_do_limiar_nao_dispara(self) -> None:
        snap = _snap(nginx=ContagemNginx(total=200, por_ip_404={"1.2.3.4": 29}))
        assert wr.regra_bruteforce_404(snap) == []


class TestNaoAutorizado:
    def test_taxa_alta_dispara(self) -> None:
        snap = _snap(nginx=ContagemNginx(total=100, auth_401_403=20))
        alertas = wr.regra_nao_autorizado(snap)
        assert len(alertas) == 1
        assert alertas[0].severity == SeveridadeAlerta.WARNING

    def test_poucos_requests_nao_dispara(self) -> None:
        snap = _snap(nginx=ContagemNginx(total=10, auth_401_403=10))
        assert wr.regra_nao_autorizado(snap) == []

    def test_taxa_baixa_nao_dispara(self) -> None:
        snap = _snap(nginx=ContagemNginx(total=100, auth_401_403=10))
        assert wr.regra_nao_autorizado(snap) == []


# ---------------------------------------------------------------------------
# Severidade granular preservada (mapa legado -> Batman OS)
# ---------------------------------------------------------------------------
class TestMapeamentoSeveridade:
    def test_mapa_completo(self) -> None:
        assert wr.mapear_severidade(wr.SeveridadeOrigem.LOW) == SeveridadeAlerta.INFO
        assert wr.mapear_severidade(wr.SeveridadeOrigem.MEDIUM) == SeveridadeAlerta.WARNING
        assert wr.mapear_severidade(wr.SeveridadeOrigem.HIGH) == SeveridadeAlerta.WARNING
        assert wr.mapear_severidade(wr.SeveridadeOrigem.CRITICAL) == SeveridadeAlerta.CRITICAL


# ---------------------------------------------------------------------------
# Regras de metrica-limiar — helpers de banda/serie/leitura
# ---------------------------------------------------------------------------
class TestPercentil95:
    def test_janela_real_captura_latencia_sustentada(self) -> None:
        # 10% de amostras altas (2/20) entram no p95 (nearest-rank).
        valores = [100.0] * 18 + [1500.0, 1500.0]
        assert wr.percentil_95(valores) == 1500.0

    def test_p95_resiste_a_spike_isolado(self) -> None:
        # 1 spike em 20 (top 5%) NAO contamina o p95 — a melhoria sobre o
        # legado, que rotulava a latencia de 1 request como "p95".
        valores = [100.0] * 19 + [1500.0]
        assert wr.percentil_95(valores) == 100.0

    def test_uma_amostra(self) -> None:
        assert wr.percentil_95([700.0]) == 700.0

    def test_vazio_e_none(self) -> None:
        assert wr.percentil_95([]) is None


class TestRoteamentoDeBanda:
    def test_valor_critical_alimenta_so_a_serie_crit(self) -> None:
        series = wr.series_da_banda(wr.METRIC_CPU, wr.LIMIAR_CPU, 95.0, agora())
        por_id = {str(s.metric_id): s for s in series}
        assert por_id["observe.cpu:warn"].points == []
        assert len(por_id["observe.cpu:crit"].points) == 1

    def test_valor_warning_alimenta_so_a_serie_warn(self) -> None:
        series = wr.series_da_banda(wr.METRIC_CPU, wr.LIMIAR_CPU, 85.0, agora())
        por_id = {str(s.metric_id): s for s in series}
        assert len(por_id["observe.cpu:warn"].points) == 1
        assert por_id["observe.cpu:crit"].points == []

    def test_valor_no_piso_ainda_dispara_inclusivo(self) -> None:
        series = wr.series_da_banda(wr.METRIC_CPU, wr.LIMIAR_CPU, 80.0, agora())
        por_id = {str(s.metric_id): s for s in series}
        ponto = por_id["observe.cpu:warn"].points[0]
        assert ponto.value > wr.LIMIAR_CPU.warning  # empurrado 1 epsilon acima do piso

    def test_valor_abaixo_nao_alimenta_nada(self) -> None:
        series = wr.series_da_banda(wr.METRIC_CPU, wr.LIMIAR_CPU, 50.0, agora())
        assert all(s.points == [] for s in series)


class TestLeiturasDeMetrica:
    def test_infra_gera_cpu_ram_disk(self) -> None:
        snap = _snap(infra=AmostraInfra(cpu_percent=10.0, ram_percent=20.0, disk_percent=30.0))
        bases = {base for base, _, _ in wr.leituras_de_metrica(snap)}
        assert {wr.METRIC_CPU, wr.METRIC_RAM, wr.METRIC_DISK} <= bases

    def test_endpoint_down_nao_gera_leitura_de_latencia(self) -> None:
        snap = _snap(endpoints=[AmostraEndpoint(url="https://x", ok=False, error="timeout")])
        bases = {base for base, _, _ in wr.leituras_de_metrica(snap)}
        assert not any(b.startswith("observe.latency:") for b in bases)

    def test_endpoint_ok_gera_latencia_p95(self) -> None:
        snap = _snap(
            endpoints=[
                AmostraEndpoint(
                    url="https://x", ok=True, status=200, latencias_janela_ms=[600.0, 700.0, 1200.0]
                )
            ]
        )
        leituras = {base: valor for base, _, valor in wr.leituras_de_metrica(snap)}
        assert leituras["observe.latency:https://x"] == 1200.0

    def test_nginx_gera_error_rate(self) -> None:
        snap = _snap(nginx=ContagemNginx(total=100, status_5xx=8))
        leituras = {base: valor for base, _, valor in wr.leituras_de_metrica(snap)}
        assert leituras["observe.error_rate:nginx"] == 8.0
