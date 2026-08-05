"""Self-consistency como gate de incerteza EXTERNO.

A confianca auto-reportada e o logprob falharam (o 3B e confidentemente
errado). Aqui a incerteza vem da ESTABILIDADE da decisao: roda N geracoes
com temperatura>0 e mede o acordo do modelo consigo mesmo. Hipotese: casos
que o modelo erra / que sao escalar-humano produzem DESACORDO (o voto se
divide), enquanto os casos claros dao N/N iguais.

Metrica: voto majoritario = predicao; acordo = (contagem do voto vencedor)/N.
Sweep de limiar de acordo: no subconjunto "confiante" (acordo >= limiar),
qual acuracia e cobertura? Se existir limiar com acuracia>=95% e cobertura
razoavel — e os erros/escalar-humano caem no subconjunto de baixo acordo —
o self-consistency da o gate que faltou (roteia confiante sozinho, escala o
resto).

Autocontido (json/collections/llama_cpp). Roda no venv WSL.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def carregar_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(linha)
        for linha in path.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gguf", required=True, type=Path)
    parser.add_argument("--holdout", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path("eval_consistency.json"))
    parser.add_argument("--n-amostras", type=int, default=5)
    parser.add_argument("--temperatura", type=float, default=0.7)
    parser.add_argument("--n-threads", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    from llama_cpp import Llama, LlamaGrammar

    gramatica = LlamaGrammar.from_json_schema(args.schema.read_text(encoding="utf-8"))
    llm = Llama(
        model_path=str(args.gguf),
        n_ctx=2048,
        n_threads=args.n_threads,
        n_gpu_layers=0,
        seed=1234,
        verbose=False,
    )
    exemplos = carregar_jsonl(args.holdout)
    if args.limit:
        exemplos = exemplos[: args.limit]

    itens: list[dict] = []
    for numero, exemplo in enumerate(exemplos, 1):
        system, usuario = exemplo["messages"][0]["content"], exemplo["messages"][1]["content"]
        gold = json.loads(exemplo["messages"][2]["content"])["opcao"]["id"]
        votos: list[str] = []
        for run in range(args.n_amostras):
            comp = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": usuario},
                ],
                temperature=args.temperatura,
                max_tokens=args.max_tokens,
                grammar=gramatica,
                seed=1000 + run * 7,
            )
            texto = comp["choices"][0]["message"]["content"] or ""
            try:
                votos.append(json.loads(texto).get("opcao", {}).get("id"))
            except (json.JSONDecodeError, TypeError, ValueError):
                votos.append(None)
        cont = Counter(v for v in votos if v is not None)
        if cont:
            pred, n_pred = cont.most_common(1)[0]
            acordo = n_pred / args.n_amostras
        else:
            pred, acordo = None, 0.0
        correto = pred == gold
        itens.append(
            {
                "n": numero,
                "gold": gold,
                "pred": pred,
                "correto": correto,
                "acordo": round(acordo, 3),
                "votos": votos,
            }
        )
        print(
            f"[{numero}/{len(exemplos)}] gold={gold} pred={pred} acordo={acordo:.2f} "
            f"{'OK' if correto else 'ERRO'} votos={votos}",
            flush=True,
        )

    total = len(itens)
    acuracia = sum(i["correto"] for i in itens) / total if total else 0.0
    sweep = []
    for limiar in [1.0, 0.8, 0.6]:
        conf = [i for i in itens if i["acordo"] >= limiar]
        if not conf:
            continue
        sweep.append(
            {
                "limiar_acordo": limiar,
                "cobertura": round(len(conf) / total, 3),
                "acuracia_confiante": round(sum(i["correto"] for i in conf) / len(conf), 4),
                "n": len(conf),
            }
        )
    # acordo medio de corretos vs errados, e dos escalar-humano
    cor = [i["acordo"] for i in itens if i["correto"]]
    err = [i["acordo"] for i in itens if not i["correto"]]
    eh = [(i["acordo"], i["correto"], i["votos"]) for i in itens if i["gold"] == "escalar-humano"]
    relatorio = {
        "gguf": str(args.gguf),
        "n_amostras": args.n_amostras,
        "temperatura": args.temperatura,
        "total": total,
        "acuracia_voto_majoritario": round(acuracia, 4),
        "sweep_acordo": sweep,
        "acordo_medio_corretos": round(sum(cor) / len(cor), 3) if cor else None,
        "acordo_medio_errados": round(sum(err) / len(err), 3) if err else None,
        "escalar_humano_detalhe": eh,
        "itens": itens,
    }
    args.out.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    resumo = {k: v for k, v in relatorio.items() if k != "itens"}
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
