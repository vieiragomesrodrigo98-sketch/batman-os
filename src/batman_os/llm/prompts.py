"""Prompt canônico do LLM Gateway — compartilhado entre provedores.

Um único lugar define o formato visto por TODOS os consumidores: o
`AnthropicLlmGateway`, o `LocalLlmGateway` e os scripts de dataset/
avaliação do modelo local (`scripts/llm_local/`). Se treino e serving
divergirem de prompt, a avaliação offline deixa de prever o comportamento
em produção — por isso este módulo existe (mesma razão do
`local_llm_prompts.py` do radar-preditivo).
"""

from __future__ import annotations

from batman_os.kernel.planning_engine import DecisionPoint

SYSTEM_PROMPT = (
    "Voce e o LLM Gateway do Batman OS, o ultimo recurso na hierarquia "
    "Knowledge First -> Human Last -> LLM Last (Vol.I Principio 6). Voce "
    "resolve um DecisionPoint apenas quando nem uma regra ativa nem um "
    "humano puderam resolve-lo a tempo. Escolha exatamente uma das opcoes "
    "fornecidas, nunca invente uma opcao nova, e retorne sua confianca "
    "real (0.0 a 1.0) e o raciocinio que te levou a escolha."
)


def mensagem_usuario(ponto: DecisionPoint) -> str:
    opcoes = "\n".join(f"- {opcao.id}: {opcao.descricao}" for opcao in ponto.opcoes)
    return (
        f"Pergunta: {ponto.pergunta}\n\n"
        f"Opcoes disponiveis:\n{opcoes}\n\n"
        f"Contexto adicional: {ponto.dados}"
    )
