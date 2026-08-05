"""Regressão do incidente 2026-07-29: lookaheads conjuntivos dot-all
(idioma da CRO-005) causavam backtracking catastrófico — o scan do
radar-preditivo ficou HORAS preso em `re.search` num .tsx grande.

A decomposição (`_decompor_lookaheads_conjuntivos` / `_busca_presenca`)
avalia cada corpo separadamente com semântica idêntica e custo linear.
"""

from __future__ import annotations

import time

from batman_os.capabilities.rules.regex_sobre_conteudo import (
    _busca_presenca,
    _decompor_lookaheads_conjuntivos,
)

PATTERN_CRO005 = (
    "(?=[\\s\\S]*?(?:label[^>]*\\*|>\\s*[^<]*\\*\\s*<))"
    "(?=[\\s\\S]*?<[Ii]nput\\b(?![^>]*\\brequired\\b)[^>]*>)"
)


class TestDecomposicao:
    def test_cro005_decompoe_em_dois_corpos(self) -> None:
        corpos = _decompor_lookaheads_conjuntivos(PATTERN_CRO005)
        assert corpos is not None
        assert len(corpos) == 2
        assert corpos[0] == "(?:label[^>]*\\*|>\\s*[^<]*\\*\\s*<)"
        assert corpos[1] == "<[Ii]nput\\b(?![^>]*\\brequired\\b)[^>]*>"

    def test_padrao_comum_nao_decompoe(self) -> None:
        assert _decompor_lookaheads_conjuntivos("ENABLE_REAL_TRADING\\s*=") is None

    def test_lookahead_unico_nao_decompoe(self) -> None:
        assert _decompor_lookaheads_conjuntivos("(?=[\\s\\S]*?foo)") is None

    def test_sufixo_extra_nao_decompoe(self) -> None:
        # lookaheads seguidos de corpo "de verdade" NÃO são pura conjunção
        assert _decompor_lookaheads_conjuntivos("(?=[\\s\\S]*?a)(?=[\\s\\S]*?b)c") is None

    def test_parenteses_dentro_de_classe_nao_confundem(self) -> None:
        pattern = "(?=[\\s\\S]*?[()x])(?=[\\s\\S]*?y)"
        corpos = _decompor_lookaheads_conjuntivos(pattern)
        assert corpos == ["[()x]", "y"]

    def test_escape_de_parentese_nao_confunde(self) -> None:
        pattern = "(?=[\\s\\S]*?\\(a\\))(?=[\\s\\S]*?b)"
        corpos = _decompor_lookaheads_conjuntivos(pattern)
        assert corpos == ["\\(a\\)", "b"]


class TestEquivalenciaSemantica:
    def test_dispara_quando_ambos_presentes(self) -> None:
        conteudo = '<label>Nome *</label>\n<input type="text" />'
        assert _busca_presenca(PATTERN_CRO005, conteudo, 0) is True

    def test_nao_dispara_sem_asterisco(self) -> None:
        conteudo = '<label>Nome</label>\n<input type="text" />'
        assert _busca_presenca(PATTERN_CRO005, conteudo, 0) is False

    def test_nao_dispara_quando_input_tem_required(self) -> None:
        conteudo = '<label>Nome *</label>\n<input type="text" required />'
        assert _busca_presenca(PATTERN_CRO005, conteudo, 0) is False

    def test_conteudo_vazio_nao_dispara(self) -> None:
        assert _busca_presenca(PATTERN_CRO005, "", 0) is False

    def test_padrao_nao_decomponivel_preserva_comportamento(self) -> None:
        assert _busca_presenca("foo.*bar", "xx foo yy bar zz", 0) is True
        assert _busca_presenca("foo.*bar", "xx foo yy", 0) is False


class TestPerformance:
    def test_arquivo_grande_sem_asterisco_avalia_em_menos_de_um_segundo(self) -> None:
        """O caso do incidente: .tsx grande cheio de tags, sem `*` em label —
        antes da decomposição isso re-tentava os lookaheads em cada posição
        (horas); agora são duas buscas lineares."""
        bloco = '<div className="x">texto</div>\n<input type="text" required />\n'
        conteudo = bloco * 8000  # ~500 KB
        inicio = time.perf_counter()
        resultado = _busca_presenca(PATTERN_CRO005, conteudo, 0)
        duracao = time.perf_counter() - inicio
        assert resultado is False
        assert duracao < 1.0, f"avaliação levou {duracao:.2f}s — regressão de perf"
