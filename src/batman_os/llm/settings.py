"""Configuração do LLM Gateway (Milestone 6 desta construção).

`Settings.carregar()` é o ÚNICO ponto que lê variável de ambiente para
estas 5 chaves — o restante do pacote `llm/` recebe uma instância de
`Settings` já construída, nunca `os.getenv()` espalhado (mesmo padrão de
`radar-preditivo/config/settings.py`, sem trazer a dependência extra de
`pydantic-settings` para um caso desse tamanho).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Vol.IX (Reference Implementation) — mínimo necessário para o LLM
    Gateway funcionar; não é a configuração inteira do batman-os."""

    anthropic_api_key: str = ""
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_max_tokens: int = Field(default=1024, gt=0)
    llm_timeout: float = Field(default=30.0, gt=0)
    max_daily_llm_cost_usd: float = Field(default=10.0, gt=0)

    @classmethod
    def carregar(
        cls, env: Mapping[str, str] | None = None, dotenv_path: str | Path | None = None
    ) -> Settings:
        """Lê de `.env`/variável de ambiente real quando `env` é omitido.
        Chave ausente usa o default da classe — só `ANTHROPIC_API_KEY`
        realmente precisa existir para uma chamada real funcionar; os
        demais defaults já são utilizáveis sem configuração adicional.

        Achado de revisão: `env` explícito (usado pelos testes) nunca
        toca o arquivo `.env` real — só quando `env` é omitido é que
        `load_dotenv()` carrega `.env` (se existir) em `os.environ` antes
        de ler (não sobrescreve variável já exportada no processo,
        comportamento padrão de `python-dotenv`). Sem isso, `.env` nunca
        era lido de verdade — só variável de ambiente já exportada
        manualmente no shell.

        `dotenv_path` (opcional, default `None`): repassado a
        `load_dotenv()`. Sem ele, `python-dotenv` localiza `.env` a partir
        do arquivo chamador via inspeção de stack, NÃO do diretório de
        trabalho atual — comportamento correto em produção (o `.env` é
        deste projeto, não do repositório que `batman scan` está
        analisando), mas que exige um caminho explícito para ser testável
        de forma determinística (ver testes)."""
        if env is None:
            load_dotenv(dotenv_path=dotenv_path)
        fonte = env if env is not None else os.environ
        kwargs: dict[str, str] = {}
        if "ANTHROPIC_API_KEY" in fonte:
            kwargs["anthropic_api_key"] = fonte["ANTHROPIC_API_KEY"]
        if "LLM_MODEL" in fonte:
            kwargs["llm_model"] = fonte["LLM_MODEL"]
        if "LLM_MAX_TOKENS" in fonte:
            kwargs["llm_max_tokens"] = fonte["LLM_MAX_TOKENS"]
        if "LLM_TIMEOUT" in fonte:
            kwargs["llm_timeout"] = fonte["LLM_TIMEOUT"]
        if "MAX_DAILY_LLM_COST_USD" in fonte:
            kwargs["max_daily_llm_cost_usd"] = fonte["MAX_DAILY_LLM_COST_USD"]
        return cls(**kwargs)
