"""Aplica rotulos de professor produzidos OFFLINE (ex.: sessao Claude
Code com Fable/Opus) ao cache do `prepare_dataset.py` — sem chamada de
API.

Entrada: um ou mais JSONL com linhas {"i": <indice 0-based no
pending_professor.jsonl>, "opcao": <id canonico>, "confidence": <0..1>,
"evidencia": <str>}. Cada rotulo valido vira um arquivo de cache
`professor_cache/<hash>.json` com o MESMO formato que a API produziria
(`RespostaLlmCandidata`), de modo que a proxima execucao de
`prepare_dataset.py --professor-max 0` consome tudo de graca.

Uso:
  python scripts/llm_local/rotular_offline.py labels1.jsonl labels2.jsonl \
      --modelo fable-5-sessao
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from prepare_dataset import (  # noqa: E402
    _OPCAO_POR_ID,
    OUT_DIR_DEFAULT,
    RespostaLlmCandidata,
    _hash_ponto,
    _truncar,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("labels", nargs="+", type=Path, help="JSONL(s) de rotulos offline")
    parser.add_argument("--pending", type=Path, default=OUT_DIR_DEFAULT / "pending_professor.jsonl")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR_DEFAULT)
    parser.add_argument(
        "--modelo", default="fable-5-sessao", help="rotulo do professor (entra no hash do cache)"
    )
    args = parser.parse_args()

    pendentes = [
        json.loads(linha)
        for linha in args.pending.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]
    cache_dir = args.out_dir / "professor_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    aplicados, rejeitados = 0, 0
    vistos: set[int] = set()
    for arquivo in args.labels:
        for numero, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            if not linha.strip():
                continue
            try:
                rotulo = json.loads(linha)
                indice = int(rotulo["i"])
                opcao = _OPCAO_POR_ID[rotulo["opcao"]]
                bruto = {
                    "opcao": {"id": opcao.id, "descricao": opcao.descricao},
                    "confidence": float(rotulo["confidence"]),
                    "evidencia_bruta": _truncar(str(rotulo["evidencia"])),
                }
                RespostaLlmCandidata.model_validate(bruto)
                ctx = pendentes[indice]["ctx"]
            except Exception as exc:
                print(f"[rejeitado] {arquivo.name}:{numero}: {exc}")
                rejeitados += 1
                continue
            if indice in vistos:
                print(f"[rejeitado] {arquivo.name}:{numero}: indice {indice} duplicado")
                rejeitados += 1
                continue
            vistos.add(indice)
            chave = _hash_ponto(ctx, args.modelo)
            (cache_dir / f"{chave}.json").write_text(
                json.dumps(bruto, ensure_ascii=False), encoding="utf-8"
            )
            aplicados += 1

    print(f"aplicados={aplicados} rejeitados={rejeitados} de {len(pendentes)} pendentes")
    print(f"proximo passo: prepare_dataset.py --professor-model {args.modelo} --professor-max 0")
    return 0 if rejeitados == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
