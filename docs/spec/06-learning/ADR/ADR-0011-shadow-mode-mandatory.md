# ADR-0011 — Shadow Mode Obrigatório antes da Ativação de Qualquer Regra

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | VI — Learning Engine |
| **Capítulos relacionados** | 24 (Rule Evolution) |
| **Princípios invocados** | Evidence First, Full Governance, Zero Cognitive Debt |
| **Data de referência** | v0.1 (Draft) |

## Contexto

A ADR-0004 (Volume III) já exige Human Review antes de qualquer promoção de conhecimento. Isso, por si só, ainda deixa uma lacuna: revisão humana avalia a *plausibilidade* de uma regra proposta com base em evidência histórica limitada (os `supportingRecords` do candidato), mas não garante que a regra generalize corretamente para casos futuros ligeiramente diferentes dos observados.

## Decisão

Toda `RuleDefinition` aprovada por Human Review passa, antes de `status: active`, por um período de **shadow mode** (Cap. 24, seção 24.4): avaliada em paralelo a decisões reais, sem influenciar o resultado, até atingir uma taxa de concordância mínima sobre um número mínimo de avaliações.

## Alternativas consideradas

1. **Ativação imediata após aprovação humana, sem validação empírica adicional** — rejeitada: risco de que uma regra plausível na revisão (baseada em uma amostra limitada) generalize mal e comece a tomar decisões incorretas de forma autônoma e silenciosa — exatamente o tipo de erro que Full Governance e Zero Cognitive Debt existem para prevenir.
2. **Validação apenas por testes sintéticos escritos pelo revisor humano** — rejeitada: testes sintéticos refletem a intuição do revisor, não necessariamente a distribuição real de casos que o Decision Engine encontrará em produção.
3. **Shadow mode com comparação contra decisões reais em produção, sem aplicar o resultado, até atingir confiança estatística mínima** — **decisão aceita**.

## Consequências

**Positivas:**
- Regras só assumem autoridade decisória real depois de demonstrarem concordância com a operação real, não apenas com a amostra que originou a proposta.
- Reduz risco de reversões custosas de regras ativas que se provam equivocadas após impactarem decisões reais.

**Negativas:**
- Atraso adicional entre aprovação humana e ativação efetiva — a redução de Cognitive Debt de uma nova regra não é imediata.
- Exige infraestrutura de avaliação paralela (Cap. 24, seção 24.4) — custo de engenharia adicional em relação a uma ativação direta.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Evidence First | ✅ A ativação de uma regra passa a exigir evidência de concordância empírica, não apenas plausibilidade histórica |
| Full Governance | ✅ Reforça o checkpoint de Human Review com uma segunda camada de validação antes de qualquer autoridade decisória real |
| Zero Cognitive Debt | ✅ Reduz o risco de que uma promoção malfeita gere, paradoxalmente, mais trabalho de correção do que economizou |

## Revisão futura

Válida até que o processo de Human Review desenvolva maturidade suficiente (histórico comprovado de baixa taxa de regras rejeitadas em shadow mode) que justifique reduzir o número mínimo de avaliações exigido para certas classes de baixo risco — nunca eliminar o shadow mode inteiramente, apenas calibrar seu rigor por classe de `DecisionPointSignature` e reversibilidade associada (Volume II, Cap. 8, seção 8.4).

---

**Voltar:** [Capítulo 24 — Rule Evolution](../02-rule-evolution.md)
