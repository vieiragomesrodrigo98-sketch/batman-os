"""Testes do `feature_manifest` — avaliador de asercao (substring + caminho
JSON com == / exists / is / in / [*] / [0]) e carga tipada do manifesto por
tenant. Zero rede."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from batman_os.foundation.types import TenantId
from batman_os.governance.governance_engine import SeveridadeAlerta
from batman_os.observe.feature_manifest import (
    AsercaoInvalida,
    AuthConfig,
    FeatureCheck,
    FeatureManifest,
    avaliar_conteudo,
    caminho_manifesto,
    carregar_manifesto,
)


class TestAvaliadorAsercao:
    def test_none_sempre_passa(self) -> None:
        assert avaliar_conteudo(None, "qualquer coisa").ok

    def test_substring_presente_e_ausente(self) -> None:
        assert avaliar_conteudo("contains:Radar Preditivo", "<h1>Radar Preditivo</h1>").ok
        r = avaliar_conteudo("contains:Entrar", "<h1>Login</h1>")
        assert not r.ok
        assert "Entrar" in r.detalhe

    def test_multiplas_clausulas_and(self) -> None:
        corpo = '{"status": "ok", "service": "radar", "timestamp": 123}'
        asercao = '.status == "ok" && .service exists && .timestamp exists'
        assert avaliar_conteudo(asercao, corpo).ok
        r = avaliar_conteudo('.status == "ok" && .serviceX exists', corpo)
        assert not r.ok

    def test_igualdade_string_e_numero_e_bool(self) -> None:
        assert avaliar_conteudo(".n == 3", '{"n": 3}').ok
        assert avaliar_conteudo(".flag == true", '{"flag": true}').ok
        assert not avaliar_conteudo(".n == 3", '{"n": 4}').ok

    def test_tipos_array_string_number_nonempty(self) -> None:
        assert avaliar_conteudo(". is array", "[]").ok
        assert avaliar_conteudo(".s is string", '{"s": "x"}').ok
        assert avaliar_conteudo(".n is number", '{"n": 1.5}').ok
        # bool NAO conta como number
        assert not avaliar_conteudo(".n is number", '{"n": true}').ok
        assert avaliar_conteudo(".lista is nonempty", '{"lista": [1]}').ok
        assert not avaliar_conteudo(".lista is nonempty", '{"lista": []}').ok

    def test_wildcard_vacuo_quando_array_vazio(self) -> None:
        # "array; se nao-vazio, cada item tem asset_ticker" — vazio e valido
        assert avaliar_conteudo(". is array && [*].asset_ticker exists", "[]").ok

    def test_wildcard_exige_campo_em_cada_elemento(self) -> None:
        ok = avaliar_conteudo("[*].asset_ticker exists", '[{"asset_ticker": "PETR4"}]')
        assert ok.ok
        ruim = avaliar_conteudo("[*].asset_ticker exists", '[{"asset_ticker": "PETR4"}, {"x": 1}]')
        assert not ruim.ok

    def test_indice_posicional(self) -> None:
        assert avaliar_conteudo("[0].name is string", '[{"name": "Free"}]').ok
        assert not avaliar_conteudo("[0].name is string", "[]").ok

    def test_operador_in_conjunto(self) -> None:
        asercao = '.sentimento in ["favoravel", "cauteloso", "alerta"]'
        assert avaliar_conteudo(asercao, '{"sentimento": "cauteloso"}').ok
        assert not avaliar_conteudo(asercao, '{"sentimento": "eufórico"}').ok

    def test_corpo_nao_json_falha_clausula_json(self) -> None:
        r = avaliar_conteudo('.status == "ok"', "<html>not json</html>")
        assert not r.ok
        assert "JSON" in r.detalhe

    def test_asercao_malformada_levanta(self) -> None:
        with pytest.raises(AsercaoInvalida):
            avaliar_conteudo(".campo operador-invalido", '{"campo": 1}')
        with pytest.raises(AsercaoInvalida):
            avaliar_conteudo("[abc].x exists", "{}")


class TestCargaDoManifesto:
    def test_carrega_exemplo_seed(self) -> None:
        manifest = carregar_manifesto(caminho_manifesto("exemplo"))
        assert manifest.tenant_id == TenantId("exemplo")
        assert manifest.base_url == "https://exemplo.test"
        assert len(manifest.features) == 12
        ids = {f.id for f in manifest.features}
        assert {"syn-api-health", "syn-auth-login", "syn-recurso-d-chat"} <= ids
        # credenciais NUNCA no arquivo — so nomes de variaveis de ambiente
        assert manifest.auth.env_credencial.startswith("BATMAN_MONITOR_")
        # tolerancias do seed
        carteira = next(f for f in manifest.features if f.id == "syn-recurso-c-exposicao")
        assert set(carteira.status_tolerados) == {403, 503}
        chat = next(f for f in manifest.features if f.id == "syn-recurso-d-chat")
        assert chat.status_tolerados == [429]

    def test_base_url_sem_barra_final(self) -> None:
        manifest = FeatureManifest(
            tenant_id=TenantId("t"),
            base_url="https://x/",
            revisado_em="2026-07-22",
            auth=AuthConfig(endpoint="/login", env_credencial="A", env_senha="B"),
            features=[],
        )
        assert manifest.base_url == "https://x"

    def test_manifesto_com_asercao_invalida_falha_ao_carregar(self, tmp_path: Path) -> None:
        dados = {
            "tenant_id": "t",
            "base_url": "https://x",
            "revisado_em": "2026-07-22",
            "auth": {"endpoint": "/login", "env_credencial": "A", "env_senha": "B"},
            "features": [
                {
                    "id": "ruim",
                    "descricao": "asercao quebrada",
                    "caminho": "/x",
                    "espera_conteudo": ".campo ??? invalido",
                    "severidade_se_cair": "warning",
                    "timeout_s": 5,
                }
            ],
        }
        arq = tmp_path / "ruim.json"
        arq.write_text(json.dumps(dados), encoding="utf-8")
        with pytest.raises(AsercaoInvalida):
            carregar_manifesto(arq)

    def test_default_habilitado_e_metodo(self) -> None:
        check = FeatureCheck(
            id="x",
            descricao="d",
            caminho="/x",
            severidade_se_cair=SeveridadeAlerta.INFO,
            timeout_s=5,
        )
        assert check.habilitado is True
        assert check.metodo == "GET"
        assert check.auth == "none"
