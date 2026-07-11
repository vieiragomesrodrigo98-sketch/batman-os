"""Testes de wiring de `cli/auditoria_seguranca_command.py` (Fase 3 do
roadmap de plataforma, `.claude/plans/peaceful-wondering-hearth.md`,
Estágio 3.2). Prova pontuais de wiring — o cenário completo com achados
plantados fica em `tests/reference/test_security_audit_playbook_e2e.py`
(Estágio 3.4)."""

from __future__ import annotations

from pathlib import Path

from batman_os.cli.auditoria_seguranca_command import (
    _CODIGO_DEPENDENCIAS,
    _CODIGOS_REGEX,
    _carregar_spec_dependencias,
    _carregar_specs_regex,
    executar_auditoria_seguranca,
    montar_playbook,
)
from batman_os.orchestration.playbook_step_specs import ChecagemDeArquivos, RelatorioConsolidadoSpec


def test_carregar_specs_regex_encontra_todos_os_codigos() -> None:
    specs = _carregar_specs_regex()
    assert set(specs.keys()) == set(_CODIGOS_REGEX)
    for codigo, (regra, descoberta) in specs.items():
        assert regra.codigo == codigo
        assert "tipo" in descoberta


def test_carregar_spec_dependencias_encontra_dep003() -> None:
    regra, descoberta = _carregar_spec_dependencias()
    assert regra.codigo == _CODIGO_DEPENDENCIAS
    assert descoberta["tipo"] == "toml_dependencias"


class TestMontarPlaybook:
    def test_playbook_tem_7_steps_6_checagens_mais_relatorio(self, tmp_path: Path) -> None:
        playbook, especificacoes = montar_playbook(tmp_path)

        assert len(playbook.steps_template) == 7
        assert len(especificacoes) == 7

        for indice in range(6):
            assert isinstance(especificacoes[indice], ChecagemDeArquivos)
        assert isinstance(especificacoes[6], RelatorioConsolidadoSpec)

    def test_step_de_relatorio_depende_de_todas_as_checagens(self, tmp_path: Path) -> None:
        playbook, _ = montar_playbook(tmp_path)

        step_relatorio = playbook.steps_template[6]
        assert step_relatorio.depende_de_indices == [0, 1, 2, 3, 4, 5]

    def test_playbook_casa_com_intent_security_audit(self, tmp_path: Path) -> None:
        from batman_os.kernel.mission_runtime import MissionIntent

        playbook, _ = montar_playbook(tmp_path)

        assert playbook.applies_to.casa_com(MissionIntent(dados={"tipo": "security-audit"}))
        assert not playbook.applies_to.casa_com(MissionIntent(dados={"tipo": "outro"}))


def test_executar_auditoria_seguranca_repo_vazio_completa_sem_achados(tmp_path: Path) -> None:
    resultado = executar_auditoria_seguranca(tmp_path)

    assert resultado.estado_final == "completed"
    assert resultado.achados == []
    assert resultado.relatorio is not None
    assert resultado.relatorio["total_achados"] == 0
