"""Circuit breaker de custo de LLM (Milestone 6 desta construção).

Design (versão simplificada do padrão já em produção em
`radar-preditivo/src/radar/llm/cost_tracker.py`, mesma assinatura de risco):
- Ledger JSONL append-only, uma linha por chamada — evita corrida de
  read-modify-write.
- `registrar()` é best-effort: qualquer falha de I/O é engolida (nunca
  derruba uma chamada de LLM só porque a contabilidade falhou).
- `orcamento_excedido()` é FAIL-CLOSED: ledger ausente = sem gasto ainda =
  libera (primeiro uso é normal); ledger presente mas ilegível = bloqueia.
  Essa assinatura de risco é inegociável — a parte simplificada aqui é só
  a quantidade de tentativas de releitura (1, não as 3 do original), não o
  fail-closed em si.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

from batman_os.llm.settings import Settings

_PRECOS_USD_POR_MILHAO: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {"input": 1.0, "output": 5.0, "cache_write": 1.25, "cache_read": 0.1},
    "claude-sonnet-5": {"input": 3.0, "output": 15.0, "cache_write": 3.75, "cache_read": 0.3},
    "claude-opus-4": {"input": 5.0, "output": 25.0, "cache_write": 6.25, "cache_read": 0.5},
    # Modelos locais (prefixo "local-", ex.: `local_gateway.MODELO_LOCAL`):
    # custo de API zero POR DESIGN. Sem esta entrada, `_preco_para` cairia
    # em `_PRECO_PADRAO` (preço de Haiku) e o teto diário seria consumido
    # por chamadas que não custam nada.
    "local-": {"input": 0.0, "output": 0.0, "cache_write": 0.0, "cache_read": 0.0},
}
_PRECO_PADRAO = _PRECOS_USD_POR_MILHAO["claude-haiku-4-5"]


def _preco_para(model: str) -> dict[str, float]:
    for prefixo, preco in _PRECOS_USD_POR_MILHAO.items():
        if model.startswith(prefixo):
            return preco
    return _PRECO_PADRAO


def estimar_custo(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """Custo estimado em USD para uma chamada, dado o breakdown de tokens."""
    p = _preco_para(model)
    return (
        input_tokens / 1_000_000 * p["input"]
        + output_tokens / 1_000_000 * p["output"]
        + cache_write_tokens / 1_000_000 * p["cache_write"]
        + cache_read_tokens / 1_000_000 * p["cache_read"]
    )


def _hoje() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


class CostTracker:
    """`ledger_path` injetado explicitamente (não um caminho global fixo
    via `os.getenv`) — torna o fail-closed trivialmente testável apontando
    para um arquivo temporário, sem monkeypatch de variável de ambiente."""

    def __init__(self, ledger_path: Path, settings: Settings) -> None:
        self._ledger_path = ledger_path
        self._settings = settings
        self._lock = threading.Lock()

    def registrar(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
    ) -> float:
        """Registra o custo de uma chamada no ledger. Best-effort: qualquer
        falha de I/O é engolida e retorna 0.0 (a contabilidade nunca é
        motivo para uma chamada de LLM já bem-sucedida falhar)."""
        custo = estimar_custo(
            model, input_tokens, output_tokens, cache_write_tokens, cache_read_tokens
        )
        try:
            entrada = {
                "ts": datetime.now(UTC).isoformat(),
                "date": _hoje(),
                "model": model,
                "in": input_tokens,
                "out": output_tokens,
                "cache_w": cache_write_tokens,
                "cache_r": cache_read_tokens,
                "cost": round(custo, 6),
            }
            with self._lock:
                self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
                with self._ledger_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(entrada) + "\n")
        except OSError:
            return 0.0
        return custo

    def _custo_do_dia_estrito(self) -> float:
        """LEVANTA em falha de leitura — base do breaker fail-closed.
        Ledger ausente = 0.0 (sem gasto ainda, primeiro uso é normal)."""
        if not self._ledger_path.exists():
            return 0.0
        hoje = _hoje()
        total = 0.0
        with self._lock, self._ledger_path.open(encoding="utf-8") as fh:
            for linha in fh:
                linha = linha.strip()
                if not linha:
                    continue
                entrada = json.loads(linha)
                if entrada.get("date") == hoje:
                    total += float(entrada.get("cost", 0.0) or 0.0)
        return total

    def orcamento_excedido(self) -> bool:
        """FAIL-CLOSED: ledger ilegível (JSON corrompido, erro de I/O) após
        1 releitura bloqueia (retorna `True`) — nunca libera gasto de LLM
        sem conseguir contabilizar. Ledger ausente libera normalmente."""
        for _tentativa in range(2):
            try:
                return self._custo_do_dia_estrito() >= self._settings.max_daily_llm_cost_usd
            except (OSError, json.JSONDecodeError):
                continue
        return True
