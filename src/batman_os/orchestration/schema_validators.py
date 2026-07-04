"""Validadores de produção para o Execution Engine (Vol.III Cap.12).

Promove para produção o mesmo padrão já usado no teste de referência
(`tests/runtime/test_execution_engine.py::ValidadorSchemaChaves`): checagem
estrutural de presença de chaves, não um validador de JSON Schema completo —
o próprio Protocol `ValidadorSchema` documenta isso como decisão aceita
("implementação real usaria um validador JSON Schema completo, fora das
dependências desta construção"). Suficiente para os schemas achatados
(achados com campos escalares) do primeiro lote de Capabilities migradas.
Reavaliar se um lote futuro exigir schemas aninhados que essa checagem não
capture.
"""

from __future__ import annotations

from typing import Any

from batman_os.runtime.capability_engine import CapabilityDefinition


class ValidadorSchemaEstrutural:
    """Satisfaz `runtime.execution_engine.ValidadorSchema` — aprova se todas
    as chaves de `output_schema["properties"]` estão presentes no output."""

    def validar(self, output: Any, output_schema: dict[str, Any]) -> bool:
        propriedades = output_schema.get("properties") or {}
        if not isinstance(output, dict):
            return not propriedades
        return all(chave in output for chave in propriedades)


class ValidadorContratoSempreAprova:
    """Satisfaz `runtime.execution_engine.ValidadorContratoNaoDeterministico`.
    Nunca de fato exercitado neste lote — todas as Capabilities migradas são
    `deterministic=True` (o Execution Engine só chama este validador quando
    `not capability.deterministic`); existe só para satisfazer a assinatura
    do construtor de `ExecutionEngine`."""

    def validar(self, capability: CapabilityDefinition, output: Any) -> bool:
        del capability, output
        return True
