"""Testes do loader dos specs da Skill AST (`ast_padrao_ausente_loader.py`,
Milestone 3 + continuação da migração)."""

from __future__ import annotations

from batman_os.capabilities.rules.ast_padrao_ausente import RegraAstSpec, SeletorTipo
from batman_os.capabilities.rules.ast_padrao_ausente_loader import carregar_especificacoes_ast
from batman_os.capabilities.rules.lote_01 import carregar_lote_01
from batman_os.capabilities.rules.lote_02 import carregar_lote_02

_TIPOS_DESCOBERTA_VALIDOS = {"arquivo_fixo", "arvore", "glob"}
_CODIGOS_ESPERADOS = {
    "BT-001",
    "BT-002",
    "BT-003",
    "COMP-001",
    "COMP-002",
    "EH-004",
    "EH-006",
    "DE-006",
    "RISK-002",
    "QA-010",
    "RISK-001",
    "BA-002",
    "DOC-001",
    "UXR-002",
}


class TestCarregarEspecificacoesAst:
    def test_carrega_os_codigos_confirmados(self) -> None:
        specs = carregar_especificacoes_ast()

        codigos = {item["regra"].codigo for item in specs}
        assert codigos == _CODIGOS_ESPERADOS

    def test_toda_regra_e_uma_regraastspec_valida(self) -> None:
        specs = carregar_especificacoes_ast()

        for item in specs:
            assert isinstance(item["regra"], RegraAstSpec)
            assert item["regra"].seletor_tipo in SeletorTipo

    def test_toda_descoberta_tem_tipo_reconhecido(self) -> None:
        specs = carregar_especificacoes_ast()

        for item in specs:
            assert item["descoberta"]["tipo"] in _TIPOS_DESCOBERTA_VALIDOS

    def test_eh006_cobre_flags_de_privilegio_e_is_active_condicional(self) -> None:
        # paridade com o legado endurecido (commit `2b803eca`): antes só
        # `role`; agora todas as flags de privilégio + is_active condicional
        # a schema de principal.
        specs = carregar_especificacoes_ast()

        [eh006] = [item["regra"] for item in specs if item["regra"].codigo == "EH-006"]
        assert set(eh006.campos_estruturais) == {
            "role",
            "is_admin",
            "is_staff",
            "is_superuser",
            "is_super_admin",
            "is_propagador",
        }
        assert eh006.campo_estrutural_condicional == "is_active"
        assert eh006.seletor_condicional == "(?i)(User|Account|Member|Profile|Perfil|Conta|Usuario)"

    def test_sem_codigos_duplicados(self) -> None:
        specs = carregar_especificacoes_ast()

        codigos = [item["regra"].codigo for item in specs]
        assert len(codigos) == len(set(codigos))

    def test_nao_repete_nenhum_codigo_ja_migrado_nos_lotes_regex(self) -> None:
        codigos_regex = {item["regra"].codigo for item in carregar_lote_01() + carregar_lote_02()}
        codigos_ast = {item["regra"].codigo for item in carregar_especificacoes_ast()}

        assert codigos_regex.isdisjoint(codigos_ast)
