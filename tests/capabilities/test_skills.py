"""Testes de Skills (Vol.IV Cap.17) — AT-17.1 a AT-17.3."""

from __future__ import annotations

from typing import Any

import pytest

from batman_os.capabilities.capability_contract import (
    AcceptanceTest,
    CapabilityImplementation,
    GapDeChecklist,
    ResultadoEsperado,
    certificar,
    propor_mudanca_major_de_skill,
    verificar_checklist,
)
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.skills import (
    CicloDeDependenciaDetectado,
    SkillDefinition,
    SkillRegistry,
    StatusSkill,
)
from batman_os.foundation.types import (
    CapabilityId,
    MissionId,
    SkillId,
    SkillRef,
    StepId,
    TenantId,
    agora,
)
from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _handler_ok(entrada: Any, contexto: ExecutionContext) -> Any:
    del contexto
    if entrada is None or "invalida" in entrada:
        raise ValueError("entrada invalida")
    if "trava" in entrada:
        raise TimeoutError("timeout simulado")
    return {"y": "ok"}


def _testes_completos() -> list[AcceptanceTest]:
    return [
        AcceptanceTest(
            name="caminho-feliz", entrada={"x": 1}, resultado_esperado=ResultadoEsperado.SUCCESS
        ),
        AcceptanceTest(
            name="entrada-invalida",
            entrada={"invalida": True},
            resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
        ),
        AcceptanceTest(
            name="timeout-dependencia",
            entrada={"trava": True},
            resultado_esperado=ResultadoEsperado.TIMEOUT,
        ),
    ]


def _implementacao(skills_used: list[SkillRef] | None = None) -> CapabilityImplementation:
    definicao = CapabilityDefinition(
        id=CapabilityId("cap-a"),
        name="cap-a",
        version="1.0.0",
        input_schema={"properties": {"x": {}}},
        output_schema={"properties": {"y": {}}},
        deterministic=True,
        side_effects=SideEffects.NONE,
    )
    return CapabilityImplementation(
        definition=definicao,
        handler=_handler_ok,
        acceptance_tests=_testes_completos(),
        skills_used=skills_used or [],
    )


def _skill(
    id_: str,
    versao: str = "1.0.0",
    dependencies: list[SkillId] | None = None,
    status: StatusSkill = StatusSkill.ACTIVE,
) -> SkillDefinition:
    return SkillDefinition(
        id=SkillId(id_), name=id_, version=versao, dependencies=dependencies or [], status=status
    )


class TestAT171SkillDisabledImpedeCertificacao:
    def test_capability_com_skill_desativada_e_rejeitada(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill("git", versao="1.0.0"))
        registry.register(_skill("git", versao="2.0.0", status=StatusSkill.DISABLED))

        implementacao = _implementacao(skills_used=[SkillRef(skill_id=SkillId("git"))])
        gaps = verificar_checklist(implementacao, skill_registry=registry)

        assert any("git" in g for g in gaps)

    def test_capability_com_skill_inexistente_e_rejeitada(self) -> None:
        registry = SkillRegistry()
        implementacao = _implementacao(skills_used=[SkillRef(skill_id=SkillId("inexistente"))])

        gaps = verificar_checklist(implementacao, skill_registry=registry)
        assert any("inexistente" in g for g in gaps)

    def test_certificar_propaga_rejeicao_de_skill(self) -> None:
        registry = SkillRegistry()
        implementacao = _implementacao(skills_used=[SkillRef(skill_id=SkillId("inexistente"))])

        with pytest.raises(GapDeChecklist):
            certificar(
                implementacao,
                revisao_humana_obtida=True,
                entrada_para_teste_idempotencia={"x": 1},
                contexto_para_teste_idempotencia=_contexto(),
                skill_registry=registry,
            )

    def test_skill_ativa_permite_certificacao(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill("git"))
        implementacao = _implementacao(skills_used=[SkillRef(skill_id=SkillId("git"))])

        gaps = verificar_checklist(implementacao, skill_registry=registry)
        assert gaps == []


class TestAT172VarreduraDeImpactoDeMudancaMajor:
    def test_mudanca_major_promovida_se_capabilities_continuam_passando(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill("git", versao="1.0.0"))
        impl = _implementacao(skills_used=[SkillRef(skill_id=SkillId("git"))])

        resultado = propor_mudanca_major_de_skill(_skill("git", versao="2.0.0"), [impl], registry)

        assert resultado.skill_promovida is True
        assert resultado.capabilities_afetadas == [CapabilityId("cap-a")]
        assert registry.versao_mais_recente(SkillId("git")).version == "2.0.0"  # type: ignore[union-attr]

    def test_mudanca_major_nao_promovida_se_capability_quebra(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill("git", versao="1.0.0"))

        testes_que_sempre_falham = [
            AcceptanceTest(
                name="quebrado",
                entrada={"invalida": True},
                resultado_esperado=ResultadoEsperado.SUCCESS,
            )
        ]
        impl = CapabilityImplementation(
            definition=CapabilityDefinition(
                id=CapabilityId("cap-quebrada"),
                name="cap-quebrada",
                version="1.0.0",
                input_schema={"properties": {"x": {}}},
                output_schema={"properties": {"y": {}}},
                deterministic=True,
                side_effects=SideEffects.NONE,
            ),
            handler=_handler_ok,
            acceptance_tests=testes_que_sempre_falham,
            skills_used=[SkillRef(skill_id=SkillId("git"))],
        )

        resultado = propor_mudanca_major_de_skill(_skill("git", versao="2.0.0"), [impl], registry)

        assert resultado.skill_promovida is False
        assert resultado.capabilities_que_quebraram == [CapabilityId("cap-quebrada")]
        # versao 2.0.0 nunca foi registrada
        assert registry.resolve(SkillId("git"), "2.0.0") is None

    def test_capability_sem_dependencia_na_skill_nao_e_afetada(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill("git"))
        impl_sem_dependencia = _implementacao(skills_used=[])

        resultado = propor_mudanca_major_de_skill(
            _skill("git", versao="2.0.0"), [impl_sem_dependencia], registry
        )

        assert resultado.capabilities_afetadas == []
        assert resultado.skill_promovida is True


class TestAT173CicloDeDependenciaRejeitado:
    def test_ciclo_direto_e_rejeitado(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill("a", dependencies=[SkillId("b")]))

        with pytest.raises(CicloDeDependenciaDetectado):
            registry.register(_skill("b", dependencies=[SkillId("a")]))

    def test_ciclo_indireto_e_rejeitado(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill("a", dependencies=[SkillId("b")]))
        registry.register(_skill("b", dependencies=[SkillId("c")]))

        with pytest.raises(CicloDeDependenciaDetectado):
            registry.register(_skill("c", dependencies=[SkillId("a")]))

    def test_grafo_sem_ciclo_e_aceito(self) -> None:
        registry = SkillRegistry()
        registry.register(_skill("yaml-parser"))
        registry.register(_skill("http-client"))
        registry.register(
            _skill("kubectl", dependencies=[SkillId("yaml-parser"), SkillId("http-client")])
        )

        assert registry.resolve(SkillId("kubectl"), "1.0.0") is not None
