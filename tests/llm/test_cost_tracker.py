"""Testes do circuit breaker de custo de LLM (Milestone 6) — fail-closed
é a garantia central: ledger ausente libera, ledger ilegível bloqueia."""

from __future__ import annotations

from pathlib import Path

from batman_os.llm.cost_tracker import CostTracker, estimar_custo
from batman_os.llm.settings import Settings


def _tracker(tmp_path: Path, max_daily_llm_cost_usd: float = 10.0) -> CostTracker:
    settings = Settings(max_daily_llm_cost_usd=max_daily_llm_cost_usd)
    return CostTracker(ledger_path=tmp_path / "llm_cost.jsonl", settings=settings)


class TestEstimarCusto:
    def test_custo_zero_para_zero_tokens(self) -> None:
        assert estimar_custo("claude-haiku-4-5-20251001", 0, 0) == 0.0

    def test_custo_cresce_com_tokens(self) -> None:
        custo = estimar_custo("claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
        assert custo == 1.0 + 5.0  # input=1.00, output=5.00 por 1M tokens

    def test_modelo_desconhecido_usa_preco_padrao_haiku(self) -> None:
        custo_conhecido = estimar_custo("claude-haiku-4-5-20251001", 1_000_000, 0)
        custo_desconhecido = estimar_custo("modelo-que-nao-existe", 1_000_000, 0)
        assert custo_conhecido == custo_desconhecido


class TestFailClosed:
    def test_ledger_ausente_libera(self, tmp_path: Path) -> None:
        tracker = _tracker(tmp_path)
        assert tracker.orcamento_excedido() is False

    def test_ledger_com_gasto_abaixo_do_teto_libera(self, tmp_path: Path) -> None:
        tracker = _tracker(tmp_path, max_daily_llm_cost_usd=10.0)
        tracker.registrar(model="claude-haiku-4-5-20251001", input_tokens=1000, output_tokens=500)

        assert tracker.orcamento_excedido() is False

    def test_ledger_com_gasto_acima_do_teto_bloqueia(self, tmp_path: Path) -> None:
        tracker = _tracker(tmp_path, max_daily_llm_cost_usd=0.000001)
        tracker.registrar(
            model="claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=1_000_000
        )

        assert tracker.orcamento_excedido() is True

    def test_ledger_ilegivel_bloqueia_fail_closed(self, tmp_path: Path) -> None:
        ledger_path = tmp_path / "llm_cost.jsonl"
        ledger_path.write_text("isso nao e JSON valido{{{\n", encoding="utf-8")
        tracker = CostTracker(ledger_path=ledger_path, settings=Settings())

        assert tracker.orcamento_excedido() is True

    def test_registrar_e_best_effort_nunca_levanta(self, tmp_path: Path) -> None:
        # Aponta para um caminho onde o diretorio pai nao pode ser criado
        # (arquivo no lugar de diretorio) - simula falha de I/O.
        arquivo_no_lugar_de_dir = tmp_path / "nao-e-um-dir"
        arquivo_no_lugar_de_dir.write_text("x", encoding="utf-8")
        tracker = CostTracker(
            ledger_path=arquivo_no_lugar_de_dir / "sub" / "llm_cost.jsonl", settings=Settings()
        )

        custo = tracker.registrar(
            model="claude-haiku-4-5-20251001", input_tokens=100, output_tokens=50
        )

        assert custo == 0.0


class TestRegistroEContabilidade:
    def test_registrar_retorna_o_custo_estimado(self, tmp_path: Path) -> None:
        tracker = _tracker(tmp_path)
        custo = tracker.registrar(
            model="claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=0
        )

        assert custo == 1.0

    def test_multiplos_registros_acumulam_no_mesmo_dia(self, tmp_path: Path) -> None:
        tracker = _tracker(tmp_path, max_daily_llm_cost_usd=1.5)
        tracker.registrar(
            model="claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=0
        )
        tracker.registrar(
            model="claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=0
        )

        assert tracker.orcamento_excedido() is True  # 2 x $1.00 = $2.00 > $1.50
