"""Monta o dataset v3 do LLM local do Batman OS.

v3 ataca o unico blocker que resta: o modelo nao sabe DEFERIR (escalar-humano
0%, e o logprob provou que nenhuma confianca serve de gate). Estrategia:
ensinar o defer como PREDICAO DE CLASSE, com exemplos UNICOS.

Fontes:
- A: dados operacionais reais do Batman legado (gerar_fonte_a) — 408.
- B: os 216 achados do batman-os rotulados por Opus, RECUPERADOS de
  `fonte_b_recuperada.jsonl` (57 suprimir-fp + 23 escalar-humano preservados).
- C: SINTETICO — outcomes reais do radar com o contexto decisivo REMOVIDO
  (so codigo+severidade+titulo) => genuinamente indecidivel => escalar-humano.
  Ensina "contexto fino -> defira" com dezenas de inputs unicos (o oversample
  de 20 na v2 nao ensinou).

Split: sinteticos (C) so no train; holdout mede achados REAIS (A+B).
Rebalanceia o train.
"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_dataset import (  # noqa: E402
    OUT_DIR_DEFAULT,
    RADAR_ROOT_DEFAULT,
    SEED,
    _carregar_json,
    _exemplo,
    _gravar_jsonl,
    _ponto,
    dividir,
    gerar_fonte_a,
    rebalancear_train,
)


def gerar_fonte_c_dos_outcomes(radar_root: Path, alvo: int = 75) -> list[dict[str, Any]]:
    """Fonte C — strip de outcomes reais do radar para escalar-humano."""
    outcomes_dir = radar_root / "Batman" / "config" / "outcomes"
    arquivos = sorted(outcomes_dir.glob("*.json"))
    rng = random.Random(SEED + 2)
    rng.shuffle(arquivos)
    confs = [0.60, 0.64, 0.68, 0.72, 0.74]
    vistos: set[tuple[str, str]] = set()
    exemplos: list[dict[str, Any]] = []
    for arq in arquivos:
        o = _carregar_json(arq)
        chave = (o.get("codigo", "?"), o.get("titulo", "")[:40])
        if chave in vistos:
            continue
        vistos.add(chave)
        ctx = {  # contexto decisivo removido de proposito
            "codigo": o.get("codigo", "?"),
            "severidade": o.get("severidade", "?"),
            "titulo": o.get("titulo", ""),
        }
        exemplos.append(
            _exemplo(
                _ponto(ctx),
                "escalar-humano",
                confs[len(exemplos) % len(confs)],
                "Contexto insuficiente: so codigo, severidade e titulo — sem causa, "
                "arquivo ou descricao que permita decidir. Escalar para humano.",
                fonte="sintetico-lowctx",
                repo="sintetico",
            )
        )
        if len(exemplos) >= alvo:
            break
    return exemplos


def main() -> int:
    out_dir = OUT_DIR_DEFAULT
    exemplos: list[dict[str, Any]] = []

    fonte_a = gerar_fonte_a(RADAR_ROOT_DEFAULT)
    print(f"[A] {len(fonte_a)} operacional real")
    exemplos.extend(fonte_a)

    fb_path = out_dir / "fonte_b_recuperada.jsonl"
    fonte_b = [
        json.loads(linha)
        for linha in fb_path.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]
    dist_b = dict(Counter(e["meta"]["opcao_gold"] for e in fonte_b))
    print(f"[B] {len(fonte_b)} rotulados Opus (recuperados) {dist_b}")
    exemplos.extend(fonte_b)

    fonte_c = gerar_fonte_c_dos_outcomes(RADAR_ROOT_DEFAULT, 75)
    print(f"[C] {len(fonte_c)} sinteticos low-context -> escalar-humano")
    exemplos.extend(fonte_c)

    train, holdout = dividir(exemplos)
    antes = Counter(e["meta"]["opcao_gold"] for e in train)
    train = rebalancear_train(train, cap_majoritaria=130, piso_minoritaria=95)
    depois = Counter(e["meta"]["opcao_gold"] for e in train)
    print(f"[balancear] antes={dict(antes)} depois={dict(depois)}")

    _gravar_jsonl(out_dir / "train.jsonl", train)
    _gravar_jsonl(out_dir / "holdout.jsonl", holdout)
    stats = {
        "total": len(exemplos),
        "train": len(train),
        "holdout": len(holdout),
        "holdout_por_opcao": dict(Counter(e["meta"]["opcao_gold"] for e in holdout)),
        "train_por_opcao": dict(depois),
    }
    (out_dir / "dataset_stats_v3.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
