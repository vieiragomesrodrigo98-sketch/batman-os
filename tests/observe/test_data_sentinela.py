"""Testes de `observe/data_sentinela.py` — sentinela de saúde de dados em
produção (capability `dados-sentinela`, Onda 1 do Plano Cobertura Total,
S162).

`TestIncidentePipeFsimMtm01` é a "prova de fogo" pedida no pacote: o
incidente REAL do radar-preditivo (pipeline de 2026-07-29 21:32 UTC
terminou `status=error` no passo `fsim_mark_to_market`, monitor antigo deu
0 alertas) tem que virar achado ao ser reproduzido em replay."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from batman_os.foundation.types import TenantId
from batman_os.governance.governance_engine import (
    FonteAlerta,
    GovernanceEngine,
    SeveridadeAlerta,
)
from batman_os.observe import data_sentinela as data_sentinela_mod
from batman_os.observe.data_manifest import (
    DataSentinelManifest,
    FonteIdadeArquivo,
    FonteJsonlPipeline,
)
from batman_os.observe.data_sentinela import DataSentinelMonitor


def _manifest(root: Path, **overrides: object) -> DataSentinelManifest:
    base: dict[str, object] = {
        "tenant_id": "acme",
        "root_dir": str(root),
        "revisado_em": "2026-07-30",
        "fontes_jsonl": [],
        "fontes_idade": [],
    }
    base.update(overrides)
    return DataSentinelManifest.model_validate(base)


def _escrever_jsonl(caminho: Path, linhas: list[dict[str, object]]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text("\n".join(json.dumps(linha) for linha in linhas) + "\n", encoding="utf-8")


def _congelar_agora(monkeypatch: pytest.MonkeyPatch, momento: datetime) -> None:
    """Fixa `agora()` (usado internamente por `DataSentinelMonitor.run_once`)
    num instante determinístico — necessário para os testes de queda de
    contagem/dia útil, que dependem de "agora" vs os timestamps das linhas."""
    monkeypatch.setattr(data_sentinela_mod, "agora", lambda: momento)


class TestIncidentePipeFsimMtm01:
    """Replay do incidente real do radar-preditivo — a linha exata que o
    `update_log.jsonl` de produção gravou em 2026-07-29 21:32 UTC."""

    _LINHA_INCIDENTE = {
        "run_at": "2026-07-29T21:32:07.123456+00:00",
        "status": "error",
        "errors": ["step fsim_mark_to_market falhou"],
        "n_rows_added": 0,
        "pipeline_full": True,
        "elapsed_s": 812.4,
        "events_updated": True,
        "steps": {
            "history": "ok",
            "ingestion": "ok",
            "regime": "ok",
            "signals": "ok",
            "monitor": "ok",
            "autopilot": "ok",
            "sim_to_outcome": "ok",
            "fsim_autopilot_close": "ok",
            "fsim_autopilot_open": "ok",
            "fsim_fill": "ok",
            "fsim_expire": "ok",
            "fsim_mark_to_market": "error",
            "calibragem": "ok",
            "autocalibragem_pesos": "ok",
            "newsletter": "ok",
            "alertas_email": "ok",
        },
    }

    def _montar_manifest(self, tmp_path: Path) -> DataSentinelManifest:
        _escrever_jsonl(tmp_path / "data" / "update_log.jsonl", [self._LINHA_INCIDENTE])
        return _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {"id": "pipeline-diario", "descricao": "d", "arquivo": "data/update_log.jsonl"}
                )
            ],
        )

    def test_pipeline_error_vira_achado_critical(self, tmp_path: Path) -> None:
        manifest = self._montar_manifest(tmp_path)
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)

        assert len(alertas) >= 1
        erro = next(a for a in alertas if a.source == FonteAlerta.DATA_PIPELINE_ERROR)
        assert erro.severity == SeveridadeAlerta.CRITICAL

    def test_passo_com_erro_aparece_na_evidencia(self, tmp_path: Path) -> None:
        manifest = self._montar_manifest(tmp_path)
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)

        erro = next(a for a in alertas if a.source == FonteAlerta.DATA_PIPELINE_ERROR)
        evidencias = [e for ev in erro.evidence for e in ev.evidencias]
        assert any("fsim_mark_to_market" in linha for linha in evidencias)


class TestProvaDeFogoStatusOkNaoAlerta:
    def test_todas_as_linhas_ok_nao_produz_achado_de_pipeline_error(self, tmp_path: Path) -> None:
        linhas: list[dict[str, object]] = [
            {"run_at": "2026-07-30T21:32:00+00:00", "status": "ok", "steps": {"a": "ok"}},
            {"run_at": "2026-07-30T21:33:00+00:00", "status": "ok"},
        ]
        _escrever_jsonl(tmp_path / "data" / "update_log.jsonl", linhas)
        manifest = _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {"id": "pipeline-diario", "descricao": "d", "arquivo": "data/update_log.jsonl"}
                )
            ],
        )
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert not any(a.source == FonteAlerta.DATA_PIPELINE_ERROR for a in alertas)


class TestProvaDeFogoArquivoAusenteVsFonteDesativada:
    def test_fonte_habilitada_com_arquivo_ausente_e_achado_critical(self, tmp_path: Path) -> None:
        manifest = _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {
                        "id": "pipeline-diario",
                        "descricao": "d",
                        "arquivo": "data/nao-existe.jsonl",
                        "habilitado": True,
                    }
                )
            ],
        )
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.DATA_SOURCE_MISSING
        assert alertas[0].severity == SeveridadeAlerta.CRITICAL

    def test_fonte_desativada_com_arquivo_ausente_nao_gera_nenhum_achado(
        self, tmp_path: Path
    ) -> None:
        manifest = _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {
                        "id": "pipeline-diario",
                        "descricao": "d",
                        "arquivo": "data/nao-existe.jsonl",
                        "habilitado": False,
                    }
                )
            ],
        )
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert alertas == []

    def test_fonte_de_idade_habilitada_com_arquivo_ausente_e_critical(self, tmp_path: Path) -> None:
        manifest = _manifest(
            tmp_path,
            fontes_idade=[
                FonteIdadeArquivo.model_validate(
                    {
                        "id": "precos",
                        "descricao": "d",
                        "arquivo": "data/nao-existe.parquet",
                        "cadencia_max_minutos": 60,
                        "habilitado": True,
                    }
                )
            ],
        )
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.DATA_SOURCE_MISSING

    def test_fonte_de_idade_desativada_com_arquivo_ausente_nao_alerta(self, tmp_path: Path) -> None:
        manifest = _manifest(
            tmp_path,
            fontes_idade=[
                FonteIdadeArquivo.model_validate(
                    {
                        "id": "precos",
                        "descricao": "d",
                        "arquivo": "data/nao-existe.parquet",
                        "cadencia_max_minutos": 60,
                        "habilitado": False,
                    }
                )
            ],
        )
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert alertas == []


class TestIdadeDeArquivo:
    def test_arquivo_fresco_nao_alerta(self, tmp_path: Path) -> None:
        arq = tmp_path / "data" / "prices_20y.parquet"
        arq.parent.mkdir(parents=True)
        arq.write_bytes(b"x")
        manifest = _manifest(
            tmp_path,
            fontes_idade=[
                FonteIdadeArquivo.model_validate(
                    {
                        "id": "precos",
                        "descricao": "d",
                        "arquivo": "data/prices_20y.parquet",
                        "cadencia_max_minutos": 60,
                    }
                )
            ],
        )
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert alertas == []

    def test_arquivo_velho_alerta_stale(self, tmp_path: Path) -> None:
        import os

        arq = tmp_path / "data" / "prices_20y.parquet"
        arq.parent.mkdir(parents=True)
        arq.write_bytes(b"x")
        antigo = (datetime.now(UTC) - timedelta(hours=5)).timestamp()
        os.utime(arq, (antigo, antigo))

        manifest = _manifest(
            tmp_path,
            fontes_idade=[
                FonteIdadeArquivo.model_validate(
                    {
                        "id": "precos",
                        "descricao": "d",
                        "arquivo": "data/prices_20y.parquet",
                        "cadencia_max_minutos": 60,
                    }
                )
            ],
        )
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.DATA_SOURCE_STALE

    def test_fim_de_semana_com_dias_uteis_apenas_nao_alerta_mesmo_velho(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        arq = tmp_path / "data" / "prices_20y.parquet"
        arq.parent.mkdir(parents=True)
        arq.write_bytes(b"x")
        sexta_passada = datetime(2026, 7, 24, 21, 30, tzinfo=UTC)  # sexta-feira
        os.utime(arq, (sexta_passada.timestamp(), sexta_passada.timestamp()))

        manifest = _manifest(
            tmp_path,
            fontes_idade=[
                FonteIdadeArquivo.model_validate(
                    {
                        "id": "precos",
                        "descricao": "d",
                        "arquivo": "data/prices_20y.parquet",
                        "cadencia_max_minutos": 1440,
                        "dias_uteis_apenas": True,
                    }
                )
            ],
        )
        domingo = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
        assert domingo.weekday() == 6
        _congelar_agora(monkeypatch, domingo)

        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert alertas == []

    def test_segunda_com_dias_uteis_apenas_volta_a_checar(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A checagem NÃO fica desligada para sempre — só pula fim de
        semana; num dia útil com o arquivo genuinamente velho, alerta."""
        import os

        arq = tmp_path / "data" / "prices_20y.parquet"
        arq.parent.mkdir(parents=True)
        arq.write_bytes(b"x")
        antigo = datetime(2026, 7, 20, 21, 30, tzinfo=UTC)  # segunda anterior
        os.utime(arq, (antigo.timestamp(), antigo.timestamp()))

        manifest = _manifest(
            tmp_path,
            fontes_idade=[
                FonteIdadeArquivo.model_validate(
                    {
                        "id": "precos",
                        "descricao": "d",
                        "arquivo": "data/prices_20y.parquet",
                        "cadencia_max_minutos": 1440,
                        "dias_uteis_apenas": True,
                    }
                )
            ],
        )
        segunda = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
        assert segunda.weekday() == 0
        _congelar_agora(monkeypatch, segunda)

        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert len(alertas) == 1
        assert alertas[0].source == FonteAlerta.DATA_SOURCE_STALE


class TestQuedaDeContagemDeLinhas:
    def _linhas_espacadas(
        self, inicio: datetime, quantidade: int, espaco_minutos: int = 5
    ) -> list[dict[str, object]]:
        return [
            {
                "run_at": (inicio + timedelta(minutes=i * espaco_minutos)).isoformat(),
                "status": "ok",
            }
            for i in range(quantidade)
        ]

    def test_queda_acima_do_limiar_alerta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agora_ = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)  # quinta-feira
        anteriores = self._linhas_espacadas(agora_ - timedelta(hours=47), 40)
        recentes = self._linhas_espacadas(agora_ - timedelta(hours=23), 5)  # queda forte
        _escrever_jsonl(tmp_path / "data" / "update_log.jsonl", anteriores + recentes)

        manifest = _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {
                        "id": "pipeline-diario",
                        "descricao": "d",
                        "arquivo": "data/update_log.jsonl",
                        "minimo_linhas_para_checar_queda": 5,
                    }
                )
            ],
        )
        _congelar_agora(monkeypatch, agora_)
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert any(a.source == FonteAlerta.DATA_ROW_COUNT_DROP for a in alertas)

    def test_queda_abaixo_do_limiar_nao_alerta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agora_ = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
        anteriores = self._linhas_espacadas(agora_ - timedelta(hours=47), 40)
        recentes = self._linhas_espacadas(agora_ - timedelta(hours=23), 38)  # ~5% de queda
        _escrever_jsonl(tmp_path / "data" / "update_log.jsonl", anteriores + recentes)

        manifest = _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {
                        "id": "pipeline-diario",
                        "descricao": "d",
                        "arquivo": "data/update_log.jsonl",
                        "minimo_linhas_para_checar_queda": 5,
                    }
                )
            ],
        )
        _congelar_agora(monkeypatch, agora_)
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert not any(a.source == FonteAlerta.DATA_ROW_COUNT_DROP for a in alertas)

    def test_baseline_pequena_demais_nao_dispara_queda(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agora_ = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
        anteriores = self._linhas_espacadas(agora_ - timedelta(hours=47), 2)  # baixo volume normal
        _escrever_jsonl(tmp_path / "data" / "update_log.jsonl", anteriores)

        manifest = _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {
                        "id": "pipeline-diario",
                        "descricao": "d",
                        "arquivo": "data/update_log.jsonl",
                        "minimo_linhas_para_checar_queda": 5,
                    }
                )
            ],
        )
        _congelar_agora(monkeypatch, agora_)
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert not any(a.source == FonteAlerta.DATA_ROW_COUNT_DROP for a in alertas)

    def test_fim_de_semana_com_flag_pula_checagem_de_queda(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _escrever_jsonl(tmp_path / "data" / "update_log.jsonl", [])  # sem nenhuma linha
        manifest = _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {
                        "id": "pipeline-diario",
                        "descricao": "d",
                        "arquivo": "data/update_log.jsonl",
                        "dias_uteis_apenas_para_queda": True,
                    }
                )
            ],
        )
        domingo = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
        _congelar_agora(monkeypatch, domingo)
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert not any(a.source == FonteAlerta.DATA_ROW_COUNT_DROP for a in alertas)


class TestBestEffort:
    def test_conteudo_nao_json_nao_quebra_o_ciclo(self, tmp_path: Path) -> None:
        arq = tmp_path / "data" / "update_log.jsonl"
        arq.parent.mkdir(parents=True)
        arq.write_text("isto nao e json\nnem isto\n", encoding="utf-8")
        manifest = _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {"id": "pipeline-diario", "descricao": "d", "arquivo": "data/update_log.jsonl"}
                )
            ],
        )
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert alertas == []  # nao quebra, so nao encontra nada de util

    def test_linha_sem_campo_status_nao_conta_como_erro(self, tmp_path: Path) -> None:
        _escrever_jsonl(
            tmp_path / "data" / "update_log.jsonl",
            [{"run_at": "2026-07-30T10:00:00+00:00", "n_rows_added": 5}],
        )
        manifest = _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {"id": "pipeline-diario", "descricao": "d", "arquivo": "data/update_log.jsonl"}
                )
            ],
        )
        alertas = DataSentinelMonitor(GovernanceEngine()).run_once(manifest)
        assert not any(a.source == FonteAlerta.DATA_PIPELINE_ERROR for a in alertas)


class TestAlertasSaoEntreguesAoGovernanceEngine:
    def test_run_once_registra_no_governance_engine(self, tmp_path: Path) -> None:
        _escrever_jsonl(
            tmp_path / "data" / "update_log.jsonl",
            [{"run_at": "2026-07-30T10:00:00+00:00", "status": "error"}],
        )
        manifest = _manifest(
            tmp_path,
            fontes_jsonl=[
                FonteJsonlPipeline.model_validate(
                    {"id": "pipeline-diario", "descricao": "d", "arquivo": "data/update_log.jsonl"}
                )
            ],
        )
        governance = GovernanceEngine()
        DataSentinelMonitor(governance).run_once(manifest)
        abertos = governance.get_open_alerts(source=FonteAlerta.DATA_PIPELINE_ERROR)
        assert len(abertos) == 1
        assert abertos[0].related_tenant_id == TenantId("acme")
