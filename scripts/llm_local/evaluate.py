"""F3 — avalia o GGUF do LLM local contra o holdout, com a MESMA
gramatica/prompt do `LocalLlmGateway`.

Script AUTOCONTIDO (json/time/llama_cpp apenas, sem importar batman_os):
roda dentro do venv de WSL que tiver llama-cpp-python, onde o pacote
batman-os nao esta instalado. O acoplamento com o gateway e garantido
pelos DADOS: o holdout ja contem o system/user literais do gateway, e o
schema vem de `schema_eval.json` (gerado no Windows por
`schema_resposta_para_ponto` — mesma funcao usada em producao).

Uso (WSL):
    python evaluate.py --gguf <modelo.gguf> --holdout <holdout.jsonl> \
        --schema <schema_eval.json> --out <relatorio.json>

Metricas: acuracia de opcao vs gold (geral, por classe, por repo/fonte),
taxa de JSON valido, calibracao por estrato de confianca (o estrato
>= --min-confidence e o que decide sem fallback em producao) e latencia.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path


def carregar_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(linha)
        for linha in path.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]


def percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = min(len(ordenados) - 1, max(0, round(p / 100 * (len(ordenados) - 1))))
    return ordenados[indice]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gguf", required=True, type=Path)
    parser.add_argument("--holdout", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path("eval_report.json"))
    parser.add_argument("--min-confidence", type=float, default=0.75)
    parser.add_argument("--n-threads", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--limit", type=int, default=0, help="0 = holdout inteiro")
    args = parser.parse_args()

    from llama_cpp import Llama, LlamaGrammar

    schema_texto = args.schema.read_text(encoding="utf-8")
    gramatica = LlamaGrammar.from_json_schema(schema_texto)
    llm = Llama(
        model_path=str(args.gguf),
        n_ctx=2048,
        n_threads=args.n_threads,
        n_gpu_layers=0,
        verbose=False,
    )

    exemplos = carregar_jsonl(args.holdout)
    if args.limit:
        exemplos = exemplos[: args.limit]

    acertos = 0
    json_validos = 0
    latencias: list[float] = []
    confusao: Counter[tuple[str, str]] = Counter()
    por_classe: dict[str, Counter] = defaultdict(Counter)
    por_grupo: dict[str, Counter] = defaultdict(Counter)
    estrato_confiante = Counter()
    itens: list[dict] = []

    for numero, exemplo in enumerate(exemplos, 1):
        system, usuario = exemplo["messages"][0]["content"], exemplo["messages"][1]["content"]
        gold = json.loads(exemplo["messages"][2]["content"])
        gold_opcao = gold["opcao"]["id"]
        meta = exemplo.get("meta", {})

        inicio = time.perf_counter()
        completion = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": usuario},
            ],
            temperature=0.0,
            max_tokens=args.max_tokens,
            grammar=gramatica,
        )
        latencia = time.perf_counter() - inicio
        latencias.append(latencia)
        texto = completion["choices"][0]["message"]["content"] or ""

        pred_opcao, pred_conf = None, None
        try:
            pred = json.loads(texto)
            pred_opcao = pred.get("opcao", {}).get("id")
            pred_conf = float(pred.get("confidence", 0.0))
            json_validos += 1
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        acertou = pred_opcao == gold_opcao
        acertos += int(acertou)
        confusao[(gold_opcao, str(pred_opcao))] += 1
        por_classe[gold_opcao]["total"] += 1
        por_classe[gold_opcao]["acertos"] += int(acertou)
        grupo = f"{meta.get('repo', '?')}/{meta.get('fonte', '?')}"
        por_grupo[grupo]["total"] += 1
        por_grupo[grupo]["acertos"] += int(acertou)
        if pred_conf is not None and pred_conf >= args.min_confidence:
            estrato_confiante["total"] += 1
            estrato_confiante["acertos"] += int(acertou)
        itens.append(
            {
                "n": numero,
                "gold": gold_opcao,
                "pred": pred_opcao,
                "conf": pred_conf,
                "latency_s": round(latencia, 2),
                "codigo": meta.get("codigo"),
                "repo": meta.get("repo"),
            }
        )
        print(
            f"[{numero}/{len(exemplos)}] gold={gold_opcao} pred={pred_opcao} "
            f"conf={pred_conf} {'OK' if acertou else 'ERRO'} ({latencia:.1f}s)",
            flush=True,
        )

    total = len(exemplos)
    relatorio = {
        "gguf": str(args.gguf),
        "holdout": str(args.holdout),
        "total": total,
        "acuracia": round(acertos / total, 4) if total else 0.0,
        "json_valido": round(json_validos / total, 4) if total else 0.0,
        "estrato_confiante": {
            "min_confidence": args.min_confidence,
            "cobertura": round(estrato_confiante["total"] / total, 4) if total else 0.0,
            "acuracia": (
                round(estrato_confiante["acertos"] / estrato_confiante["total"], 4)
                if estrato_confiante["total"]
                else None
            ),
        },
        "por_classe": {
            classe: {
                "total": contagem["total"],
                "acuracia": round(contagem["acertos"] / contagem["total"], 4),
            }
            for classe, contagem in sorted(por_classe.items())
        },
        "por_grupo": {
            grupo: {
                "total": contagem["total"],
                "acuracia": round(contagem["acertos"] / contagem["total"], 4),
            }
            for grupo, contagem in sorted(por_grupo.items())
        },
        "confusao": {f"{gold}->{pred}": n for (gold, pred), n in sorted(confusao.items())},
        "latencia_s": {
            "p50": round(percentil(latencias, 50), 2),
            "p95": round(percentil(latencias, 95), 2),
            "media": round(statistics.mean(latencias), 2) if latencias else 0.0,
        },
        "itens": itens,
    }
    args.out.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    resumo = {k: v for k, v in relatorio.items() if k != "itens"}
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
