"""Vol.IX Cap.34/35 — prova ponta-a-ponta do Playbook "Auditar Segurança"
(Fase 3 do roadmap de plataforma, `.claude/plans/peaceful-wondering-
hearth.md`, Estágio 3.4).

Mesma doutrina de `test_scan_e2e.py`: nenhum mock de Kernel/Runtime/
Capability — chama `executar_auditoria_seguranca()` (a função pública real
da CLI, `cli/auditoria_seguranca_command.py`) contra um repositório
sintético com violações REAIS plantadas, provando que os Estágios 3.1-3.3
se compõem de ponta a ponta: 1 Missão, 7 steps (6 checagens + 1 relatório),
DAG de dependências resolvida via `WorkflowEngine`, achados agregados
corretamente no relatório final.
"""

from __future__ import annotations

from pathlib import Path

from batman_os.cli.auditoria_seguranca_command import executar_auditoria_seguranca
from batman_os.learning.knowledge_graph import KnowledgeGraph, TipoAresta, TipoNoKnowledge


def _plantar_repositorio_com_violacoes(root: Path) -> None:
    """4 violações reais (CLOUD-001, DEVOPS-003, CLOUD-002, DEP-003) + 2
    checagens deliberadamente limpas (RED-007: nenhuma chave hardcoded;
    DEVOPS-004: nenhum workflow do GitHub Actions presente)."""
    (root / "api").mkdir(parents=True)
    # CLOUD-001 (critical) -- credencial de nuvem hardcoded.
    (root / "api" / "config.py").write_text("AWS_KEY = 'AKIAABCDEFGHIJKLMNOP'\n", encoding="utf-8")

    # DEVOPS-003 (critical) -- .env presente, .gitignore sem excluir .env.
    (root / ".env").write_text("SECRET=x\n", encoding="utf-8")
    (root / ".gitignore").write_text("node_modules/\n", encoding="utf-8")

    # CLOUD-002 (medium) -- Dockerfile sem HEALTHCHECK.
    (root / "Dockerfile").write_text(
        'FROM python:3.11\nCMD ["python", "app.py"]\n', encoding="utf-8"
    )

    # DEP-003 (medium) -- dependencia sem teto de versao.
    (root / "pyproject.toml").write_text(
        '[project]\nname = "smoke"\nversion = "0.1.0"\ndependencies = ["fastapi>=0.100"]\n',
        encoding="utf-8",
    )

    # RED-007 -- deliberadamente limpo: nenhuma AES_KEY/SECRET_KEY/etc.
    # literal em api/config.py (só a credencial de nuvem acima, que RED-007
    # nao reconhece).

    # DEVOPS-004 -- deliberadamente limpo: nenhum .github/workflows/*.yml
    # plantado, glob nao encontra nada.


class TestAuditoriaSegurancaPlaybookPontaAPonta:
    def test_playbook_completo_detecta_exatamente_as_4_violacoes_plantadas(
        self, tmp_path: Path
    ) -> None:
        _plantar_repositorio_com_violacoes(tmp_path)

        resultado = executar_auditoria_seguranca(tmp_path)

        assert resultado.estado_final == "completed"

        codigos = {a["codigo"] for a in resultado.achados}
        assert codigos == {"CLOUD-001", "DEVOPS-003", "CLOUD-002", "DEP-003"}
        assert len(resultado.achados) == 4

        assert resultado.relatorio is not None
        assert resultado.relatorio["total_achados"] == 4
        assert resultado.relatorio["resumo_por_severidade"] == {"critical": 2, "medium": 2}
        assert resultado.relatorio["resumo_por_codigo"] == {
            "CLOUD-001": 1,
            "DEVOPS-003": 1,
            "CLOUD-002": 1,
            "DEP-003": 1,
        }

    def test_repositorio_limpo_completa_sem_nenhum_achado(self, tmp_path: Path) -> None:
        (tmp_path / "api").mkdir()
        (tmp_path / "api" / "app.py").write_text("print('ola mundo')\n", encoding="utf-8")

        resultado = executar_auditoria_seguranca(tmp_path)

        assert resultado.estado_final == "completed"
        assert resultado.achados == []
        assert resultado.relatorio is not None
        assert resultado.relatorio["total_achados"] == 0

    def test_resultado_referencia_mission_id_e_workflow_run_id_reais(self, tmp_path: Path) -> None:
        """`estado_final == "completed"` só é alcançado depois de
        `runtime.transition(..., WORKFLOW_COMPLETED)` suceder de verdade
        (`playbook_driver.py`) — prova que a composição passa pelo Mission
        Runtime real, não só pelo WorkflowEngine isolado."""
        _plantar_repositorio_com_violacoes(tmp_path)

        resultado = executar_auditoria_seguranca(tmp_path)

        assert resultado.estado_final == "completed"
        assert resultado.mission_id is not None
        assert resultado.workflow_run_id is not None

    def test_grafo_de_conhecimento_recebe_a_missao_reconciliada(self, tmp_path: Path) -> None:
        """Fase 4, Estágio 4.3 — mesma prova ponta-a-ponta, agora passando
        `grafo_conhecimento` real: confirma que a Missão real (não uma
        fake de unit test) aparece no Mission Graph com o Playbook
        correto. Este fluxo nunca produz `DecisionPoint` (ver docstring
        de `_SemConhecimentoAinda`) — cobre o caso "Missão sem decisões"
        de fora para dentro, com o driver real."""
        _plantar_repositorio_com_violacoes(tmp_path)
        grafo = KnowledgeGraph()

        resultado = executar_auditoria_seguranca(tmp_path, grafo_conhecimento=grafo)

        assert resultado.estado_final == "completed"

        nos_missao = grafo.nos_por_tipo(TipoNoKnowledge.MISSION)
        assert len(nos_missao) == 1
        assert nos_missao[0].ref == str(resultado.mission_id)

        nos_playbook = grafo.nos_por_tipo(TipoNoKnowledge.PLAYBOOK)
        assert any(no.ref == "auditoria-seguranca" for no in nos_playbook)

        vizinhos = grafo.get_neighbors(nos_missao[0], edge_kind=TipoAresta.USES)
        assert any(v.ref == "auditoria-seguranca" for v in vizinhos)

        # Este fluxo nao produz DecisionPoint (ver _SemConhecimentoAinda) —
        # nenhum no DECISION deve existir.
        assert grafo.nos_por_tipo(TipoNoKnowledge.DECISION) == []
