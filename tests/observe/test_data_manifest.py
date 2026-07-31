"""Testes de `observe/data_manifest.py` — manifesto declarativo de fontes de
dados da capability `dados-sentinela` (Onda 1, Plano Cobertura Total, S162)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from batman_os.observe.data_manifest import (
    DataSentinelManifest,
    FonteIdadeArquivo,
    FonteJsonlPipeline,
    caminho_manifesto_dados,
    carregar_manifesto_dados,
)


def _manifesto_minimo(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "tenant_id": "acme",
        "root_dir": "/opt/exemplo/prod",
        "revisado_em": "2026-07-30",
        "fontes_jsonl": [],
        "fontes_idade": [],
    }
    base.update(overrides)
    return base


class TestFonteJsonlPipelineDefaults:
    def test_defaults_seguros(self) -> None:
        fonte = FonteJsonlPipeline.model_validate(
            {"id": "x", "descricao": "d", "arquivo": "data/update_log.jsonl"}
        )
        assert fonte.campo_status == "status"
        assert fonte.valor_ok == "ok"
        assert fonte.campo_timestamp == "run_at"
        assert fonte.linhas_recentes_para_status == 50
        assert fonte.queda_percentual_max == 20.0
        assert fonte.habilitado is True
        assert fonte.dias_uteis_apenas_para_queda is False


class TestFonteIdadeArquivoDefaults:
    def test_exige_cadencia_max_minutos(self) -> None:
        with pytest.raises(ValidationError):
            FonteIdadeArquivo.model_validate({"id": "x", "descricao": "d", "arquivo": "a.parquet"})

    def test_defaults_seguros(self) -> None:
        fonte = FonteIdadeArquivo.model_validate(
            {"id": "x", "descricao": "d", "arquivo": "a.parquet", "cadencia_max_minutos": 60}
        )
        assert fonte.severidade.value == "warning"
        assert fonte.habilitado is True
        assert fonte.dias_uteis_apenas is False


class TestCarregarManifestoDados:
    def test_carrega_manifesto_completo(self, tmp_path: Path) -> None:
        arq = tmp_path / "acme_dados.json"
        arq.write_text(
            json.dumps(
                _manifesto_minimo(
                    fontes_jsonl=[
                        {
                            "id": "pipeline",
                            "descricao": "d",
                            "arquivo": "data/update_log.jsonl",
                        }
                    ],
                    fontes_idade=[
                        {
                            "id": "precos",
                            "descricao": "d",
                            "arquivo": "data/prices_20y.parquet",
                            "cadencia_max_minutos": 1440,
                        }
                    ],
                )
            ),
            encoding="utf-8",
        )
        manifest = carregar_manifesto_dados(arq)
        assert manifest.tenant_id == "acme"
        assert len(manifest.fontes_jsonl) == 1
        assert len(manifest.fontes_idade) == 1

    def test_chaves_extra_sao_ignoradas(self, tmp_path: Path) -> None:
        arq = tmp_path / "acme_dados.json"
        arq.write_text(
            json.dumps({**_manifesto_minimo(), "_nota": "comentario livre"}), encoding="utf-8"
        )
        manifest = carregar_manifesto_dados(arq)
        assert manifest.tenant_id == "acme"

    def test_chave_extra_dentro_de_fonte_e_ignorada(self, tmp_path: Path) -> None:
        """`_cadencia` (documentação da cadência do crontab.prod) dentro de
        cada fonte no manifesto real do exemplo não pode quebrar a
        validação."""
        arq = tmp_path / "acme_dados.json"
        arq.write_text(
            json.dumps(
                _manifesto_minimo(
                    fontes_jsonl=[
                        {
                            "id": "pipeline",
                            "descricao": "d",
                            "arquivo": "data/update_log.jsonl",
                            "_cadencia": "explicação livre citando o crontab",
                        }
                    ]
                )
            ),
            encoding="utf-8",
        )
        manifest = carregar_manifesto_dados(arq)
        assert manifest.fontes_jsonl[0].id == "pipeline"


class TestCaminhoManifestoDados:
    def test_usa_sufixo_dados_para_nao_colidir_com_o_manifesto_http(self) -> None:
        caminho = caminho_manifesto_dados("exemplo")
        assert caminho.name == "exemplo_dados.json"


class TestManifestoRealExemplo:
    """O manifesto commitado (`observe/manifests/exemplo_dados.json`)
    tem que carregar de verdade — sanity check contra regressão de schema."""

    def test_carrega_o_manifesto_real(self) -> None:
        manifest = carregar_manifesto_dados(caminho_manifesto_dados("exemplo"))
        assert manifest.tenant_id == "exemplo"
        assert manifest.root_dir
        assert len(manifest.fontes_jsonl) >= 1
        assert len(manifest.fontes_idade) >= 1

    def test_fonte_pipeline_diario_aponta_para_update_log(self) -> None:
        manifest = carregar_manifesto_dados(caminho_manifesto_dados("exemplo"))
        fonte = next(f for f in manifest.fontes_jsonl if f.id == "pipeline-diario")
        assert fonte.arquivo == "data/update_log.jsonl"


class TestDataSentinelManifestModel:
    def test_model_validate_direto(self) -> None:
        manifest = DataSentinelManifest.model_validate(_manifesto_minimo())
        assert manifest.fontes_jsonl == []
        assert manifest.fontes_idade == []
