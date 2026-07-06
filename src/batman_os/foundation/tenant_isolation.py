"""Vol. VIII, Cap. 32/33 — enforcement mínimo de isolamento de tenant.

Achado de auditoria fechado na Milestone 7 desta construção: `TenantId`
existe como tipo desde o Vol.III Cap.14 (ADR-0005) e todo método de leitura
de `OperationalMemory` já exige `tenant_id` como parâmetro obrigatório —
mas nada FALHAVA AUDIVELMENTE se, por algum bug futuro, uma consulta
retornasse um registro de tenant errado; a garantia dependia inteiramente
da lógica de filtro estar correta, sem nenhuma checagem independente.

Este módulo é essa segunda camada (defesa em profundidade, não substituição
do filtro na fonte): `exigir_tenant_correspondente()` é chamado sobre CADA
registro que sai de uma consulta escopada por tenant, e levanta
`IsolamentoDeTenantViolado` se o `tenant_id` do registro não bater com o
solicitado — nunca deveria disparar em uso normal; existe para transformar
um vazamento silencioso de dado entre tenants em uma falha alta e imediata.

Gap conhecido, documentado deliberadamente (não uma omissão silenciosa):
`KnowledgeGraph` (Vol.VI Cap.23) ainda não carrega `tenant_id` em
`KnowledgeNode`/`KnowledgeEdge` — adicionar isso é retrofit estrutural nos
nós/arestas já construídos na Milestone 4 (`rule_evolution.py`,
`workflow_evolution.py`, `aprendizado_para_metricas.py`), mudança mais
profunda que um helper de enforcement, fora do escopo desta Milestone.
"""

from __future__ import annotations

from batman_os.foundation.types import TenantId


class IsolamentoDeTenantViolado(Exception):
    """Vol.VIII Cap.32/33 — um registro escopado por tenant não corresponde
    ao `tenant_id` solicitado. Nunca deveria ocorrer em uso normal; existe
    para nunca deixar um vazamento de dado entre tenants passar em silêncio."""


def exigir_tenant_correspondente(esperado: TenantId, encontrado: TenantId) -> None:
    """Vol.VIII Cap.32/33 — segunda camada de enforcement sobre um registro
    já retornado por uma consulta que deveria ter filtrado por tenant."""
    if encontrado != esperado:
        raise IsolamentoDeTenantViolado(
            f"Registro pertence ao tenant '{encontrado}', mas a consulta era "
            f"escopada para '{esperado}' — isolamento de tenant violado"
        )
