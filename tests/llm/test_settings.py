"""Testes de Settings do LLM Gateway (Milestone 6)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from batman_os.llm.settings import Settings


def test_sem_env_usa_defaults() -> None:
    settings = Settings.carregar(env={})

    assert settings.anthropic_api_key == ""
    assert settings.llm_model == "claude-haiku-4-5-20251001"
    assert settings.llm_max_tokens == 1024
    assert settings.llm_timeout == 30.0
    assert settings.max_daily_llm_cost_usd == 10.0


def test_le_todas_as_chaves_do_env() -> None:
    settings = Settings.carregar(
        env={
            "ANTHROPIC_API_KEY": "sk-fake-123",
            "LLM_MODEL": "claude-opus-4-8",
            "LLM_MAX_TOKENS": "2048",
            "LLM_TIMEOUT": "45.5",
            "MAX_DAILY_LLM_COST_USD": "25.0",
        }
    )

    assert settings.anthropic_api_key == "sk-fake-123"
    assert settings.llm_model == "claude-opus-4-8"
    assert settings.llm_max_tokens == 2048
    assert settings.llm_timeout == 45.5
    assert settings.max_daily_llm_cost_usd == 25.0


def test_chave_parcial_usa_default_para_o_resto() -> None:
    settings = Settings.carregar(env={"ANTHROPIC_API_KEY": "sk-fake-456"})

    assert settings.anthropic_api_key == "sk-fake-456"
    assert settings.llm_model == "claude-haiku-4-5-20251001"


def test_carregar_sem_argumento_nao_levanta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # So garante que nao quebra sem ANTHROPIC_API_KEY configurada (nenhum
    # teste deste modulo depende de uma chave real existir). dotenv_path
    # aponta pra um diretorio vazio para nao carregar o .env real deste
    # projeto (que teria uma chave de verdade) e vazar ANTHROPIC_API_KEY
    # para os.environ pelo resto da sessao de pytest.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    Settings.carregar(dotenv_path=tmp_path / ".env")


class TestMilestone6CarregaArquivoEnvDeVerdade:
    """Achado de revisão: `Settings.carregar()` sem `env` explícito nunca
    lia o arquivo `.env` de verdade — só variável já exportada no processo.
    `load_dotenv()` fecha essa lacuna (só quando `env` é omitido — os
    testes acima com `env={...}` continuam 100% isolados do `.env` real).

    `dotenv_path` explícito nos testes: `load_dotenv()` sem argumento
    localiza `.env` por inspeção de stack do arquivo chamador, NÃO pelo
    diretório de trabalho atual — `monkeypatch.chdir()` sozinho não muda
    qual `.env` é encontrado (achado ao escrever este teste). `dotenv_path`
    explícito é a forma determinística de testar isso."""

    def test_le_valor_de_um_arquivo_env_explicito(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text(
            "ANTHROPIC_API_KEY=sk-do-arquivo-env\nLLM_MAX_TOKENS=777\n", encoding="utf-8"
        )
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)

        settings = Settings.carregar(dotenv_path=dotenv_path)

        assert settings.anthropic_api_key == "sk-do-arquivo-env"
        assert settings.llm_max_tokens == 777

        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("LLM_MAX_TOKENS", raising=False)

    def test_variavel_ja_exportada_no_processo_tem_prioridade_sobre_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text("ANTHROPIC_API_KEY=sk-do-arquivo-env\n", encoding="utf-8")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ja-exportada-no-processo")

        settings = Settings.carregar(dotenv_path=dotenv_path)

        assert settings.anthropic_api_key == "sk-ja-exportada-no-processo"

    def test_env_explicito_nunca_toca_o_arquivo_env_real(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dotenv_path = tmp_path / ".env"
        dotenv_path.write_text("ANTHROPIC_API_KEY=sk-do-arquivo-env\n", encoding="utf-8")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        settings = Settings.carregar(env={}, dotenv_path=dotenv_path)

        assert settings.anthropic_api_key == ""
        assert os.environ.get("ANTHROPIC_API_KEY") is None
