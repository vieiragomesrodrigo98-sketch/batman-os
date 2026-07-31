"""Testes do `batman monitor` — orquestrador `executar_monitor` (com sonda +
credenciais + governance injetaveis, sem rede) e o wiring `main(["monitor", ...])`
(manifesto todo desabilitado => um ciclo sem I/O). Zero rede."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from batman_os.cli.batman import main
from batman_os.cli.monitor_command import (
    alertas_para_inbox,
    executar_dados_sentinela,
    executar_monitor,
    resolver_manifest_dados_path,
    resolver_manifest_path,
)
from batman_os.foundation.types import Criticidade, Evidence, TenantId
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceAlert,
    GovernanceEngine,
    SeveridadeAlerta,
)
from batman_os.governance.inbox import InboxStore, OrigemAchado
from batman_os.observe.data_manifest import caminho_manifesto_dados
from batman_os.observe.feature_manifest import caminho_manifesto
from batman_os.observe.functional_monitor import RespostaSonda


class _SondaFake:
    def __init__(self, por_caminho: dict[str, RespostaSonda]) -> None:
        self._por = por_caminho

    def sondar(
        self,
        *,
        url: str,
        metodo: str = "GET",
        headers: object | None = None,
        corpo: object | None = None,
        timeout_s: float = 8.0,
    ) -> RespostaSonda:
        return self._por[urlparse(url).path]


def _escrever_manifesto(tmp_path: Path, features: list[dict[str, object]]) -> Path:
    dados = {
        "tenant_id": "acme",
        "base_url": "https://x",
        "revisado_em": "2026-07-22",
        "auth": {"endpoint": "/api/auth/login", "env_credencial": "CPF", "env_senha": "SENHA"},
        "features": features,
    }
    arq = tmp_path / "acme.json"
    arq.write_text(json.dumps(dados), encoding="utf-8")
    return arq


class TestExecutarMonitor:
    def test_roda_um_ciclo_com_sonda_fake(self, tmp_path: Path) -> None:
        arq = _escrever_manifesto(
            tmp_path,
            [
                {
                    "id": "syn-health",
                    "descricao": "saude",
                    "caminho": "/api/health",
                    "espera_conteudo": '.status == "ok"',
                    "severidade_se_cair": "critical",
                    "timeout_s": 5,
                }
            ],
        )
        sonda = _SondaFake({"/api/health": RespostaSonda(status=None, down=True, erro="timeout")})
        gov = GovernanceEngine()
        manifest, alertas = executar_monitor(arq, sondador=sonda, governance=gov)

        assert manifest.tenant_id == TenantId("acme")
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.FEATURE_DOWN

    def test_resolver_manifest_path_default_e_explicito(self) -> None:
        assert resolver_manifest_path("exemplo", None) == caminho_manifesto("exemplo")
        assert resolver_manifest_path("acme", "/tmp/x.json") == Path("/tmp/x.json")


def _escrever_manifesto_dados(tmp_path: Path, **overrides: object) -> Path:
    dados: dict[str, object] = {
        "tenant_id": "acme",
        "root_dir": str(tmp_path),
        "revisado_em": "2026-07-30",
        "fontes_jsonl": [],
        "fontes_idade": [],
    }
    dados.update(overrides)
    arq = tmp_path / "acme_dados.json"
    arq.write_text(json.dumps(dados), encoding="utf-8")
    return arq


class TestExecutarDadosSentinela:
    """`executar_dados_sentinela` — orquestrador da capability
    `dados-sentinela` (Onda 1, Plano Cobertura Total, S162), mesmo padrão
    de `executar_monitor` para o par HTTP."""

    def test_roda_um_ciclo_e_devolve_manifest_e_alertas(self, tmp_path: Path) -> None:
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "update_log.jsonl").write_text(
            json.dumps({"run_at": "2026-07-30T10:00:00+00:00", "status": "error"}) + "\n",
            encoding="utf-8",
        )
        arq = _escrever_manifesto_dados(
            tmp_path,
            fontes_jsonl=[{"id": "pipeline", "descricao": "d", "arquivo": "data/update_log.jsonl"}],
        )
        manifest, alertas = executar_dados_sentinela(arq, governance=GovernanceEngine())
        assert manifest.tenant_id == TenantId("acme")
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.DATA_PIPELINE_ERROR

    def test_root_dir_override_sobrescreve_o_do_manifesto(self, tmp_path: Path) -> None:
        outro_root = tmp_path / "outro"
        (outro_root / "data").mkdir(parents=True)
        (outro_root / "data" / "update_log.jsonl").write_text(
            json.dumps({"run_at": "2026-07-30T10:00:00+00:00", "status": "error"}) + "\n",
            encoding="utf-8",
        )
        # manifesto aponta para um root_dir que nao existe -- so funciona
        # por causa do override
        arq = _escrever_manifesto_dados(
            tmp_path,
            root_dir=str(tmp_path / "nao-existe"),
            fontes_jsonl=[{"id": "pipeline", "descricao": "d", "arquivo": "data/update_log.jsonl"}],
        )
        manifest, alertas = executar_dados_sentinela(
            arq, root_dir_override=str(outro_root), governance=GovernanceEngine()
        )
        assert manifest.root_dir == str(outro_root)
        assert len(alertas) == 1

    def test_resolver_manifest_dados_path_default_e_explicito(self) -> None:
        assert resolver_manifest_dados_path("exemplo", None) == caminho_manifesto_dados(
            "exemplo"
        )
        assert resolver_manifest_dados_path("acme", "/tmp/x.json") == Path("/tmp/x.json")


class TestWiringCli:
    def test_main_monitor_roda_ciclo_sem_rede(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        # todas as features desabilitadas => run_once nao sonda nada (zero rede)
        arq = _escrever_manifesto(
            tmp_path,
            [
                {
                    "id": "syn-off",
                    "descricao": "desligado",
                    "caminho": "/api/off",
                    "severidade_se_cair": "critical",
                    "timeout_s": 5,
                    "habilitado": False,
                }
            ],
        )
        codigo = main(["monitor", "--tenant", "acme", "--manifest", str(arq)])
        assert codigo == 0
        saida = capsys.readouterr().out
        assert "0 alerta(s)" in saida
        assert "tenant=acme" in saida

    def test_monitor_exige_tenant(self) -> None:
        try:
            main(["monitor"])
        except SystemExit as exc:
            assert exc.code != 0
        else:
            raise AssertionError("esperava SystemExit sem --tenant")

    def test_sem_dados_manifest_dados_sentinela_nao_roda(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        """Rollout pendente de autorização do DEV (deploy/batman-os-monitor.
        service não passa --dados-manifest) — sem a flag, comportamento
        idêntico ao `batman monitor` de antes desta capacidade."""
        arq = _escrever_manifesto(
            tmp_path,
            [
                {
                    "id": "syn-off",
                    "descricao": "desligado",
                    "caminho": "/api/off",
                    "severidade_se_cair": "critical",
                    "timeout_s": 5,
                    "habilitado": False,
                }
            ],
        )
        codigo = main(["monitor", "--tenant", "acme", "--manifest", str(arq)])
        assert codigo == 0
        saida = capsys.readouterr().out
        assert "dados-sentinela" not in saida

    def test_com_dados_manifest_dados_sentinela_roda_e_alerta(
        self,
        tmp_path: Path,
        capsys,  # type: ignore[no-untyped-def]
    ) -> None:
        arq_http = _escrever_manifesto(
            tmp_path,
            [
                {
                    "id": "syn-off",
                    "descricao": "desligado",
                    "caminho": "/api/off",
                    "severidade_se_cair": "critical",
                    "timeout_s": 5,
                    "habilitado": False,
                }
            ],
        )
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "update_log.jsonl").write_text(
            json.dumps({"run_at": "2026-07-30T21:32:00+00:00", "status": "error"}) + "\n",
            encoding="utf-8",
        )
        arq_dados = _escrever_manifesto_dados(
            tmp_path,
            fontes_jsonl=[{"id": "pipeline", "descricao": "d", "arquivo": "data/update_log.jsonl"}],
        )
        codigo = main(
            [
                "monitor",
                "--tenant",
                "acme",
                "--manifest",
                str(arq_http),
                "--dados-manifest",
                str(arq_dados),
            ]
        )
        assert codigo == 0
        saida = capsys.readouterr().out
        assert "dados-sentinela tenant=acme" in saida
        assert "data-pipeline-error" in saida
        assert "1 alerta(s)" in saida


class TestAlertasParaInbox:
    """Adaptador `GovernanceAlert` -> `AchadoInboxEntrada`
    (`alertas_para_inbox`) — ponto 4 do pacote da capacidade Inbox."""

    def test_severidade_e_traduzida(self) -> None:
        alerta = GovernanceAlert(
            source=FonteAlerta.FEATURE_DOWN,
            severity=SeveridadeAlerta.CRITICAL,
            evidence=[Evidence(origem="feature-monitor:syn-health", evidencias=["timeout"])],
        )
        entradas = alertas_para_inbox([alerta])

        assert entradas[0].severidade == Criticidade.CRITICAL

    def test_chave_dominio_usa_source_e_evidencia(self) -> None:
        alerta = GovernanceAlert(
            source=FonteAlerta.FEATURE_DOWN,
            severity=SeveridadeAlerta.WARNING,
            evidence=[Evidence(origem="feature-monitor:syn-health", evidencias=["500"])],
        )
        entradas = alertas_para_inbox([alerta])

        assert entradas[0].chave_dominio == "feature-down|feature-monitor:syn-health"

    def test_sem_evidencia_nao_levanta_e_usa_placeholder(self) -> None:
        alerta = GovernanceAlert(
            source=FonteAlerta.MANIFEST_DRIFT, severity=SeveridadeAlerta.WARNING, evidence=[]
        )
        entradas = alertas_para_inbox([alerta])

        assert "sem-evidencia" in entradas[0].chave_dominio

    def test_detalhe_junta_todas_as_evidencias(self) -> None:
        alerta = GovernanceAlert(
            source=FonteAlerta.FEATURE_DOWN,
            severity=SeveridadeAlerta.CRITICAL,
            evidence=[Evidence(origem="x", evidencias=["linha1", "linha2"])],
        )
        entradas = alertas_para_inbox([alerta])

        assert "linha1" in entradas[0].detalhe
        assert "linha2" in entradas[0].detalhe


class TestInboxIntegracaoMonitor:
    """Integracao `batman monitor` -> inbox — ponto 4 do pacote. `--db`
    novo (nao existia antes desta capacidade): ausente = comportamento
    identico ao anterior (sem persistencia)."""

    def test_sem_db_nao_grava_no_inbox(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        # feature desabilitada => run_once nao sonda nada (zero rede), mesmo
        # padrao de TestWiringCli.test_main_monitor_roda_ciclo_sem_rede acima
        # -- `main(["monitor", ...])` nao aceita sondador fake injetado.
        arq = _escrever_manifesto(
            tmp_path,
            [
                {
                    "id": "syn-health",
                    "descricao": "saude",
                    "caminho": "/api/health",
                    "severidade_se_cair": "critical",
                    "timeout_s": 5,
                    "habilitado": False,
                }
            ],
        )

        codigo = main(["monitor", "--tenant", "acme", "--manifest", str(arq)])
        assert codigo == 0
        assert "inbox:" not in capsys.readouterr().out

    def test_com_db_grava_alerta_no_inbox(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        arq = _escrever_manifesto(
            tmp_path,
            [
                {
                    "id": "syn-health",
                    "descricao": "saude",
                    "caminho": "/api/health",
                    "severidade_se_cair": "critical",
                    "timeout_s": 5,
                    "habilitado": False,
                }
            ],
        )
        db_path = tmp_path / "estado.db"

        codigo = main(["monitor", "--tenant", "acme", "--manifest", str(arq), "--db", str(db_path)])

        assert codigo == 0
        # feature desabilitada => 0 alertas, mas o wiring do inbox ainda roda
        # (ingest com lista vazia) — sem erro, "0 novo(s)".
        assert "inbox:" in capsys.readouterr().out
        with InboxStore(str(db_path)) as store:
            assert store.listar() == []

    def test_alerta_real_de_feature_caida_vira_achado_no_inbox(self, tmp_path: Path) -> None:
        arq = _escrever_manifesto(
            tmp_path,
            [
                {
                    "id": "syn-health",
                    "descricao": "saude",
                    "caminho": "/api/health",
                    "severidade_se_cair": "critical",
                    "timeout_s": 5,
                }
            ],
        )
        manifest, alertas = executar_monitor(
            arq,
            sondador=_SondaFake(
                {"/api/health": RespostaSonda(status=None, down=True, erro="timeout")}
            ),
            governance=GovernanceEngine(),
        )
        assert len(alertas) == 1  # sanity check do fixture

        db_path = tmp_path / "estado.db"
        with InboxStore(str(db_path)) as store:
            resumo = store.ingest(
                alertas_para_inbox(alertas), origem=OrigemAchado.MONITOR, tenant_id=TenantId("acme")
            )
            assert resumo.novos == 1
            achados = store.listar()
        assert len(achados) == 1
        assert achados[0].origem == OrigemAchado.MONITOR
        assert achados[0].severidade == Criticidade.CRITICAL
