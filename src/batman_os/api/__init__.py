"""Vol.IX Cap.34 (extensão HTTP) — Fase 6 do roadmap de plataforma
(`.claude/plans/peaceful-wondering-hearth.md`).

Camada HTTP fina sobre o motor já existente (Mission Runtime→Planning→
Decision→Workflow→Execution) — nenhuma lógica de domínio nova mora
aqui, só wiring de app FastAPI e contratos JSON. A especificação de 10
volumes é deliberadamente silenciosa sobre forma de API (confirmado por
investigação direta antes de desenhar esta fase — ver o plano); duas
restrições reais vêm dela mesmo assim: todo endpoint envolve uma Missão
real (nunca uma ação avulsa, Vol.I Cap.3), e todo endpoint carrega/aplica
`tenant_id` (ADR-0005 + Vol.VIII Cap.33).
"""

from __future__ import annotations
