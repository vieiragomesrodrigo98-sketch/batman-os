"""Testes de `api/auth.py` (Fase 8 do roadmap de plataforma, `.claude/
plans/peaceful-wondering-hearth.md`, Estágio 8.1) — mecanismo isolado,
ainda não aplicado a nenhum endpoint real (ver Estágio 8.2)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from batman_os.api.app import criar_app
from batman_os.api.auth import ApiKeyStore, TenantAutenticadoDep


class TestApiKeyStore:
    def test_resolve_chave_valida_para_o_tenant_certo(self) -> None:
        store = ApiKeyStore({"acme": "chave-acme", "globex": "chave-globex"})

        assert store.resolver("chave-acme") == "acme"
        assert store.resolver("chave-globex") == "globex"

    def test_chave_desconhecida_resolve_none(self) -> None:
        store = ApiKeyStore({"acme": "chave-acme"})

        assert store.resolver("chave-que-nao-existe") is None

    def test_store_vazio_nunca_resolve_nada(self) -> None:
        store = ApiKeyStore({})

        assert store.resolver("qualquer-coisa") is None

    def test_carregar_de_env_explicito_nunca_toca_dotenv_real(self) -> None:
        store = ApiKeyStore.carregar(env={"BATMAN_API_KEYS": '{"acme": "chave-acme"}'})

        assert store.resolver("chave-acme") == "acme"

    def test_carregar_sem_variavel_retorna_store_vazio(self) -> None:
        store = ApiKeyStore.carregar(env={})

        assert store.resolver("qualquer-coisa") is None

    def test_carregar_com_variavel_vazia_retorna_store_vazio(self) -> None:
        store = ApiKeyStore.carregar(env={"BATMAN_API_KEYS": "   "})

        assert store.resolver("qualquer-coisa") is None

    def test_carregar_com_json_malformado_levanta_erro_claro(self) -> None:
        with pytest.raises(ValueError, match="BATMAN_API_KEYS"):
            ApiKeyStore.carregar(env={"BATMAN_API_KEYS": "{nao-e-json"})

    def test_carregar_com_json_que_nao_e_objeto_levanta_erro_claro(self) -> None:
        with pytest.raises(ValueError, match="BATMAN_API_KEYS"):
            ApiKeyStore.carregar(env={"BATMAN_API_KEYS": "[1, 2, 3]"})


class TestCriarAppConstroiChaveStore:
    def test_api_keys_explicito_e_usado_no_lifespan(self) -> None:
        app = criar_app(api_keys={"acme": "chave-acme"})

        with TestClient(app):
            assert app.state.chave_store.resolver("chave-acme") == "acme"

    def test_sem_api_keys_explicito_carrega_de_env_vazio_por_padrao(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BATMAN_API_KEYS", raising=False)
        app = criar_app(db_path=":memory:")

        with TestClient(app):
            assert app.state.chave_store.resolver("qualquer-coisa") is None


def _app_de_teste_com_rota_autenticada(api_keys: dict[str, str]) -> FastAPI:
    """App FastAPI mínimo, descartável, só para exercitar `TenantAutenticadoDep`
    de ponta a ponta via HTTP real — nenhum endpoint de produção usa esta
    dependency ainda neste estágio (ver Estágio 8.2)."""
    app = criar_app(api_keys=api_keys)

    @app.get("/_rota_de_teste")
    def _rota_de_teste(tenant_id: TenantAutenticadoDep) -> dict[str, str]:
        return {"tenant_id": tenant_id}

    return app


class TestDependencyDeAutenticacao:
    def test_sem_header_retorna_401(self) -> None:
        app = _app_de_teste_com_rota_autenticada({"acme": "chave-acme"})
        with TestClient(app) as client:
            resposta = client.get("/_rota_de_teste")

        assert resposta.status_code == 401
        assert resposta.headers["www-authenticate"] == "Bearer"

    def test_chave_errada_retorna_401(self) -> None:
        app = _app_de_teste_com_rota_autenticada({"acme": "chave-acme"})
        with TestClient(app) as client:
            resposta = client.get(
                "/_rota_de_teste", headers={"Authorization": "Bearer chave-errada"}
            )

        assert resposta.status_code == 401

    def test_chave_certa_resolve_o_tenant_correto(self) -> None:
        app = _app_de_teste_com_rota_autenticada({"acme": "chave-acme"})
        with TestClient(app) as client:
            resposta = client.get("/_rota_de_teste", headers={"Authorization": "Bearer chave-acme"})

        assert resposta.status_code == 200
        assert resposta.json() == {"tenant_id": "acme"}
