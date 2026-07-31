"""Testes da Skill AST "nó selecionado sem padrão no corpo/contexto" (Vol.IV Cap.17)."""

from __future__ import annotations

import pytest

from batman_os.capabilities.capability_contract import certificar
from batman_os.capabilities.operator import ExecutionContext
from batman_os.capabilities.rules.ast_padrao_ausente import (
    EntradaInvalida,
    avaliar_regra_ast,
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
        "seletor_tipo": "classdef",
        "seletor_include": "X",
        "seletor_exclude": None,
        "corpo_padrao": "protegido",
        "campo_estrutural": None,
        "metodos_call": [],
        "janela_linhas": 10,
        "precondicao_arquivo": None,
        "ignore_case": False,
    }
    base.update(overrides)
    return base


class TestSeletorClassDef:
    def test_dispara_quando_classe_incluida_sem_padrao_no_corpo(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooRequest:\n    id: int\n",
            "regra": _regra(seletor_include=r"Request$", corpo_padrao="protegido"),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_corpo_tem_padrao(self) -> None:
        # "protegido" precisa estar DENTRO do span sintatico do node (nao um
        # comentario apos a ultima instrucao) - ast.get_source_segment corta
        # no fim da ultima instrucao, mesmo comportamento do motor legado
        # (BT-003/COMP-001/COMP-002 usam a mesma funcao).
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooRequest:\n    protegido = True\n    id: int\n",
            "regra": _regra(seletor_include=r"Request$", corpo_padrao="protegido"),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_nome_excluido(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooResponse:\n    id: int\n",
            "regra": _regra(
                seletor_include=r"(Request|Response)$",
                seletor_exclude=r"Response$",
                corpo_padrao="protegido",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_nome_nao_bate_include(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooHelper:\n    id: int\n",
            "regra": _regra(seletor_include=r"Request$", corpo_padrao="protegido"),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_precondicao_arquivo_bloqueia_quando_ausente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooRequest:\n    id: int\n",
            "regra": _regra(
                seletor_include=r"Request$",
                corpo_padrao="protegido",
                precondicao_arquivo="BaseModel",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_precondicao_arquivo_libera_quando_presente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "from x import BaseModel\nclass FooRequest:\n    id: int\n",
            "regra": _regra(
                seletor_include=r"Request$",
                corpo_padrao="protegido",
                precondicao_arquivo="BaseModel",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1


class TestSeletorBasesExclude:
    """Achado de revisão da continuação da migração (RISK-001): suprime o
    achado se QUALQUER classe-base casar o padrão — replica "Enums e
    subclasses de outro *Sinal* herdam os campos do pai, não flagear"."""

    def test_dispara_quando_classe_nao_tem_base_excluida(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class SinalCompra:\n    ticker: str\n",
            "regra": _regra(
                seletor_include=r"Sinal",
                corpo_padrao="stop_loss|take_profit",
                seletor_bases_exclude="Enum|IntEnum|StrEnum|Sinal",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_para_subclasse_de_enum(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class SinalTipo(Enum):\n    COMPRA = 1\n",
            "regra": _regra(
                seletor_include=r"Sinal",
                corpo_padrao="stop_loss|take_profit",
                seletor_bases_exclude="Enum|IntEnum|StrEnum|Sinal",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_subclasse_de_outro_sinal(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class SinalCompraDetalhado(SinalBase):\n    ticker: str\n",
            "regra": _regra(
                seletor_include=r"Sinal",
                corpo_padrao="stop_loss|take_profit",
                seletor_bases_exclude="Enum|IntEnum|StrEnum|Sinal",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []


class TestCorpoEscopo:
    """Replica COMP-001/COMP-002: gate positivo sobre o corpo antes de
    avaliar `corpo_padrao`."""

    def test_nao_dispara_quando_escopo_nao_casa(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooModel:\n    nome_da_tabela: str\n",
            "regra": _regra(
                seletor_include=r"Model$",
                corpo_escopo=r"\bcpf\b|\bemail\b",
                corpo_padrao=r"deleted_at",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_dispara_quando_escopo_casa_e_padrao_ausente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooModel:\n    email: str\n",
            "regra": _regra(
                seletor_include=r"Model$",
                corpo_escopo=r"\bcpf\b|\bemail\b",
                corpo_padrao=r"deleted_at",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_escopo_casa_mas_padrao_presente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooModel:\n    email: str\n    deleted_at: str\n",
            "regra": _regra(
                seletor_include=r"Model$",
                corpo_escopo=r"\bcpf\b|\bemail\b",
                corpo_padrao=r"deleted_at",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []


class TestCorpoEscopoLimiteDePalavra:
    """Recalibração COMP-001 (S162, Onda 1 do Plano Cobertura Total) —
    achado real: `\\b(...)│\\b` não casa `email_address`/`user_name` porque
    `_` conta como caractere de palavra em regex — colunas PII reais
    (`UserNotificationConfigTable.email_address`) passavam batido. O novo
    `corpo_escopo` usa fronteira "não-letra" — casa através de `_`, mas
    continua SEM casar substring dentro de uma palavra maior
    (`username` não vira `name`)."""

    _ESCOPO_NOVO = r"(?<![A-Za-z])(cpf|email|nome|name|telefone|phone|endereco|address)(?![A-Za-z])"

    def test_email_address_com_underscore_agora_casa(self) -> None:
        entrada = {
            "caminho": "api/database/tables.py",
            "conteudo": (
                "class UserNotificationConfigTable(Base):\n"
                "    email_address: Mapped[str | None] = mapped_column(String(200))\n"
            ),
            "regra": _regra(
                seletor_include=r"Table$",
                corpo_escopo=self._ESCOPO_NOVO,
                corpo_padrao=r"deleted_at",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1  # sem deleted_at -> achado real

    def test_user_name_com_underscore_agora_casa(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooTable(Base):\n    user_name: Mapped[str]\n",
            "regra": _regra(
                seletor_include=r"Table$",
                corpo_escopo=self._ESCOPO_NOVO,
                corpo_padrao=r"deleted_at",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_username_concatenado_sem_underscore_nao_casa(self) -> None:
        """`username` NÃO é `name` — a fronteira "não-letra" não permite
        casar substring dentro de uma sequência contínua de letras (evita
        gerar FP novo ao consertar o gap do underscore)."""
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooTable(Base):\n    username: Mapped[str]\n",
            "regra": _regra(
                seletor_include=r"Table$",
                corpo_escopo=self._ESCOPO_NOVO,
                corpo_padrao=r"deleted_at",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_protegido_com_deleted_at_nao_dispara(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "class FooTable(Base):\n"
                "    email_address: Mapped[str]\n"
                "    deleted_at: Mapped[datetime | None]\n"
            ),
            "regra": _regra(
                seletor_include=r"Table$",
                corpo_escopo=self._ESCOPO_NOVO,
                corpo_padrao=r"deleted_at",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []


class TestIgnorarKwargLiteral:
    """Recalibração COMP-001 (S162, Onda 1 do Plano Cobertura Total) —
    achado real: `CautoPositionTable`/`CautoSnapshotTable` (zero PII) eram
    flagradas só por causa do kwarg `name="uq_..."` de `UniqueConstraint`
    dentro de `__table_args__`. `ignorar_kwarg_literal=["name"]` remove esse
    kwarg (sempre um LITERAL de string) antes de avaliar `corpo_escopo`,
    sem afetar uma coluna `name = Column(...)` de verdade (nunca um
    literal de string puro)."""

    _ESCOPO = r"(?<![A-Za-z])(cpf|email|nome|name|telefone|phone|endereco|address)(?![A-Za-z])"

    _TABELA_CAUTO_REAL = (
        "class CautoPositionTable(Base, TimestampMixin):\n"
        '    __tablename__ = "pb_cauto_positions"\n\n'
        "    id: Mapped[int] = mapped_column(primary_key=True)\n"
        '    account_id: Mapped[int] = mapped_column(ForeignKey("pb_cauto_accounts.id"))\n'
        "    signal_id: Mapped[int] = mapped_column(Integer)\n\n"
        "    __table_args__ = (\n"
        '        UniqueConstraint("account_id", "signal_id", '
        'name="uq_pb_cauto_positions_account_signal"),\n'
        "    )\n"
    )

    def test_tabela_sem_pii_com_kwarg_name_nao_dispara_com_a_flag(self) -> None:
        entrada = {
            "caminho": "api/database/tables.py",
            "conteudo": self._TABELA_CAUTO_REAL,
            "regra": _regra(
                seletor_include=r"Table$",
                corpo_escopo=self._ESCOPO,
                corpo_padrao=r"deleted_at",
                ignorar_kwarg_literal=["name"],
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_mesma_tabela_dispara_sem_a_flag_documentando_o_fp_antigo(self) -> None:
        entrada = {
            "caminho": "api/database/tables.py",
            "conteudo": self._TABELA_CAUTO_REAL,
            "regra": _regra(
                seletor_include=r"Table$", corpo_escopo=self._ESCOPO, corpo_padrao=r"deleted_at"
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_coluna_name_real_continua_disparando_com_a_flag_ligada(self) -> None:
        """A flag não pode virar um jeito de nunca mais achar PII em
        `name` — uma coluna DE VERDADE (`name = Column(...)`, nunca um
        literal de string puro) continua disparando."""
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "class ApiTokenTable(Base):\n    name: Mapped[str] = mapped_column(String(100))\n"
            ),
            "regra": _regra(
                seletor_include=r"Table$",
                corpo_escopo=self._ESCOPO,
                corpo_padrao=r"deleted_at",
                ignorar_kwarg_literal=["name"],
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1


class TestInverteDisparo:
    """Replica BT-003: disparo quando o padrao ESTA presente (campo
    controlado pelo servidor exposto num schema de request), nao ausente."""

    def test_dispara_quando_padrao_presente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooRequest:\n    created_at: str\n",
            "regra": _regra(
                seletor_include=r"Request$",
                corpo_padrao=r"created_at\s*:",
                inverte_disparo=True,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_padrao_ausente(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooRequest:\n    nome: str\n",
            "regra": _regra(
                seletor_include=r"Request$",
                corpo_padrao=r"created_at\s*:",
                inverte_disparo=True,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []


class TestCampoEstrutural:
    """Replica EH-006: modo exato via ast.AnnAssign, nao regex sobre texto."""

    def test_dispara_quando_campo_declarado_de_verdade(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooUpdate:\n    role: str\n",
            "regra": _regra(
                seletor_include=r"Update$", corpo_padrao="ignorado", campo_estrutural="role"
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_campo_so_aparece_em_comentario(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooUpdate:\n    # role: str (nao adicionar)\n    id: int\n",
            "regra": _regra(
                seletor_include=r"Update$", corpo_padrao="ignorado", campo_estrutural="role"
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []


class TestCamposEstruturaisECondicional:
    """Paridade com o EH-006 ENDURECIDO do legado (commit `2b803eca`):
    qualquer flag de privilégio da lista dispara, e `is_active` só conta
    quando o nome do schema indica um principal (User/Account/...) — em
    recurso (Coupon/Plan/Faq) é "recurso habilitado", uso legítimo (S158)."""

    @staticmethod
    def _regra_eh006() -> dict[str, object]:
        return _regra(
            seletor_include=r"(Update|Patch|Modify|Edit)$",
            corpo_padrao="ignorado",
            campos_estruturais=[
                "role",
                "is_admin",
                "is_staff",
                "is_superuser",
                "is_super_admin",
                "is_propagador",
            ],
            campo_estrutural_condicional="is_active",
            seletor_condicional="(?i)(User|Account|Member|Profile|Perfil|Conta|Usuario)",
        )

    def test_dispara_para_is_admin_em_schema_de_update(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooUpdate:\n    is_admin: bool\n",
            "regra": self._regra_eh006(),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_dispara_para_is_propagador(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooUpdate:\n    is_propagador: bool\n",
            "regra": self._regra_eh006(),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_role_continua_disparando(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class FooUpdate:\n    role: str\n",
            "regra": self._regra_eh006(),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_is_active_dispara_em_schema_de_principal(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class UserUpdate:\n    is_active: bool\n",
            "regra": self._regra_eh006(),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_is_active_nao_dispara_em_schema_de_recurso(self) -> None:
        # o falso positivo real que motivou o refino no legado:
        # FaqUpdate/CouponUpdate/PlanUpdate.is_active (S158).
        entrada = {
            "caminho": "a.py",
            "conteudo": "class CouponUpdate:\n    is_active: bool\n",
            "regra": self._regra_eh006(),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_campo_comum(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class UserUpdate:\n    nome: str\n    email: str\n",
            "regra": self._regra_eh006(),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_fora_de_schema_de_update(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "class UserResponse:\n    is_admin: bool\n",
            "regra": self._regra_eh006(),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []


class TestSeletorFunctionDef:
    def test_dispara_quando_decorator_bate_e_corpo_sem_padrao(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": ("@router.delete('/x')\ndef remover(id: int):\n    db.delete(id)\n"),
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include=r"router\.(delete|post|put)",
                corpo_padrao=r"log_action",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_corpo_tem_log_action(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "@router.delete('/x')\n"
                "def remover(id: int):\n"
                "    log_action('remover', id)\n"
                "    db.delete(id)\n"
            ),
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include=r"router\.(delete|post|put)",
                corpo_padrao=r"log_action",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_decorator_excluido_suprime_mesmo_sem_padrao_no_corpo(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": ("@router.get('/x')\ndef listar():\n    return db.query(X).all()\n"),
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include=r"router\.(get|delete|post|put)",
                seletor_exclude=r"router\.get",
                corpo_padrao=r"log_action",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_seletor_include_casa_so_no_corpo_tambem_dispara(self) -> None:
        # replica BT-002: has_admin_dep = decorator OU mencao solta no corpo
        # (require_admin usado como Depends() dentro dos parametros/corpo,
        # nao so como decorator).
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "@router.post('/x')\ndef alterar(user=Depends(require_admin)):\n    fazer_algo()\n"
            ),
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include=r"require_admin",
                corpo_padrao=r"log_action",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_seletor_so_decorator_ignora_match_solto_no_corpo(self) -> None:
        # replica BT-001: is_delete so olha decorator_list, nunca o corpo -
        # um `.delete(` dentro do corpo (ex.: chamada ao ORM) nao deve
        # selecionar a funcao se ela nao e um HANDLER de delete de verdade.
        entrada = {
            "caminho": "a.py",
            "conteudo": ("@router.post('/x')\ndef criar():\n    cache.delete(chave)\n"),
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include=r"\.delete\s*\(",
                seletor_so_decorator=True,
                corpo_padrao=r"log_action",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_seletor_so_decorator_ainda_dispara_quando_decorator_bate(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": ("@router.delete('/x')\ndef remover(id: int):\n    db.delete(id)\n"),
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include=r"\.delete\s*\(",
                seletor_so_decorator=True,
                corpo_padrao=r"log_action",
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1


class TestSeletorNomeFuncao:
    """Achado de revisão da continuação da migração (RISK-002 divergiu
    contra o `radar-preditivo` real): `seletor_include` casa contra o
    corpo/contexto inteiro da função, não especificamente contra
    `node.name` — uma função cujo CORPO apenas MENCIONA a palavra-chave
    (chamada a outra função, comentário) dispara por engano, mesmo não
    sendo ela própria a função-alvo. `seletor_nome_funcao` fecha essa
    lacuna, selecionando SÓ pelo nome."""

    def test_nao_dispara_quando_so_o_corpo_menciona_a_palavra_chave(self) -> None:
        # Caso real que causou a divergencia: uma funcao chamada
        # 'casos_similares' cujo corpo menciona 'backtest' (ex.: chama
        # outra funcao relacionada) nao deveria disparar RISK-002 - so a
        # funcao literalmente NOMEADA com 'backtest' deveria.
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "def casos_similares():\n"
                "    # usa dados de backtest para sugerir casos parecidos\n"
                "    return buscar_historico()\n"
            ),
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include="backtest",
                seletor_nome_funcao="backtest",
                corpo_padrao=r"cost|fee|spread",
                ignore_case=True,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_dispara_quando_o_nome_da_funcao_bate(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": ("def run_backtest():\n    return simular()\n"),
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include="backtest",
                seletor_nome_funcao="backtest",
                corpo_padrao=r"cost|fee|spread",
                ignore_case=True,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_nome_bate_mas_corpo_tem_o_padrao_protegido(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": ("def run_backtest():\n    return simular(fee=0.001)\n"),
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include="backtest",
                seletor_nome_funcao="backtest",
                corpo_padrao=r"cost|fee|spread",
                ignore_case=True,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []


class TestExigeDocstring:
    """Achado da continuação da migração (BA-002/DOC-001/UXR-002 — mesma
    checagem estrutural exata, 3 códigos distintos): docstring é conteúdo
    ARBITRÁRIO, regex sobre `corpo_padrao` não expressa "é uma string
    literal de verdade" — usa `ast.get_docstring` diretamente."""

    def test_dispara_quando_rota_nao_tem_docstring(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "@router.get('/x')\ndef listar():\n    return []\n",
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include=r"router\.(get|post|put|patch|delete)",
                seletor_so_decorator=True,
                exige_docstring=True,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_rota_tem_docstring(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "@router.get('/x')\ndef listar():\n    '''Lista os itens.'''\n    return []\n"
            ),
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include=r"router\.(get|post|put|patch|delete)",
                seletor_so_decorator=True,
                exige_docstring=True,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_para_funcao_que_nao_e_rota(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "def helper():\n    return 1\n",
            "regra": _regra(
                seletor_tipo="functiondef",
                seletor_include=r"router\.(get|post|put|patch|delete)",
                seletor_so_decorator=True,
                exige_docstring=True,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []


class TestSeletorCall:
    def test_dispara_quando_primeiro_arg_bate_e_janela_sem_padrao(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": ("@app.get('/admin/x')\ndef admin_x():\n    return {}\n"),
            "regra": _regra(
                seletor_tipo="call",
                seletor_include=r"/admin",
                corpo_padrao=r"require_admin|is_admin",
                metodos_call=["get", "post", "put", "delete"],
                janela_linhas=5,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert len(saida["achados"]) == 1

    def test_nao_dispara_quando_janela_tem_require_admin(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": (
                "@app.get('/admin/x')\ndef admin_x():\n    require_admin()\n    return {}\n"
            ),
            "regra": _regra(
                seletor_tipo="call",
                seletor_include=r"/admin",
                corpo_padrao=r"require_admin|is_admin",
                metodos_call=["get", "post", "put", "delete"],
                janela_linhas=5,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_nao_dispara_quando_metodo_nao_esta_na_lista(self) -> None:
        entrada = {
            "caminho": "a.py",
            "conteudo": "@app.get('/admin/x')\ndef admin_x():\n    return {}\n",
            "regra": _regra(
                seletor_tipo="call",
                seletor_include=r"/admin",
                corpo_padrao=r"require_admin",
                metodos_call=["post"],
                janela_linhas=5,
            ),
        }
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []


class TestErroDeSintaxe:
    def test_conteudo_com_erro_de_sintaxe_nao_quebra_e_retorna_vazio(self) -> None:
        entrada = {"caminho": "a.py", "conteudo": "def (:\n", "regra": _regra()}
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []

    def test_conteudo_none_retorna_vazio(self) -> None:
        entrada = {"caminho": "a.py", "conteudo": None, "regra": _regra()}
        saida = avaliar_regra_ast(entrada, _contexto())
        assert saida["achados"] == []


class TestEntradaInvalida:
    def test_levanta_excecao_sem_campo_regra(self) -> None:
        with pytest.raises(EntradaInvalida):
            avaliar_regra_ast({"caminho": "a.py"}, _contexto())


class TestCertificacao:
    def test_implementacao_real_passa_na_certificacao(self) -> None:
        impl = construir_implementacao()
        contexto = _contexto()
        entrada_idempotencia = {
            "caminho": "a.py",
            "conteudo": "class X:\n    pass\n",
            "regra": _regra(),
        }
        definicao_certificada = certificar(
            impl,
            entrada_para_teste_idempotencia=entrada_idempotencia,
            contexto_para_teste_idempotencia=contexto,
        )
        assert definicao_certificada.status == StatusCapability.ACTIVE
