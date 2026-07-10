"""Testes do Capability Engine (Vol.III Cap.11) — AT-11.1 a AT-11.3."""

from __future__ import annotations

from typing import Any

import pytest

from batman_os.foundation.types import CapabilityId, CapabilityRef, SkillRef
from batman_os.kernel.mission_runtime import MissionIntent
from batman_os.runtime.capability_engine import (
    CapabilityDefinition,
    CapabilityNaoEncontrada,
    CapabilityRegistry,
    RegistroInvalido,
    SideEffects,
    StatusCapability,
)


def _def(
    nome: str = "detect-sql-injection",
    versao: str = "1.0.0",
    deterministic: bool = True,
    required_skills: list[SkillRef] | None = None,
    input_schema: dict[str, Any] | None = None,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        id=CapabilityId(nome),
        name=nome,
        version=versao,
        input_schema=input_schema or {},
        output_schema={},
        deterministic=deterministic,
        side_effects=SideEffects.NONE,
        required_skills=required_skills or [],
    )


class TestAT111ResolucaoEstavel:
    def test_resolve_mesma_ref_sempre_retorna_a_mesma_definicao(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_def(versao="1.0.0"))
        ref = CapabilityRef(capability_id=CapabilityId("detect-sql-injection"), versao="1.0.0")

        antes = registry.resolve(ref)
        registry.register(_def(nome="outra-capability", versao="1.0.0"))
        depois = registry.resolve(ref)

        assert antes.input_schema == depois.input_schema
        assert antes.output_schema == depois.output_schema
        assert antes.deterministic == depois.deterministic
        assert antes.side_effects == depois.side_effects

    def test_resolve_versao_inexistente_falha(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_def(versao="1.0.0"))

        with pytest.raises(CapabilityNaoEncontrada):
            registry.resolve(
                CapabilityRef(capability_id=CapabilityId("detect-sql-injection"), versao="9.9.9")
            )


class TestAT112MudancaMajorExigeDeprecatedBy:
    def test_bump_major_sem_depreca_e_rejeitado(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_def(versao="1.0.0"))

        with pytest.raises(RegistroInvalido):
            registry.register(_def(versao="2.0.0"))

    def test_bump_major_com_depreca_funciona_e_marca_versao_antiga(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_def(versao="1.0.0"))
        registry.register(
            _def(versao="2.0.0"),
            depreca=CapabilityRef(
                capability_id=CapabilityId("detect-sql-injection"), versao="1.0.0"
            ),
        )

        antiga = registry.resolve(
            CapabilityRef(capability_id=CapabilityId("detect-sql-injection"), versao="1.0.0")
        )
        assert antiga.status == StatusCapability.DEPRECATED
        assert antiga.deprecated_by == CapabilityId("detect-sql-injection")

    def test_bump_minor_nao_exige_depreca(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_def(versao="1.0.0"))
        registry.register(_def(versao="1.1.0"))  # nao levanta

        assert registry.resolve(
            CapabilityRef(capability_id=CapabilityId("detect-sql-injection"), versao="1.1.0")
        )

    def test_deterministic_false_sem_skill_llm_gateway_e_rejeitado(self) -> None:
        registry = CapabilityRegistry()
        with pytest.raises(RegistroInvalido):
            registry.register(_def(deterministic=False, required_skills=[]))

    def test_deterministic_false_com_skill_llm_gateway_funciona(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _def(deterministic=False, required_skills=[SkillRef(skill_id="llm-gateway")])
        )


class TestAT113FindCandidatesDeterministico:
    def test_mesma_entrada_mesmo_estado_produz_mesmo_resultado(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_def(nome="cap-a", input_schema={"properties": {"alvo": {}}}))
        registry.register(_def(nome="cap-b", input_schema={"properties": {"outro": {}}}))
        intent = MissionIntent(dados={"alvo": "servico-x"})

        resultado_1 = registry.find_candidates(intent)
        resultado_2 = registry.find_candidates(intent)

        assert [d.id for d in resultado_1] == [d.id for d in resultado_2]

    def test_filtra_por_compatibilidade_de_schema(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_def(nome="compativel", input_schema={"properties": {"alvo": {}}}))
        registry.register(
            _def(nome="incompativel", input_schema={"properties": {"campo_ausente": {}}})
        )
        intent = MissionIntent(dados={"alvo": "servico-x"})

        candidatos = registry.find_candidates(intent)

        assert [d.id for d in candidatos] == [CapabilityId("compativel")]

    def test_capability_desativada_nunca_e_candidata(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_def(nome="cap-a"))
        registry.disable(CapabilityId("cap-a"), "1.0.0", reason="falha critica")

        candidatos = registry.find_candidates(MissionIntent(dados={}))

        assert candidatos == []

    def test_ordena_por_especificidade_depois_versao(self) -> None:
        registry = CapabilityRegistry()
        registry.register(
            _def(nome="generica", input_schema={})  # sem properties -> compativel com tudo
        )
        registry.register(
            _def(nome="especifica", input_schema={"properties": {"alvo": {}, "ambiente": {}}})
        )
        intent = MissionIntent(dados={"alvo": "x", "ambiente": "prod"})

        candidatos = registry.find_candidates(intent)

        assert candidatos[0].id == CapabilityId("especifica")

    def test_buscar_candidatos_retorna_refs_para_uso_direto_no_planning_engine(self) -> None:
        registry = CapabilityRegistry()
        registry.register(_def(nome="cap-a"))

        refs = registry.buscar_candidatos(MissionIntent(dados={}))

        assert refs == [CapabilityRef(capability_id=CapabilityId("cap-a"), versao="1.0.0")]

    def test_campo_const_discrimina_capabilities_com_mesmas_chaves(self) -> None:
        """Achado de auditoria (validacao final Milestones 2-7): duas
        Capabilities com o MESMO conjunto de nomes de campo (`tipo`,
        `caminho`) mas valores de `tipo` diferentes NAO podem empatar como
        candidatas para a mesma entrada — sem isso, `_compor_via_grafo_
        capacidades` gera um passo por candidato empatado, e o scan crasha
        com `EntradaNaoRegistrada` ao tentar invocar o segundo passo."""
        registry = CapabilityRegistry()
        registry.register(
            _def(
                nome="cap-tipo-a",
                input_schema={
                    "properties": {
                        "tipo": {"const": "tipo-a", "default": "tipo-a"},
                        "caminho": {},
                    }
                },
            )
        )
        registry.register(
            _def(
                nome="cap-tipo-b",
                input_schema={
                    "properties": {
                        "tipo": {"const": "tipo-b", "default": "tipo-b"},
                        "caminho": {},
                    }
                },
            )
        )
        intent = MissionIntent(dados={"tipo": "tipo-a", "caminho": "x.py"})

        candidatos = registry.find_candidates(intent)

        assert [d.id for d in candidatos] == [CapabilityId("cap-tipo-a")]

    def test_campo_sem_const_continua_exigindo_so_presenca_da_chave(self) -> None:
        """Propriedade sem `const` (schema de Milestone 1/2, sem
        discriminador) preserva o comportamento anterior — nao regride."""
        registry = CapabilityRegistry()
        registry.register(_def(nome="cap-a", input_schema={"properties": {"alvo": {}}}))
        intent = MissionIntent(dados={"alvo": "qualquer-valor"})

        candidatos = registry.find_candidates(intent)

        assert [d.id for d in candidatos] == [CapabilityId("cap-a")]


def test_versao_do_registro_muda_a_cada_mutacao() -> None:
    registry = CapabilityRegistry()
    v0 = registry.versao()
    registry.register(_def())
    v1 = registry.versao()

    assert v0 != v1


class TestOwnerETags:
    """Fase 1 do roadmap de plataforma (item "capability.yaml") --
    extensao aditiva, opcional, sem afetar nenhuma Capability ja
    registrada."""

    def test_owner_e_tags_tem_default_vazio(self) -> None:
        definicao = _def()

        assert definicao.owner == ""
        assert definicao.tags == []

    def test_owner_e_tags_aceitam_valores_explicitos(self) -> None:
        definicao = CapabilityDefinition(
            id=CapabilityId("cap-com-metadados"),
            name="cap-com-metadados",
            version="1.0.0",
            deterministic=True,
            side_effects=SideEffects.NONE,
            owner="code-reviewer",
            tags=["seguranca", "regressao"],
        )

        assert definicao.owner == "code-reviewer"
        assert definicao.tags == ["seguranca", "regressao"]
