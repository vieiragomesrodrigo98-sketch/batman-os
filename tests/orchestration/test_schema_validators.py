"""Testes dos validadores de produção da camada de orquestração."""

from __future__ import annotations

from batman_os.foundation.types import CapabilityId
from batman_os.orchestration.schema_validators import (
    ValidadorContratoSempreAprova,
    ValidadorSchemaEstrutural,
)
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects


def _capability() -> CapabilityDefinition:
    return CapabilityDefinition(
        id=CapabilityId("cap-teste"),
        name="cap-teste",
        version="1.0.0",
        deterministic=True,
        side_effects=SideEffects.NONE,
    )


class TestValidadorSchemaEstrutural:
    def test_aprova_quando_todas_as_chaves_estao_presentes(self) -> None:
        validador = ValidadorSchemaEstrutural()
        schema: dict[str, object] = {"properties": {"achados": {}}}

        assert validador.validar({"achados": []}, schema) is True

    def test_reprova_quando_falta_chave(self) -> None:
        validador = ValidadorSchemaEstrutural()
        schema: dict[str, object] = {"properties": {"achados": {}}}

        assert validador.validar({}, schema) is False

    def test_reprova_quando_output_nao_e_dict_mas_schema_exige_propriedades(self) -> None:
        validador = ValidadorSchemaEstrutural()
        schema: dict[str, object] = {"properties": {"achados": {}}}

        assert validador.validar("nao-e-dict", schema) is False

    def test_aprova_output_nao_dict_quando_schema_sem_propriedades(self) -> None:
        validador = ValidadorSchemaEstrutural()

        assert validador.validar("qualquer-coisa", {}) is True


class TestValidadorContratoSempreAprova:
    def test_sempre_aprova(self) -> None:
        validador = ValidadorContratoSempreAprova()

        assert validador.validar(_capability(), {"qualquer": "coisa"}) is True
