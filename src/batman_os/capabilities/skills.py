"""Vol. IV, Cap. 17 — Skills.

Unidade de conhecimento especializado composável que Capabilities usam
internamente — catalogada, versionada e reaproveitada entre múltiplas
Capabilities. Uma Missão nunca invoca uma Skill diretamente (fronteira de
contrato público preservada: o mundo externo ao Kernel só enxerga
Capabilities, nunca Skills).

Fonte da verdade: docs/spec/04-capabilities/03-skills.md
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from batman_os.foundation.types import SkillId


class StatusSkill(StrEnum):
    """Vol.IV Cap.17, secao 17.3."""

    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class SkillInterface(BaseModel):
    """Vol.IV Cap.17, secao 17.3 — contrato de métodos expostos, análogo a
    uma biblioteca interna. A especificação não detalha a forma exata; modelo
    mínimo: nomes de métodos expostos por esta Skill."""

    metodos: list[str] = Field(default_factory=list)


class SkillDefinition(BaseModel):
    """Vol.IV Cap.17, secao 17.3."""

    id: SkillId
    name: str
    version: str
    interface: SkillInterface = Field(default_factory=SkillInterface)
    dependencies: list[SkillId] = Field(default_factory=list)
    status: StatusSkill = StatusSkill.ACTIVE


class CicloDeDependenciaDetectado(Exception):
    """Vol.IV Cap.17, secao 17.5 (AT-17.3) — ciclo de dependência entre
    Skills é sempre um erro de registro, nunca resolvido em runtime."""


def _partes_versao(versao: str) -> tuple[int, int, int]:
    major, minor, patch = (versao.split(".") + ["0", "0"])[:3]
    return int(major), int(minor), int(patch)


def _encontrar_ciclo(grafo: dict[SkillId, list[SkillId]]) -> list[SkillId] | None:
    """DFS com marcação de 3 cores — mesma técnica do Planning Engine
    (Vol.II Cap.7) aplicada ao grafo de dependências entre Skills."""
    cor: dict[SkillId, int] = dict.fromkeys(grafo, 0)  # 0=branco 1=cinza 2=preto
    pilha: list[SkillId] = []

    def dfs(no: SkillId) -> list[SkillId] | None:
        cor[no] = 1
        pilha.append(no)
        for vizinho in grafo.get(no, []):
            if cor.get(vizinho, 0) == 1:
                inicio = pilha.index(vizinho)
                return [*pilha[inicio:], vizinho]
            if cor.get(vizinho, 0) == 0:
                achado = dfs(vizinho)
                if achado is not None:
                    return achado
        pilha.pop()
        cor[no] = 2
        return None

    for no in grafo:
        if cor[no] == 0:
            achado = dfs(no)
            if achado is not None:
                return achado
    return None


class SkillRegistry:
    """Vol.IV Cap.17, secao 17.3-17.5."""

    def __init__(self) -> None:
        self._catalogo: dict[tuple[SkillId, str], SkillDefinition] = {}

    def register(self, definicao: SkillDefinition) -> None:
        """AT-17.3 — rejeita registro que introduza ciclo no grafo de
        dependências (considerando a versão mais recente de cada Skill já
        registrada, mais esta nova definição)."""
        grafo_tentativo = self._grafo_versoes_mais_recentes()
        grafo_tentativo[definicao.id] = definicao.dependencies

        ciclo = _encontrar_ciclo(grafo_tentativo)
        if ciclo is not None:
            raise CicloDeDependenciaDetectado(
                f"Registrar '{definicao.id}' introduziria ciclo de dependencia: {ciclo}"
            )

        self._catalogo[(definicao.id, definicao.version)] = definicao

    def resolve(self, skill_id: SkillId, version: str) -> SkillDefinition | None:
        return self._catalogo.get((skill_id, version))

    def versao_mais_recente(self, skill_id: SkillId) -> SkillDefinition | None:
        candidatas = [d for (sid, _v), d in self._catalogo.items() if sid == skill_id]
        if not candidatas:
            return None
        return max(candidatas, key=lambda d: _partes_versao(d.version))

    def esta_desativada(self, skill_id: SkillId) -> bool:
        """Vol.IV Cap.17, secao 17.6 (AT-17.1) — usado pela certificação de
        Capability (Cap.16) para rejeitar dependência em Skill `disabled`."""
        atual = self.versao_mais_recente(skill_id)
        return atual is None or atual.status == StatusSkill.DISABLED

    def _grafo_versoes_mais_recentes(self) -> dict[SkillId, list[SkillId]]:
        mais_recentes: dict[SkillId, SkillDefinition] = {}
        for (sid, _versao), definicao in self._catalogo.items():
            atual = mais_recentes.get(sid)
            if atual is None or _partes_versao(definicao.version) > _partes_versao(atual.version):
                mais_recentes[sid] = definicao
        return {sid: list(d.dependencies) for sid, d in mais_recentes.items()}
