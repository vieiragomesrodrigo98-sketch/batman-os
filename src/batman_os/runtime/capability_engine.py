"""Vol. III, Cap. 11 — Capability Engine.

Como Capabilities são registradas, versionadas, resolvidas e descobertas — o
catálogo vivo que o Planning Engine consulta para compor planos e que o
Execution Engine invoca de fato.

Fonte da verdade: docs/spec/03-runtime/01-capability-engine.md
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from batman_os.foundation.types import CapabilityId, CapabilityRef, SkillRef
from batman_os.kernel.mission_runtime import MissionIntent

JSONSchema = dict[str, Any]


class StatusCapability(StrEnum):
    """Vol.III Cap.11, secao 11.3. `draft` (secao 11.5, diagrama de ciclo de
    vida) é um estágio pré-registro — nunca um valor armazenado no campo
    `status` de uma `CapabilityDefinition` já registrada."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class SideEffects(StrEnum):
    """Vol.III Cap.11, secao 11.3."""

    NONE = "none"
    REVERSIBLE = "reversible"
    IRREVERSIBLE = "irreversible"


class CapabilityDefinition(BaseModel):
    """Vol.III Cap.11, secao 11.3.

    `idempotent` (Vol.IV Cap.16, secao 16.5) — default `True` (toda Capability
    com `side_effects != none` deve, sempre que tecnicamente viavel, ser
    desenhada como idempotente); `False` e uma declaracao explicita de
    excecao, nunca implicita."""

    id: CapabilityId
    name: str
    version: str
    input_schema: JSONSchema = Field(default_factory=dict)
    output_schema: JSONSchema = Field(default_factory=dict)
    required_skills: list[SkillRef] = Field(default_factory=list)
    deterministic: bool
    side_effects: SideEffects
    idempotent: bool = True
    deprecated_by: CapabilityId | None = None
    status: StatusCapability = StatusCapability.ACTIVE


class RegistroInvalido(Exception):
    """Vol.III Cap.11, secao 11.7 — rejeitada no registro: mudança MAJOR sem
    `deprecatedBy` (AT-11.2), ou `deterministic: false` sem isolamento
    comprovado do LLM Gateway (viola ADR-0001, Volume I)."""


class CapabilityNaoEncontrada(Exception):
    """`resolve()`/`deprecate()`/`disable()` referenciando um (id, versão)
    nunca registrado."""


_SKILL_LLM_GATEWAY = "llm-gateway"


def _partes_versao(versao: str) -> tuple[int, int, int]:
    major, minor, patch = (versao.split(".") + ["0", "0"])[:3]
    return int(major), int(minor), int(patch)


def _e_bump_major(anterior: str, nova: str) -> bool:
    """Vol.III Cap.11, secao 11.3.1."""
    return _partes_versao(nova)[0] > _partes_versao(anterior)[0]


def _tem_skill_llm_gateway(skills: list[SkillRef]) -> bool:
    """Verificação proxy de "isolamento comprovado do LLM Gateway" (secao
    11.7) — a especificação não detalha como provar isolamento de infra em
    tempo de registro; convenção adotada aqui: toda Capability não
    determinística deve declarar a Skill `llm-gateway` entre suas
    `required_skills`, tornando a dependência explícita e auditável."""
    return any(s.skill_id == _SKILL_LLM_GATEWAY for s in skills)


class CapabilityRegistry:
    """Vol.III Cap.11, secao 11.4."""

    def __init__(self) -> None:
        self._catalogo: dict[tuple[CapabilityId, str], CapabilityDefinition] = {}
        self._motivos_desativacao: dict[tuple[CapabilityId, str], str] = {}
        self._versao_registro = 0

    def register(
        self, definicao: CapabilityDefinition, depreca: CapabilityRef | None = None
    ) -> None:
        """Vol.III Cap.11, secao 11.4. `depreca` (não nomeado explicitamente
        na assinatura da especificação) identifica qual versão anterior esta
        nova versão substitui — obrigatório quando a mudança é MAJOR
        (AT-11.2); ver nota de implementação no README sobre gaps mecânicos
        entre pseudocódigo e execução real."""
        if not definicao.deterministic and not _tem_skill_llm_gateway(definicao.required_skills):
            raise RegistroInvalido(
                f"Capability '{definicao.id}' marcada deterministic=False sem "
                f"a Skill '{_SKILL_LLM_GATEWAY}' declarada em required_skills "
                "(isolamento do LLM Gateway não comprovado — viola ADR-0001)"
            )

        anterior_ativa = self._versao_ativa_mais_recente(definicao.id)
        if anterior_ativa is not None and _e_bump_major(anterior_ativa.version, definicao.version):
            if depreca is None:
                raise RegistroInvalido(
                    f"Mudança MAJOR de '{definicao.id}' ({anterior_ativa.version} -> "
                    f"{definicao.version}) exige 'depreca' explícito apontando a "
                    "versão substituída (AT-11.2)"
                )

        self._catalogo[(definicao.id, definicao.version)] = definicao

        if depreca is not None:
            chave_antiga = (depreca.capability_id, depreca.versao)
            antiga = self._catalogo.get(chave_antiga)
            if antiga is not None:
                self._catalogo[chave_antiga] = antiga.model_copy(
                    update={"status": StatusCapability.DEPRECATED, "deprecated_by": definicao.id}
                )

        self._versao_registro += 1

    def resolve(self, ref: CapabilityRef) -> CapabilityDefinition:
        """Vol.III Cap.11, secao 11.4 — resolução exata por id+versão
        (AT-11.1: sempre retorna a mesma definição, mesmo apos o catalogo
        evoluir com novas versões nao relacionadas)."""
        chave = (ref.capability_id, ref.versao)
        if chave not in self._catalogo:
            raise CapabilityNaoEncontrada(f"{ref.capability_id}@{ref.versao}")
        return self._catalogo[chave]

    def find_candidates(self, intent: MissionIntent) -> list[CapabilityDefinition]:
        """Vol.III Cap.11, secao 11.6 (AT-11.3) — resolução determinística,
        casamento estrutural de schema, nunca "palpite semântico" via LLM.
        Deduplicado por `id`: entre versoes ativas do mesmo id, so a mais
        recente concorre (evita a Planning Engine compor dois steps para a
        "mesma" capability em versoes diferentes)."""
        mais_recente_por_id: dict[CapabilityId, CapabilityDefinition] = {}
        for definicao in self._catalogo.values():
            if definicao.status != StatusCapability.ACTIVE:
                continue
            if not self._schema_compativel(definicao, intent):
                continue
            atual = mais_recente_por_id.get(definicao.id)
            if atual is None or _partes_versao(definicao.version) > _partes_versao(atual.version):
                mais_recente_por_id[definicao.id] = definicao

        candidatos = list(mais_recente_por_id.values())
        candidatos.sort(
            key=lambda d: (self._especificidade(d, intent), _partes_versao(d.version)),
            reverse=True,
        )
        return candidatos

    def buscar_candidatos(self, intent: MissionIntent) -> list[CapabilityRef]:
        """Adaptador para o Protocol `RegistroCapacidades` (Planning Engine,
        Cap.7) — permite que este Registry seja injetado diretamente em
        `planning_engine.plan()` sem código de integração extra."""
        return [
            CapabilityRef(capability_id=d.id, versao=d.version)
            for d in self.find_candidates(intent)
        ]

    def deprecate(
        self, capability_id: CapabilityId, version: str, replaced_by: CapabilityId
    ) -> None:
        """Vol.III Cap.11, secao 11.4."""
        chave = (capability_id, version)
        definicao = self._catalogo.get(chave)
        if definicao is None:
            raise CapabilityNaoEncontrada(f"{capability_id}@{version}")
        self._catalogo[chave] = definicao.model_copy(
            update={"status": StatusCapability.DEPRECATED, "deprecated_by": replaced_by}
        )
        self._versao_registro += 1

    def disable(self, capability_id: CapabilityId, version: str, reason: str) -> None:
        """Vol.III Cap.11, secao 11.4, nota crítica — nunca é remoção física;
        continua resolvível para auditoria (`replay`, Cap.10), apenas deixa
        de ser candidata para novos planos."""
        chave = (capability_id, version)
        definicao = self._catalogo.get(chave)
        if definicao is None:
            raise CapabilityNaoEncontrada(f"{capability_id}@{version}")
        self._catalogo[chave] = definicao.model_copy(update={"status": StatusCapability.DISABLED})
        self._motivos_desativacao[chave] = reason
        self._versao_registro += 1

    def versao(self) -> str:
        """Vol.III Cap.11, secao 11.4 (`RegistryVersion`) — usado no
        `planHash` (Vol.II Cap.7) para invalidar hashes quando o catálogo
        muda."""
        return str(self._versao_registro)

    def _versao_ativa_mais_recente(
        self, capability_id: CapabilityId
    ) -> CapabilityDefinition | None:
        candidatas = [
            d
            for (cid, _versao), d in self._catalogo.items()
            if cid == capability_id and d.status == StatusCapability.ACTIVE
        ]
        if not candidatas:
            return None
        return max(candidatas, key=lambda d: _partes_versao(d.version))

    def _schema_compativel(self, definicao: CapabilityDefinition, intent: MissionIntent) -> bool:
        """Vol.III Cap.11, secao 11.6 — casamento estrutural de schema.

        Achado de auditoria (validacao final do lote Milestones 2-7 desta
        construcao): checar SO a presenca das chaves nao discrimina entre
        Capabilities com o MESMO conjunto de nomes de campo mas schemas
        semanticamente diferentes (ex.: 8 Entradas da Milestone 3 — todas
        `{tipo, caminho, conteudo, regra}` — cada uma com um `tipo:
        Literal[...]` proprio). Sem checar o VALOR de um campo `const`
        (discriminador), todas as 8 empatavam como candidatas para
        qualquer uma das 8 entradas, gerando um plano de 8 passos em vez
        de 1 (`EntradaNaoRegistrada` ao tentar invocar o passo 2+, ja que
        `scan_command.py` so registra entrada para o passo 0). Campo sem
        `const` continua exigindo so presenca da chave — comportamento
        inalterado para schemas sem discriminador (ex.: `EntradaRegexArquivo`,
        Milestone 1/2)."""
        propriedades = definicao.input_schema.get("properties")
        if not propriedades:
            return True  # sem requisitos declarados -> compativel com qualquer intent
        for chave, propriedade in propriedades.items():
            if chave not in intent.dados:
                return False
            valor_const = propriedade.get("const")
            if valor_const is not None and intent.dados[chave] != valor_const:
                return False
        return True

    def _especificidade(self, definicao: CapabilityDefinition, intent: MissionIntent) -> int:
        propriedades = definicao.input_schema.get("properties") or {}
        return sum(1 for chave in propriedades if chave in intent.dados)
