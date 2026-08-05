"""v3 Parte A — confianca por LOGPROB (não pela confianca auto-reportada).

Um 3B infla a auto-confianca (v2: cobertura 100% no estrato >=0.75). A
probabilidade real do token da OPCAO escolhida, porem, e honesta. Este
script gera com logprobs, extrai o logprob medio dos tokens que formam o
valor de `opcao.id`, converte em pseudo-prob (exp), e faz um SWEEP de
limiar: em cada corte, qual a acuracia e a cobertura do subconjunto
"confiante" (logprob-prob acima do corte). Se existir um corte com
acuracia >=95% e cobertura razoavel, o blocker de calibracao esta resolvido
(roteia os confiantes sozinho, escala o resto p/ humano).

Autocontido (json/math/llama_cpp). Roda no venv WSL com llama-cpp-python.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def carregar_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(linha)
        for linha in path.read_text(encoding="utf-8").splitlines()
        if linha.strip()
    ]


def _prob_da_opcao(texto: str, opcao_id: str, tokens: list[dict]) -> float | None:
    """logprob medio dos tokens que compoem o valor de `opcao.id`, como
    pseudo-prob (exp(media)). Localiza a substring do id no texto e mapeia
    para os tokens que a cobrem, acumulando o comprimento token a token."""
    pos = texto.find(opcao_id)
    if pos < 0:
        return None
    ini, fim = pos, pos + len(opcao_id)
    cursor = 0
    logprobs_no_span: list[float] = []
    for tok in tokens:
        t = tok.get("token", "")
        t_ini, t_fim = cursor, cursor + len(t)
        # token sobrepoe o span do valor do id?
        if t_fim > ini and t_ini < fim:
            lp = tok.get("logprob")
            if lp is not None:
                logprobs_no_span.append(float(lp))
        cursor = t_fim
        if t_ini >= fim:
            break
    if not logprobs_no_span:
        return None
    return math.exp(sum(logprobs_no_span) / len(logprobs_no_span))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gguf", required=True, type=Path)
    parser.add_argument("--holdout", required=True, type=Path)
    parser.add_argument("--schema", required=True, type=Path)
    parser.add_argument("--out", type=Path, default=Path("eval_logprob.json"))
    parser.add_argument("--n-threads", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    from llama_cpp import Llama, LlamaGrammar

    gramatica = LlamaGrammar.from_json_schema(args.schema.read_text(encoding="utf-8"))
    llm = Llama(
        model_path=str(args.gguf),
        n_ctx=2048,
        n_threads=args.n_threads,
        n_gpu_layers=0,
        logits_all=True,
        verbose=False,
    )
    exemplos = carregar_jsonl(args.holdout)
    if args.limit:
        exemplos = exemplos[: args.limit]

    itens: list[dict] = []
    for numero, exemplo in enumerate(exemplos, 1):
        system, usuario = exemplo["messages"][0]["content"], exemplo["messages"][1]["content"]
        gold = json.loads(exemplo["messages"][2]["content"])["opcao"]["id"]
        completion = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": usuario},
            ],
            temperature=0.0,
            max_tokens=args.max_tokens,
            grammar=gramatica,
            logprobs=True,
            top_logprobs=1,
        )
        choice = completion["choices"][0]
        texto = choice["message"]["content"] or ""
        tokens = (choice.get("logprobs") or {}).get("content") or []
        try:
            pred_obj = json.loads(texto)
            pred = pred_obj.get("opcao", {}).get("id")
            conf_self = float(pred_obj.get("confidence", 0.0))
        except (json.JSONDecodeError, TypeError, ValueError):
            pred, conf_self = None, 0.0
        prob_lp = _prob_da_opcao(texto, pred, tokens) if pred else None
        correto = pred == gold
        itens.append(
            {
                "n": numero,
                "gold": gold,
                "pred": pred,
                "correto": correto,
                "conf_self": conf_self,
                "prob_lp": prob_lp,
            }
        )
        print(
            f"[{numero}/{len(exemplos)}] gold={gold} pred={pred} "
            f"self={conf_self} lp={prob_lp} {'OK' if correto else 'ERRO'}",
            flush=True,
        )

    total = len(itens)
    acuracia = sum(i["correto"] for i in itens) / total if total else 0.0
    com_lp = [i for i in itens if i["prob_lp"] is not None]
    # sweep de limiar de logprob-prob
    sweep = []
    for corte in [round(0.05 * k, 2) for k in range(1, 20)]:
        confiantes = [i for i in com_lp if i["prob_lp"] >= corte]
        if not confiantes:
            continue
        acc_conf = sum(i["correto"] for i in confiantes) / len(confiantes)
        sweep.append(
            {
                "corte": corte,
                "cobertura": round(len(confiantes) / total, 3),
                "acuracia_confiante": round(acc_conf, 4),
                "n_confiante": len(confiantes),
            }
        )
    # menor corte que atinge >=95% no subconjunto confiante
    passa = next((s for s in sweep if s["acuracia_confiante"] >= 0.95), None)
    relatorio = {
        "gguf": str(args.gguf),
        "total": total,
        "acuracia_geral": round(acuracia, 4),
        "sweep_logprob": sweep,
        "primeiro_corte_>=95%": passa,
        "itens": itens,
    }
    args.out.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    resumo = {k: v for k, v in relatorio.items() if k != "itens"}
    print(json.dumps(resumo, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    main()
