"""Utilidades de JSON Schema do LLM Gateway — compartilhadas entre provedores.

`flatten_refs` veio do `anthropic_gateway.py` (onde nasceu privada) para cá
quando o `LocalLlmGateway` passou a precisar do mesmo schema achatado para
compilar a gramática GBNF.
"""

from __future__ import annotations

import copy
from typing import Any

from batman_os.kernel.decision_engine import RespostaLlmCandidata
from batman_os.kernel.planning_engine import DecisionPoint


def flatten_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve `$ref` inline — Pydantic gera `$defs` para tipos aninhados
    (ex.: `DecisionOption` dentro de `RespostaLlmCandidata`); a Anthropic
    aceita `$defs`, mas resolver explicitamente evita edge cases, e a
    compilação de gramática GBNF do llama.cpp exige o schema já achatado
    (lógica genérica, sem acoplamento a domínio — adaptada quase literal do
    radar-preditivo)."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})
    if not defs:
        return schema

    def resolve(obj: Any) -> Any:
        if isinstance(obj, dict):
            if "$ref" in obj:
                nome_ref = obj["$ref"].rsplit("/", 1)[-1]
                return resolve(defs.get(nome_ref, obj))
            return {k: resolve(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [resolve(i) for i in obj]
        return obj

    resolved: dict[str, Any] = resolve(schema)
    return resolved


def schema_resposta_para_ponto(ponto: DecisionPoint) -> dict[str, Any]:
    """Schema de `RespostaLlmCandidata` achatado e com `opcao.id` restrito
    por `enum` às opções deste DecisionPoint. A restrição elimina NA
    GRAMÁTICA (não só na pós-validação) o modo de falha nº 1 de um modelo
    pequeno: inventar uma opção que não existe."""
    schema = flatten_refs(RespostaLlmCandidata.model_json_schema())
    opcao_props = schema.get("properties", {}).get("opcao", {}).get("properties", {})
    if "id" in opcao_props:
        opcao_props["id"] = {**opcao_props["id"], "enum": [opcao.id for opcao in ponto.opcoes]}
    return schema
