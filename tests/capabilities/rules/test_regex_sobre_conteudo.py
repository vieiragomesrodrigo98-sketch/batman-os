"""Testes da Capability genérica 'regex sobre conteúdo de arquivo' (Vol.IV Cap.16)."""

from __future__ import annotations

import hashlib

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.regex_sobre_conteudo import (
    EntradaInvalida,
    avaliar_regra_regex,
    construir_implementacao,
)
from batman_os.foundation.types import MissionId, StepId, TenantId, agora
from batman_os.runtime.capability_engine import StatusCapability


def _contexto() -> ExecutionContext:
    return ExecutionContext(
        mission_id=MissionId("m-1"),
        tenant_id=TenantId("t-1"),
        step_id=StepId("s-1"),
        deadline=agora(),
    )


def _regra(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "codigo": "TEST-001",
        "agente": "teste",
        "severidade": "high",
        "categoria": "cat",
        "titulo": "titulo",
        "causa": "causa",
        "remediacao": "remediacao",
        "modo": "presenca",
        "pattern": None,
        "pattern_mitigacao": None,
        "pattern_escopo": None,
        "ignore_case": False,
    }
    base.update(overrides)
    return base


class TestIgnorarComentarios:
    """Recalibração EH-002 (S162, Onda 1 do Plano Cobertura Total): achado
    real do 1º scan completo do radar-preditivo — `api/routers/checkout.py:
    43,96` são comentários DEFENSIVOS documentando o próprio fix ("nunca
    ecoar str(exc)"), não código violador. `ignorar_comentarios=True`
    (opt-in por spec, default False preserva 100% do comportamento
    anterior) remove `#...` antes de avaliar o pattern."""

    _TRECHO_REAL_CHECKOUT = (
        "def _provider_ou_503():\n"
        "    try:\n"
        "        return get_payment_provider()\n"
        "    except PaymentProviderIndisponivelError as exc:\n"
        "        # Mensagem FIXA — nunca ecoar str(exc) na resposta (exposição de internals).\n"
        "        raise HTTPException(\n"
        "            status_code=503,\n"
        '            detail="Pagamento ainda não configurado — tente novamente mais tarde.",\n'
        "        ) from exc\n"
    )

    def test_comentario_descrevendo_o_fix_nao_dispara_com_flag_ligada(self) -> None:
        entrada = {
            "caminho": "api/routers/checkout.py",
            "conteudo": self._TRECHO_REAL_CHECKOUT,
            "regra": _regra(
                modo="presenca", pattern=r"str\(exc\)", ignorar_comentarios=True
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []

    def test_mesmo_trecho_dispara_sem_a_flag_documentando_o_bug_antigo(self) -> None:
        """Prova de que a flag é o mecanismo real do fix — sem ela (default
        False), o mesmo comentário ainda dispara (comportamento antigo
        preservado para specs que não optarem por `ignorar_comentarios`)."""
        entrada = {
            "caminho": "api/routers/checkout.py",
            "conteudo": self._TRECHO_REAL_CHECKOUT,
            "regra": _regra(modo="presenca", pattern=r"str\(exc\)"),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_codigo_real_fora_de_comentario_continua_disparando(self) -> None:
        """A flag não pode virar uma forma de nunca mais detectar EH-002 —
        `str(exc)` em código de VERDADE (fora de comentário) continua
        disparando mesmo com `ignorar_comentarios=True`."""
        entrada = {
            "caminho": "api/routers/algo.py",
            "conteudo": "raise HTTPException(status_code=500, detail=str(exc))",
            "regra": _regra(
                modo="presenca", pattern=r"str\(exc\)", ignorar_comentarios=True
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_arquivo_ausente_com_flag_ligada_nao_quebra(self) -> None:
        entrada = {
            "caminho": "api/routers/nao_existe.py",
            "conteudo": None,
            "regra": _regra(
                modo="presenca", pattern=r"str\(exc\)", ignorar_comentarios=True
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []


class TestModoPresenca:
    def test_dispara_quando_pattern_presente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "SECRET_KEY = 'x'",
            "regra": _regra(modo="presenca", pattern="SECRET_KEY"),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_pattern_ausente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "nada aqui",
            "regra": _regra(modo="presenca", pattern="SECRET_KEY"),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_arquivo_ausente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": None,
            "regra": _regra(modo="presenca", pattern="SECRET_KEY"),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []


class TestModoAusencia:
    def test_dispara_quando_pattern_ausente(self) -> None:
        entrada = {
            "caminho": ".env.production.example",
            "conteudo": "OUTRA_VAR=1",
            "regra": _regra(modo="ausencia", pattern="ENABLE_REAL_TRADING=false"),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_pattern_presente(self) -> None:
        entrada = {
            "caminho": ".env.production.example",
            "conteudo": "ENABLE_REAL_TRADING=false",
            "regra": _regra(modo="ausencia", pattern="ENABLE_REAL_TRADING=false"),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_arquivo_ausente_vps002(self) -> None:
        """VPS-002: se o arquivo nem existe, a regra retorna cedo (sem achado)."""
        entrada = {
            "caminho": ".env.production.example",
            "conteudo": None,
            "regra": _regra(modo="ausencia", pattern="ENABLE_REAL_TRADING=false"),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []


class TestModoAusenciaComEscopo:
    """NS-002: só exige o padrão quando o escopo (ssl_certificate) já existe."""

    def test_dispara_quando_escopo_presente_e_padrao_ausente(self) -> None:
        entrada = {
            "caminho": "nginx.conf",
            "conteudo": "ssl_certificate /etc/x.pem;",
            "regra": _regra(
                modo="ausencia",
                pattern="Strict-Transport-Security",
                pattern_escopo="ssl_certificate",
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_escopo_ausente(self) -> None:
        entrada = {
            "caminho": "nginx.conf",
            "conteudo": "server { listen 80; }",
            "regra": _regra(
                modo="ausencia",
                pattern="Strict-Transport-Security",
                pattern_escopo="ssl_certificate",
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_escopo_e_padrao_presentes(self) -> None:
        entrada = {
            "caminho": "nginx.conf",
            "conteudo": "ssl_certificate /etc/x.pem;\nStrict-Transport-Security max-age=1;",
            "regra": _regra(
                modo="ausencia",
                pattern="Strict-Transport-Security",
                pattern_escopo="ssl_certificate",
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []


class TestModoArquivoAusente:
    def test_dispara_quando_conteudo_none(self) -> None:
        entrada = {
            "caminho": ".env.production.example",
            "conteudo": None,
            "regra": _regra(modo="arquivo-ausente"),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_conteudo_presente(self) -> None:
        entrada = {
            "caminho": ".env.production.example",
            "conteudo": "",
            "regra": _regra(modo="arquivo-ausente"),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []


class TestModoArquivoPresente:
    def test_dispara_quando_conteudo_presente(self) -> None:
        entrada = {"caminho": ".env", "conteudo": "X=1", "regra": _regra(modo="arquivo-presente")}
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_conteudo_none(self) -> None:
        entrada = {"caminho": ".env", "conteudo": None, "regra": _regra(modo="arquivo-presente")}
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []


class TestModoPresencaSemMitigacao:
    """VPS-013: porta admin exposta (presenca) sem restrição de IP (mitigacao)."""

    def test_dispara_quando_padrao_presente_e_mitigacao_ausente(self) -> None:
        entrada = {
            "caminho": "firewall.sh",
            "conteudo": "allow 5050",
            "regra": _regra(
                modo="presenca-sem-mitigacao",
                pattern=r"\b(5050|5555|15672)\b",
                pattern_mitigacao=r"from\s+[\d.]+|restrict",
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_mitigacao_presente(self) -> None:
        entrada = {
            "caminho": "firewall.sh",
            "conteudo": "allow 5050 from 10.0.0.1",
            "regra": _regra(
                modo="presenca-sem-mitigacao",
                pattern=r"\b(5050|5555|15672)\b",
                pattern_mitigacao=r"from\s+[\d.]+|restrict",
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_padrao_ausente(self) -> None:
        entrada = {
            "caminho": "firewall.sh",
            "conteudo": "allow 22",
            "regra": _regra(
                modo="presenca-sem-mitigacao",
                pattern=r"\b(5050|5555|15672)\b",
                pattern_mitigacao=r"from\s+[\d.]+|restrict",
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []


class TestCondicoesAdicionais:
    """DEVOPS-003: .env presente E .gitignore sem '.env' -> achado."""

    def test_dispara_quando_todas_as_condicoes_batem(self) -> None:
        entrada = {
            "caminho": ".env",
            "conteudo": "X=1",
            "regra": _regra(codigo="DEVOPS-003", modo="arquivo-presente"),
            "condicoes_adicionais": [
                {
                    "caminho": ".gitignore",
                    "conteudo": "node_modules/\n",
                    "checar": "ausencia",
                    "pattern": r"\.env",
                }
            ],
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_gitignore_ja_cobre(self) -> None:
        entrada = {
            "caminho": ".env",
            "conteudo": "X=1",
            "regra": _regra(codigo="DEVOPS-003", modo="arquivo-presente"),
            "condicoes_adicionais": [
                {
                    "caminho": ".gitignore",
                    "conteudo": ".env\n",
                    "checar": "ausencia",
                    "pattern": r"\.env",
                }
            ],
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []

    def test_dispara_quando_gitignore_ausente_tambem_conta_como_ausencia(self) -> None:
        """Replica o comportamento original de EnvNoRepo: gitignore inexistente
        nao protege .env. A camada de descoberta (cli/descoberta_arquivos.py)
        representa 'arquivo ausente, mas conta como sem protecao' passando
        conteudo="" em vez de None (ver docstring de _condicao_simples_satisfeita)."""
        entrada = {
            "caminho": ".env",
            "conteudo": "X=1",
            "regra": _regra(codigo="DEVOPS-003", modo="arquivo-presente"),
            "condicoes_adicionais": [
                {"caminho": ".gitignore", "conteudo": "", "checar": "ausencia", "pattern": r"\.env"}
            ],
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_de002_nenhum_dos_3_caminhos_existe(self) -> None:
        entrada = {
            "caminho": "alembic",
            "conteudo": None,
            "regra": _regra(codigo="DE-002", modo="arquivo-ausente"),
            "condicoes_adicionais": [
                {"caminho": "migrations", "conteudo": None, "checar": "arquivo-ausente"},
                {"caminho": "alembic.ini", "conteudo": None, "checar": "arquivo-ausente"},
            ],
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_de002_nao_dispara_se_migrations_existe(self) -> None:
        entrada = {
            "caminho": "alembic",
            "conteudo": None,
            "regra": _regra(codigo="DE-002", modo="arquivo-ausente"),
            "condicoes_adicionais": [
                {"caminho": "migrations", "conteudo": "", "checar": "arquivo-ausente"},
                {"caminho": "alembic.ini", "conteudo": None, "checar": "arquivo-ausente"},
            ],
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []


class TestFingerprint:
    def test_reproduz_formula_do_motor_legado(self) -> None:
        entrada = {
            "caminho": "a\\b\\app.py",
            "conteudo": "SECRET_KEY = 'x'",
            "regra": _regra(
                codigo="TEST-001", agente="teste", categoria="cat", pattern="SECRET_KEY"
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        esperado = hashlib.sha1(b"teste|cat|a/b/app.py|TEST-001|").hexdigest()
        assert saida["achados"][0]["fingerprint"] == esperado


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_regra(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_regra_regex({"caminho": "a.py"}, _contexto())


class TestFiltroDeInclusao:
    """Achado da continuação da migração (LEGAL-004/PD-003/RISK-005/
    UXR-005): filtro de INCLUSÃO por nome de arquivo ou caminho — a
    camada de descoberta só suporta exclusão, então esse filtro roda no
    próprio handler."""

    def test_pattern_nome_arquivo_incluir_bloqueia_arquivo_sem_match(self) -> None:
        entrada = {
            "caminho": "frontend/src/pages/Home.tsx",
            "conteudo": "sem disclaimer aqui",
            "regra": _regra(
                modo="ausencia",
                pattern="disclaimer",
                pattern_nome_arquivo_incluir="modal|dialog",
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []

    def test_pattern_nome_arquivo_incluir_permite_arquivo_com_match(self) -> None:
        entrada = {
            "caminho": "frontend/src/components/ModalConfirm.tsx",
            "conteudo": "nada relevante aqui",
            "regra": _regra(
                modo="ausencia",
                pattern="disclaimer",
                pattern_nome_arquivo_incluir="modal|dialog",
                ignore_case=True,
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_pattern_caminho_incluir_bloqueia_caminho_sem_match(self) -> None:
        entrada = {
            "caminho": "frontend/src/pages/Dashboard.tsx",
            "conteudo": "nada relevante aqui",
            "regra": _regra(
                modo="ausencia",
                pattern="disclaimer",
                pattern_caminho_incluir="simulac|carteira",
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert saida["achados"] == []

    def test_pattern_caminho_incluir_permite_caminho_com_match(self) -> None:
        entrada = {
            "caminho": "frontend/src/pages/Simulacao.tsx",
            "conteudo": "nada relevante aqui",
            "regra": _regra(
                modo="ausencia",
                pattern="disclaimer",
                pattern_caminho_incluir="simulac|carteira",
                ignore_case=True,
            ),
        }
        saida = avaliar_regra_regex(entrada, _contexto())
        assert len(saida["achados"]) == 1


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = {
            "caminho": "a.py",
            "conteudo": "x",
            "regra": _regra(modo="arquivo-presente"),
        }
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
