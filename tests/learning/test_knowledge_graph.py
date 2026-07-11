"""Testes do Knowledge Graph (Vol.VI Cap.23) — AT-23.1 a AT-23.3."""

from __future__ import annotations

from datetime import timedelta

import pytest
from pydantic import ValidationError

from batman_os.foundation.types import (
    CapabilityId,
    MissionTypeId,
    PlaybookId,
    SkillId,
    TenantId,
    agora,
)
from batman_os.learning.knowledge_graph import (
    KnowledgeEdge,
    KnowledgeGraph,
    KnowledgeNode,
    KnowledgeNodeDetail,
    TipoAresta,
    TipoNoKnowledge,
    detectar_drift,
    verificar_integridade,
)

TENANT = TenantId("tenant-1")
OUTRO_TENANT = TenantId("tenant-2")


def _no(tipo: TipoNoKnowledge, ref: str) -> KnowledgeNode:
    return KnowledgeNode(tipo=tipo, ref=ref, tenant_id=TENANT)


class TestAT231ReconciliacaoDentroDoSla:
    def test_no_atualizado_dentro_do_sla_nao_e_drift(self) -> None:
        grafo = KnowledgeGraph()
        no = _no(TipoNoKnowledge.CAPABILITY, "cap-a")
        agora_ = agora()
        grafo.adicionar_no(no, KnowledgeNodeDetail(atualizado_em=agora_))

        drift = detectar_drift(
            grafo, timestamps_fonte={no: agora_ + timedelta(minutes=1)}, sla=timedelta(hours=1)
        )
        assert drift == []

    def test_no_desatualizado_alem_do_sla_e_drift(self) -> None:
        grafo = KnowledgeGraph()
        no = _no(TipoNoKnowledge.CAPABILITY, "cap-a")
        agora_ = agora()
        grafo.adicionar_no(no, KnowledgeNodeDetail(atualizado_em=agora_))

        drift = detectar_drift(
            grafo,
            timestamps_fonte={no: agora_ + timedelta(hours=2)},
            sla=timedelta(hours=1),
        )
        assert drift == [no]

    def test_no_nunca_registrado_no_grafo_e_drift(self) -> None:
        grafo = KnowledgeGraph()
        no = _no(TipoNoKnowledge.CAPABILITY, "cap-nunca-registrada")

        drift = detectar_drift(grafo, timestamps_fonte={no: agora()}, sla=timedelta(hours=1))
        assert drift == [no]


class TestAT232EquivalenciaComVarreduraDeImpactoDeSkill:
    """Vol.VI Cap.23, secao 23.5 (AT-23.2) — impact_analysis de uma Skill
    deve retornar o mesmo conjunto de Capabilities que a varredura manual
    do Vol.IV Cap.17 (`propor_mudanca_major_de_skill`)."""

    def test_capabilities_que_usam_a_skill_sao_diretamente_dependentes(self) -> None:
        grafo = KnowledgeGraph()
        skill = _no(TipoNoKnowledge.SKILL, "git")
        cap_a = _no(TipoNoKnowledge.CAPABILITY, "cap-a")
        cap_b = _no(TipoNoKnowledge.CAPABILITY, "cap-b")
        cap_sem_dependencia = _no(TipoNoKnowledge.CAPABILITY, "cap-c")

        for no in (skill, cap_a, cap_b, cap_sem_dependencia):
            grafo.adicionar_no(no)
        grafo.adicionar_aresta(
            KnowledgeEdge(kind=TipoAresta.USES, de=cap_a, para=skill, tenant_id=TENANT)
        )
        grafo.adicionar_aresta(
            KnowledgeEdge(kind=TipoAresta.USES, de=cap_b, para=skill, tenant_id=TENANT)
        )

        relatorio = grafo.impact_analysis(skill)

        afetadas = {n.ref for n in relatorio.directly_dependent}
        assert afetadas == {"cap-a", "cap-b"}
        assert "cap-c" not in afetadas

    def test_equivalencia_direta_com_cap17_capabilities_afetadas(self) -> None:
        """Reproduz o mesmo cenario testado em Cap.17
        (test_skills.py::TestAT172VarreduraDeImpactoDeMudancaMajor) e
        confirma que o Knowledge Graph chega ao mesmo conjunto."""
        from batman_os.capabilities.capability_contract import (
            AcceptanceTest,
            CapabilityImplementation,
            ResultadoEsperado,
            propor_mudanca_major_de_skill,
        )
        from batman_os.capabilities.skills import SkillDefinition, SkillRegistry
        from batman_os.foundation.types import SkillRef
        from batman_os.runtime.capability_engine import CapabilityDefinition, SideEffects

        def _handler_ok(entrada: object, contexto: object) -> object:
            del contexto
            if entrada is None or "invalida" in entrada:  # type: ignore[operator]
                raise ValueError("entrada invalida")
            return {"y": "ok"}

        testes = [
            AcceptanceTest(
                name="feliz", entrada={"x": 1}, resultado_esperado=ResultadoEsperado.SUCCESS
            ),
            AcceptanceTest(
                name="invalida",
                entrada={"invalida": True},
                resultado_esperado=ResultadoEsperado.SCHEMA_REJECTION,
            ),
        ]
        impl = CapabilityImplementation(
            definition=CapabilityDefinition(
                id=CapabilityId("cap-a"),
                name="cap-a",
                version="1.0.0",
                input_schema={"properties": {"x": {}}},
                output_schema={"properties": {"y": {}}},
                deterministic=True,
                side_effects=SideEffects.NONE,
            ),
            handler=_handler_ok,
            acceptance_tests=testes,
            skills_used=[SkillRef(skill_id=SkillId("git"))],
        )

        registry = SkillRegistry()
        registry.register(SkillDefinition(id=SkillId("git"), name="git", version="1.0.0"))
        resultado_cap17 = propor_mudanca_major_de_skill(
            SkillDefinition(id=SkillId("git"), name="git", version="2.0.0"), [impl], registry
        )

        grafo = KnowledgeGraph()
        skill_no = _no(TipoNoKnowledge.SKILL, "git")
        cap_no = _no(TipoNoKnowledge.CAPABILITY, "cap-a")
        grafo.adicionar_no(skill_no)
        grafo.adicionar_no(cap_no)
        grafo.adicionar_aresta(
            KnowledgeEdge(kind=TipoAresta.USES, de=cap_no, para=skill_no, tenant_id=TENANT)
        )

        relatorio = grafo.impact_analysis(skill_no)
        afetadas_grafo = {CapabilityId(n.ref) for n in relatorio.directly_dependent}

        assert afetadas_grafo == set(resultado_cap17.capabilities_afetadas)
        assert list(afetadas_grafo) == resultado_cap17.capabilities_afetadas

    def test_transitivamente_dependente_via_playbook(self) -> None:
        grafo = KnowledgeGraph()
        skill = _no(TipoNoKnowledge.SKILL, "git")
        cap = _no(TipoNoKnowledge.CAPABILITY, "cap-a")
        playbook = _no(TipoNoKnowledge.PLAYBOOK, "pb-1")

        grafo.adicionar_no(skill)
        grafo.adicionar_no(cap)
        grafo.adicionar_no(
            playbook, KnowledgeNodeDetail(mission_type_id=MissionTypeId("investigate-incident"))
        )
        grafo.adicionar_aresta(
            KnowledgeEdge(kind=TipoAresta.USES, de=cap, para=skill, tenant_id=TENANT)
        )
        grafo.adicionar_aresta(
            KnowledgeEdge(kind=TipoAresta.INSTANTIATED_BY, de=playbook, para=cap, tenant_id=TENANT)
        )

        relatorio = grafo.impact_analysis(skill)

        assert cap in relatorio.directly_dependent
        assert playbook in relatorio.transitively_dependent
        assert relatorio.affected_playbooks == [PlaybookId("pb-1")]
        assert relatorio.affected_mission_types == [MissionTypeId("investigate-incident")]


class TestAT233RegraSemJustifiedByViolaIntegridade:
    def test_regra_sem_justified_by_e_violacao(self) -> None:
        grafo = KnowledgeGraph()
        regra = _no(TipoNoKnowledge.RULE, "SRE-002")
        grafo.adicionar_no(regra)

        violacoes = verificar_integridade(grafo)
        assert any("SRE-002" in v for v in violacoes)

    def test_regra_com_justified_by_esta_ok(self) -> None:
        grafo = KnowledgeGraph()
        regra = _no(TipoNoKnowledge.RULE, "SRE-002")
        evidencia = _no(TipoNoKnowledge.EVIDENCE, "incidente-4821")
        grafo.adicionar_no(regra)
        grafo.adicionar_no(evidencia)
        grafo.adicionar_aresta(
            KnowledgeEdge(kind=TipoAresta.JUSTIFIED_BY, de=regra, para=evidencia, tenant_id=TENANT)
        )

        violacoes = verificar_integridade(grafo)
        assert violacoes == []

    def test_outros_tipos_de_no_nao_exigem_justified_by(self) -> None:
        grafo = KnowledgeGraph()
        grafo.adicionar_no(_no(TipoNoKnowledge.CAPABILITY, "cap-a"))

        violacoes = verificar_integridade(grafo)
        assert violacoes == []


class TestProvenanceTrail:
    def test_trilha_completa_ate_a_origem(self) -> None:
        grafo = KnowledgeGraph()
        regra = _no(TipoNoKnowledge.RULE, "R-17")
        registro = _no(TipoNoKnowledge.OPERATIONAL_RECORD, "or-12x")
        evidencia = _no(TipoNoKnowledge.EVIDENCE, "incidente-4821")
        grafo.adicionar_no(regra)
        grafo.adicionar_no(registro)
        grafo.adicionar_no(evidencia)
        grafo.adicionar_aresta(
            KnowledgeEdge(kind=TipoAresta.PROMOTED_FROM, de=regra, para=registro, tenant_id=TENANT)
        )
        grafo.adicionar_aresta(
            KnowledgeEdge(
                kind=TipoAresta.JUSTIFIED_BY, de=registro, para=evidencia, tenant_id=TENANT
            )
        )

        trilha = grafo.provenance_trail(regra)
        assert trilha == [registro, evidencia]

    def test_sem_proveniencia_retorna_trilha_vazia_sem_lancar(self) -> None:
        grafo = KnowledgeGraph()
        regra = _no(TipoNoKnowledge.RULE, "R-99")
        grafo.adicionar_no(regra)

        assert grafo.provenance_trail(regra) == []

    def test_ciclo_de_proveniencia_nao_trava_e_nao_repete_infinitamente(self) -> None:
        grafo = KnowledgeGraph()
        a = _no(TipoNoKnowledge.RULE, "a")
        b = _no(TipoNoKnowledge.RULE, "b")
        grafo.adicionar_no(a)
        grafo.adicionar_no(b)
        grafo.adicionar_aresta(
            KnowledgeEdge(kind=TipoAresta.PROMOTED_FROM, de=a, para=b, tenant_id=TENANT)
        )
        grafo.adicionar_aresta(
            KnowledgeEdge(kind=TipoAresta.PROMOTED_FROM, de=b, para=a, tenant_id=TENANT)
        )

        trilha = grafo.provenance_trail(a)
        assert trilha == [b]  # para antes de repetir 'a'


class TestFase4Estagio41TenantIdEmNoEAresta:
    """Vol.VI Cap.23 — retrofit de `tenant_id` (Fase 4, Estagio 4.1):
    fecha o gap documentado em `foundation/tenant_isolation.py` antes do
    Mission Graph (Estagio 4.2) introduzir nos de Missao, que ja carregam
    `tenant_id` obrigatorio em todo o resto do Kernel."""

    def test_nos_por_tenant_filtra_apenas_o_tenant_pedido(self) -> None:
        grafo = KnowledgeGraph()
        no_tenant_1 = KnowledgeNode(tipo=TipoNoKnowledge.RULE, ref="R-1", tenant_id=TENANT)
        no_tenant_2 = KnowledgeNode(tipo=TipoNoKnowledge.RULE, ref="R-2", tenant_id=OUTRO_TENANT)
        grafo.adicionar_no(no_tenant_1)
        grafo.adicionar_no(no_tenant_2)

        nos_do_tenant_1 = grafo.nos_por_tenant(TENANT)

        assert nos_do_tenant_1 == [no_tenant_1]

    def test_nos_por_tenant_sem_nenhum_no_do_tenant_retorna_vazio(self) -> None:
        grafo = KnowledgeGraph()
        grafo.adicionar_no(KnowledgeNode(tipo=TipoNoKnowledge.RULE, ref="R-1", tenant_id=TENANT))

        assert grafo.nos_por_tenant(OUTRO_TENANT) == []

    def test_knowledge_node_sem_tenant_id_e_rejeitado(self) -> None:
        with pytest.raises(ValidationError):
            KnowledgeNode(tipo=TipoNoKnowledge.RULE, ref="R-1")  # type: ignore[call-arg]

    def test_knowledge_edge_sem_tenant_id_e_rejeitado(self) -> None:
        de = _no(TipoNoKnowledge.RULE, "R-1")
        para = _no(TipoNoKnowledge.EVIDENCE, "ev-1")
        with pytest.raises(ValidationError):
            KnowledgeEdge(kind=TipoAresta.JUSTIFIED_BY, de=de, para=para)  # type: ignore[call-arg]
