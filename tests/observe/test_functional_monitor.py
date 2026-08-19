"""Testes do `FunctionalMonitor` — run_once (ok/down/conteudo/recuperacao),
casos nao-outage (carteira 403/503, chat 429), auth sintetica (token reusado
como Bearer; credencial ausente => config, nao outage), drift (feature removida
/ rota nova) e best-effort. Sonda e credenciais FAKE — zero rede."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from batman_os.foundation.types import TenantId
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceAlert,
    GovernanceEngine,
    SeveridadeAlerta,
)
from batman_os.observe.feature_manifest import (
    AuthConfig,
    DriftConfig,
    FeatureCheck,
    FeatureManifest,
    MetodoHttp,
    TipoAuth,
)
from batman_os.observe.functional_monitor import FunctionalMonitor, RespostaSonda


class _SinkFake:
    def __init__(self) -> None:
        self.entregues: list[GovernanceAlert] = []

    def enviar(self, alert: GovernanceAlert) -> None:
        self.entregues.append(alert)


class _SondaFake:
    """Sonda programavel por caminho. Registra cada chamada (para asserir
    Bearer, corpo, reuso de login). Uma resposta `Exception` levanta (best-effort)."""

    def __init__(self) -> None:
        self.por_caminho: dict[str, RespostaSonda | Exception] = {}
        self.chamadas: list[dict[str, object]] = []

    def responder(self, caminho: str, resp: RespostaSonda | Exception) -> None:
        self.por_caminho[caminho] = resp

    def sondar(
        self,
        *,
        url: str,
        metodo: str = "GET",
        headers: Mapping[str, str] | None = None,
        corpo: Mapping[str, Any] | None = None,
        timeout_s: float = 8.0,
    ) -> RespostaSonda:
        caminho = urlparse(url).path
        self.chamadas.append(
            {
                "caminho": caminho,
                "metodo": metodo,
                "headers": dict(headers) if headers else {},
                "corpo": dict(corpo) if corpo else {},
            }
        )
        resp = self.por_caminho.get(caminho)
        if resp is None:
            raise AssertionError(f"_SondaFake sem resposta para {caminho}")
        if isinstance(resp, Exception):
            raise resp
        return resp


class _CredsFake:
    def __init__(self, mapa: dict[str, str]) -> None:
        self._mapa = mapa

    def obter(self, nome_var: str) -> str | None:
        return self._mapa.get(nome_var)


def _auth() -> AuthConfig:
    return AuthConfig(
        endpoint="/api/auth/login",
        env_credencial="CPF",
        env_senha="SENHA",
        env_credencial_prime="PCPF",
        env_senha_prime="PSENHA",
    )


def _manifest(features: list[FeatureCheck], tenant: str = "acme") -> FeatureManifest:
    return FeatureManifest(
        tenant_id=TenantId(tenant),
        base_url="https://x",
        revisado_em="2026-07-22",
        auth=_auth(),
        features=features,
    )


def _check(
    id_: str = "syn-health",
    caminho: str = "/api/health",
    *,
    auth: TipoAuth = "none",
    espera_conteudo: str | None = None,
    severidade: SeveridadeAlerta = SeveridadeAlerta.CRITICAL,
    status_tolerados: list[int] | None = None,
    corpo: dict[str, Any] | None = None,
    metodo: MetodoHttp = "GET",
) -> FeatureCheck:
    return FeatureCheck(
        id=id_,
        descricao=f"desc {id_}",
        metodo=metodo,
        caminho=caminho,
        espera_conteudo=espera_conteudo,
        auth=auth,
        severidade_se_cair=severidade,
        timeout_s=8,
        status_tolerados=status_tolerados or [],
        corpo=corpo,
    )


_LOGIN_OK = RespostaSonda(status=200, corpo='{"access_token": "tok-abc", "role": "viewer"}')


class TestRunOnceBasico:
    def test_feature_ok_nao_gera_alerta(self) -> None:
        sonda = _SondaFake()
        sonda.responder("/api/health", RespostaSonda(status=200, corpo='{"status": "ok"}'))
        gov = GovernanceEngine(sink=_SinkFake())
        monitor = FunctionalMonitor(gov, sondador=sonda)
        alertas = monitor.run_once(_manifest([_check(espera_conteudo='.status == "ok"')]))
        assert alertas == []

    def test_feature_down_emite_e_entrega_feature_down(self) -> None:
        sonda = _SondaFake()
        sonda.responder("/api/health", RespostaSonda(status=None, down=True, erro="timeout"))
        sink = _SinkFake()
        gov = GovernanceEngine(sink=sink)
        monitor = FunctionalMonitor(gov, sondador=sonda)
        alertas = monitor.run_once(_manifest([_check()]))
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.FEATURE_DOWN
        assert alertas[0].severity == SeveridadeAlerta.CRITICAL
        # entregue no sink (dedupe do sink cuida de nao spammar em ciclos seguintes)
        assert [a.id for a in sink.entregues] == [a.id for a in alertas]
        # evidencia carrega esperado-vs-obtido
        linhas = "\n".join(alertas[0].evidence[0].evidencias)
        assert "down real" in linhas

    def test_conteudo_faltando_vira_feature_down(self) -> None:
        sonda = _SondaFake()
        sonda.responder("/api/health", RespostaSonda(status=200, corpo='{"status": "degraded"}'))
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(gov, sondador=sonda)
        alertas = monitor.run_once(_manifest([_check(espera_conteudo='.status == "ok"')]))
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.FEATURE_DOWN
        assert "conteudo" in "\n".join(alertas[0].evidence[0].evidencias)

    def test_recuperacao_emite_feature_recovered(self) -> None:
        sonda = _SondaFake()
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(gov, sondador=sonda)
        manifest = _manifest([_check()])

        sonda.responder("/api/health", RespostaSonda(status=None, down=True, erro="timeout"))
        c1 = monitor.run_once(manifest)
        assert c1[0].source == FonteAlerta.FEATURE_DOWN

        sonda.responder("/api/health", RespostaSonda(status=200, corpo="{}"))
        c2 = monitor.run_once(manifest)
        assert len(c2) == 1
        assert c2[0].source == FonteAlerta.FEATURE_RECOVERED
        assert c2[0].severity == SeveridadeAlerta.INFO

        # ok e ja estava ok -> nada
        assert monitor.run_once(manifest) == []


class TestCasosNaoOutage:
    def test_carteira_403_e_503_nao_sao_outage(self) -> None:
        for status in (403, 503):
            sonda = _SondaFake()
            sonda.responder("/api/auth/login", _LOGIN_OK)
            sonda.responder("/api/recurso-c", RespostaSonda(status=status, corpo="{}"))
            gov = GovernanceEngine()
            monitor = FunctionalMonitor(
                gov,
                sondador=sonda,
                credenciais=_CredsFake({"PCPF": "111", "PSENHA": "s"}),
            )
            check = _check(
                "syn-recurso-c",
                "/api/recurso-c",
                auth="sessao-prime",
                severidade=SeveridadeAlerta.INFO,
                status_tolerados=[403, 503],
            )
            assert monitor.run_once(_manifest([check])) == []

    def test_chat_429_quota_tratado_como_nao_outage(self) -> None:
        sonda = _SondaFake()
        sonda.responder("/api/auth/login", _LOGIN_OK)
        sonda.responder("/api/recurso-d/message", RespostaSonda(status=429, corpo="{}"))
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(
            gov, sondador=sonda, credenciais=_CredsFake({"CPF": "1", "SENHA": "s"})
        )
        check = _check(
            "syn-recurso-d-chat",
            "/api/recurso-d/message",
            auth="sessao",
            metodo="POST",
            status_tolerados=[429],
            corpo={"session_id": "<uuid4>", "message": "ping"},
        )
        assert monitor.run_once(_manifest([check])) == []


class TestAuthSintetica:
    def test_login_obtem_token_e_reusa_como_bearer(self) -> None:
        sonda = _SondaFake()
        sonda.responder("/api/auth/login", _LOGIN_OK)
        sonda.responder("/api/recurso-a", RespostaSonda(status=200, corpo="[]"))
        sonda.responder("/api/recurso-h", RespostaSonda(status=200, corpo="{}"))
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(
            gov, sondador=sonda, credenciais=_CredsFake({"CPF": "1", "SENHA": "s"})
        )
        manifest = _manifest(
            [
                _check(
                    "syn-recurso-a", "/api/recurso-a", auth="sessao", espera_conteudo=". is array"
                ),
                _check("syn-recurso-h", "/api/recurso-h", auth="sessao"),
            ]
        )
        assert monitor.run_once(manifest) == []

        # login chamado UMA vez (token reusado entre os dois checks de sessao)
        logins = [c for c in sonda.chamadas if c["caminho"] == "/api/auth/login"]
        assert len(logins) == 1
        # o Bearer foi para as chamadas de feature
        sinais = next(c for c in sonda.chamadas if c["caminho"] == "/api/recurso-a")
        assert sinais["headers"] == {"Authorization": "Bearer tok-abc"}

    def test_credencial_ausente_nao_e_outage(self) -> None:
        sonda = _SondaFake()
        sonda.responder("/api/recurso-a", RespostaSonda(status=200, corpo="[]"))
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(gov, sondador=sonda, credenciais=_CredsFake({}))
        alertas = monitor.run_once(
            _manifest([_check("syn-recurso-a", "/api/recurso-a", auth="sessao")])
        )
        # nenhum FEATURE_DOWN — o check nao rodou (config, nao outage)
        assert alertas == []
        assert "syn-recurso-a" in monitor.ultimos_pulados
        # nunca chegou a sondar a feature
        assert not any(c["caminho"] == "/api/recurso-a" for c in sonda.chamadas)

    def test_login_corpo_usa_placeholders_de_credencial(self) -> None:
        sonda = _SondaFake()
        sonda.responder(
            "/api/auth/login",
            RespostaSonda(status=200, corpo='{"access_token": "t", "role": "v"}'),
        )
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(
            gov, sondador=sonda, credenciais=_CredsFake({"CPF": "12345", "SENHA": "segredo"})
        )
        check = _check(
            "syn-auth-login",
            "/api/auth/login",
            metodo="POST",
            espera_conteudo=".access_token is nonempty",
            corpo={"cpf": "<cpf>", "password": "<senha>"},
        )
        assert monitor.run_once(_manifest([check])) == []
        login = next(c for c in sonda.chamadas if c["caminho"] == "/api/auth/login")
        assert login["corpo"] == {"cpf": "12345", "password": "segredo"}


class TestDrift:
    def test_feature_removida_gera_manifest_drift(self) -> None:
        sink = _SinkFake()
        gov = GovernanceEngine(sink=sink)
        monitor = FunctionalMonitor(gov, sondador=_SondaFake())
        manifest = _manifest([_check("syn-recurso-a", "/api/recurso-a", auth="sessao")])
        # /api/recurso-a sumiu das rotas reais
        alertas = monitor.checar_drift(manifest, rotas_reais=["/api/health", "/api/recurso-h"])
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.MANIFEST_DRIFT
        assert alertas[0].severity == SeveridadeAlerta.WARNING
        texto = "\n".join(e for ev in alertas[0].evidence for e in ev.evidencias)
        assert "/api/recurso-a" in texto
        assert sink.entregues  # entregue via sink

    def test_rota_nova_sem_cobertura_gera_drift_e_ignora_borda(self) -> None:
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(gov, sondador=_SondaFake())
        manifest = FeatureManifest(
            tenant_id=TenantId("acme"),
            base_url="https://x",
            revisado_em="2026-07-22",
            auth=_auth(),
            features=[_check("syn-health", "/api/health")],
            drift=DriftConfig(rotas_ignoradas=["^/api/admin/"]),
        )
        alertas = monitor.checar_drift(
            manifest,
            rotas_reais=["/api/health", "/api/nova-feature", "/api/admin/deploy"],
        )
        assert len(alertas) == 1
        texto = "\n".join(e for ev in alertas[0].evidence for e in ev.evidencias)
        assert "/api/nova-feature" in texto
        assert "/api/admin/deploy" not in texto  # rota de borda ignorada

    def test_sem_drift_nao_alarma(self) -> None:
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(gov, sondador=_SondaFake())
        manifest = _manifest([_check("syn-health", "/api/health")])
        assert monitor.checar_drift(manifest, rotas_reais=["/api/health"]) == []

    def test_404_consistente_vira_drift_nao_outage(self) -> None:
        sonda = _SondaFake()
        sonda.responder("/api/removida", RespostaSonda(status=404, corpo="not found"))
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(gov, sondador=sonda)
        manifest = FeatureManifest(
            tenant_id=TenantId("acme"),
            base_url="https://x",
            revisado_em="2026-07-22",
            auth=_auth(),
            features=[_check("syn-removida", "/api/removida")],
            drift=DriftConfig(ciclos_para_confirmar_removida=2),
        )
        # ciclo 1: ainda nao confirma -> nenhum alerta (nunca FEATURE_DOWN por 404)
        assert monitor.run_once(manifest) == []
        # ciclo 2: confirma -> MANIFEST_DRIFT
        c2 = monitor.run_once(manifest)
        assert len(c2) == 1
        assert c2[0].source == FonteAlerta.MANIFEST_DRIFT


class TestBestEffortEMultiTenant:
    def test_check_que_levanta_nao_impede_os_outros(self) -> None:
        sonda = _SondaFake()
        sonda.responder("/api/a", RuntimeError("sonda explodiu neste check"))
        sonda.responder("/api/b", RespostaSonda(status=None, down=True, erro="timeout"))
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(gov, sondador=sonda)
        manifest = _manifest([_check("syn-a", "/api/a"), _check("syn-b", "/api/b")])
        alertas = monitor.run_once(manifest)
        # o check A levantou e foi ignorado; B ainda produziu seu FEATURE_DOWN
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.FEATURE_DOWN
        assert "syn-b" in alertas[0].evidence[0].origem

    def test_alertas_carregam_related_tenant_id(self) -> None:
        sonda = _SondaFake()
        sonda.responder("/api/health", RespostaSonda(status=None, down=True, erro="x"))
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(gov, sondador=sonda)
        alertas = monitor.run_once(_manifest([_check()], tenant="cliente-xyz"))
        assert alertas[0].related_tenant_id == TenantId("cliente-xyz")

    def test_run_forever_best_effort_conta_ciclos(self) -> None:
        sonda = _SondaFake()
        sonda.responder("/api/health", RespostaSonda(status=200, corpo="{}"))
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(gov, sondador=sonda)
        ciclos = monitor.run_forever(
            _manifest([_check()]), intervalo=0.0, max_ciclos=3, dormir=lambda s: None
        )
        assert ciclos == 3

    def test_check_desabilitado_nao_roda(self) -> None:
        sonda = _SondaFake()
        gov = GovernanceEngine()
        monitor = FunctionalMonitor(gov, sondador=sonda)
        check = FeatureCheck(
            id="syn-off",
            descricao="desligado",
            caminho="/api/off",
            severidade_se_cair=SeveridadeAlerta.CRITICAL,
            timeout_s=8,
            habilitado=False,
        )
        assert monitor.run_once(_manifest([check])) == []
        assert sonda.chamadas == []
