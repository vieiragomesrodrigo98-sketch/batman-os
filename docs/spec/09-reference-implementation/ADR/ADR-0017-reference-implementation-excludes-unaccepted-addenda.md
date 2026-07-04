# ADR-0017 — Implementação de Referência Constrói Apenas a Especificação Aceita

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | IX — Reference Implementation |
| **Capítulos relacionados** | 34 (Implementação de Referência, seção 34.7); Volume VIII, Cap. 32, seção 32.4 |
| **Princípios invocados** | Full Governance, Evolution Never Stops |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Os Anexos (`ADDENDA.md`) documentam propostas arquiteturais coerentes e bem especificadas (World Model, Goal Engine, Continuous Mission, entre outras), mas nenhuma delas passou pelo processo de aceite formal descrito no Volume VII, Capítulo 27, seção 27.6. Há uma tentação natural de, ao construir a implementação de referência, já incluir essas propostas "porque fazem sentido e já estão bem descritas" — especialmente quando o autor da especificação e o autor da implementação são a mesma pessoa ou equipe.

## Decisão

O roteiro de fases da implementação de referência (Cap. 34) constrói exclusivamente os 33 capítulos e 15 ADRs já `Accepted` por definição de fazerem parte do corpo principal da obra. Nenhum Anexo é incorporado a nenhuma fase, mesmo informalmente, sem uma `GovernanceDecision` registrada (Vol. VII, Cap. 27, AT-27.3). Código exploratório relacionado a Anexos vive exclusivamente em `addenda/` (Vol. VIII, Cap. 32, seção 32.4), fora das fases descritas neste volume.

## Alternativas consideradas

1. **Incluir Anexos bem especificados diretamente no roteiro de fases, por conveniência de já estarem documentados** — rejeitada: isso tornaria o processo de aceite formal (Cap. 27) uma formalidade pós-fato, em vez de um checkpoint real — exatamente o padrão que a própria obra criticou na avaliação do ADD-0003 (rejeitado) e reforçou na ADR-0011 (shadow mode obrigatório mesmo após aprovação humana).
2. **Implementação de referência constrói estritamente o que já foi aceito, com Anexos isolados em `addenda/` até aceite formal** — **decisão aceita**.

## Consequências

**Positivas:**
- Mantém a integridade do próprio processo de governança descrito no Volume VII — "aceitar" um Anexo continua significando algo, mesmo quando tecnicamente seria mais rápido simplesmente construí-lo.
- Qualquer pessoa auditando a implementação de referência sabe, sem ambiguidade, que tudo fora de `addenda/` corresponde à especificação formalmente aceita.

**Negativas:**
- Propostas genuinamente boas (como o World Model) ficam sem implementação plena até passarem por um processo formal, mesmo que a evidência técnica já esteja disponível — um custo de velocidade deliberadamente aceito em nome de integridade de processo.
- Exige disciplina para não "vazar" código de `addenda/` para as fases principais antes do aceite formal — mitigado estruturalmente pelo linter de dependências já especificado (Vol. VIII, Cap. 32, AT-32.1).

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Nenhuma mudança arquitetural entra em produção sem o checkpoint que a própria obra formalizou |
| Evolution Never Stops | ✅ Anexos continuam sendo o caminho legítimo de evolução — este ADR não os rejeita, apenas preserva a integridade do processo pelo qual evoluem |

## Revisão futura

Válida enquanto o Volume VII continuar sendo o processo vigente de aceite arquitetural. Se o processo de Human Review (Cap. 28) evoluir para incluir um caminho de aceite mais rápido para Anexos de baixo risco (ex.: ADD-0004, que já foi avaliado como o de aceitação mais simples da leva original), isso deveria ser formalizado como uma atualização ao próprio Capítulo 27 — nunca como uma exceção informal na implementação de referência.

---

**Voltar:** [Capítulo 34 — Implementação de Referência do Batman OS](../01-reference-implementation.md)
