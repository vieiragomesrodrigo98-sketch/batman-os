"""Vol. IX (Reference Implementation) — LLM Gateway real, não um Volume da
spec (mesmo status de `orchestration/`/`cli/`).

Implementa o "último recurso" da hierarquia Knowledge First -> Human Last
-> LLM Last (Vol.I Princípio 6, Vol.II Cap.8): quando o sistema roda
desatendido (cron, patrol futuro) e nem regra nem humano resolvem um
`DecisionPoint` a tempo, o LLM é consultado antes de travar.
"""

from __future__ import annotations
