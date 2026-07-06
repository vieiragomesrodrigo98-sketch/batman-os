"""Testes de Settings do LLM Gateway (Milestone 6)."""

from __future__ import annotations

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


def test_carregar_sem_argumento_nao_levanta() -> None:
    # Le de os.environ de verdade - so garante que nao quebra sem
    # ANTHROPIC_API_KEY configurada (nenhum teste deste modulo depende
    # de uma chave real existir).
    Settings.carregar()
