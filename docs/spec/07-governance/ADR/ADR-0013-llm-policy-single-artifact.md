# ADR-0013 — Política de Escalonamento a LLM como Artefato Único, Versionado e Revisável

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | VII — Governance |
| **Capítulos relacionados** | 29 (LLM Escalation) |
| **Princípios invocados** | Full Governance, Evidence First, LLM Last |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Até o Volume VII, as regras de uso de LLM estavam corretamente especificadas, mas dispersas: o limite de retentativas vivia no Decision Engine (Volume II, Cap. 8), a validação de saída no Execution Engine (Volume III, Cap. 12), e a exigência de aprovação humana para decisões irreversíveis também no Decision Engine. Regras corretas, porém fragmentadas, dificultam auditoria agregada e tornam fácil que uma mudança pontual (ex.: "só desta vez, aumentar o limite de retries") passe despercebida do ponto de vista de governança, mesmo respeitando cada regra individualmente.

## Decisão

Toda a política de uso de LLM é consolidada em um único artefato versionado, `LLMEscalationPolicy` (Cap. 29, seção 29.2), que passa pelo mesmo processo de Human Review (Cap. 28) que qualquer outro Knowledge Asset — com exigência adicional de que mudanças que **relaxem** controles (`requiresHumanCoApproval` menos restritivo, `maxRetriesPerDecisionPoint` maior, `circuitBreakerThreshold` mais tolerante) incluam evidência quantitativa extraída de `LLMUsageAudit`, não apenas justificativa qualitativa.

## Alternativas consideradas

1. **Manter os parâmetros de uso de LLM implícitos e distribuídos em cada componente, como estavam até o Volume VI** — rejeitada: dificulta auditoria agregada (não há um único lugar para perguntar "qual é a política de LLM hoje?") e facilita mudanças pontuais não intencionalmente escrutinadas como mudança de postura de governança.
2. **Consolidar em `LLMEscalationPolicy` único e versionado, com exigência de evidência quantitativa para relaxamento de controles** — **decisão aceita**.

## Consequências

**Positivas:**
- Qualquer pessoa (ou auditoria externa) pode perguntar "qual é a política vigente de uso de LLM neste sistema" e receber uma resposta única e versionada, em vez de precisar reconstruir a resposta a partir de múltiplos capítulos e implementações.
- Mudanças que relaxam controles ficam estruturalmente mais difíceis de passar despercebidas, porque exigem uma classe de evidência (`LLMUsageAudit`) que precisa ser gerada e revisada explicitamente.

**Negativas:**
- Introduz uma camada de indireção: componentes individuais (Decision Engine, Execution Engine) passam a consultar uma política externa em vez de ter parâmetros fixos embutidos — custo de engenharia adicional de integração.
- Exige que `LLMUsageAudit` (Cap. 29, seção 29.5) esteja funcionando corretamente antes que a exigência de evidência quantitativa para relaxamento de controles seja, na prática, verificável.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Toda a postura de uso de LLM torna-se um artefato único, auditável e versionado |
| Evidence First | ✅ Relaxamento de controle exige evidência quantitativa específica, não apenas justificativa textual |
| LLM Last | ✅ Reforça, em nível de política agregada, o mesmo princípio que a ADR-0001 estabeleceu em nível de arquitetura |

## Revisão futura

Válida enquanto a consolidação em uma única política não se tornar, ela mesma, um gargalo de flexibilidade legítima entre `MissionType`s com perfis de risco muito distintos — o campo `scope` (Cap. 29, seção 29.2) já permite refinamento por tipo de missão exatamente para mitigar esse risco antecipadamente; se isso se provar insuficiente, uma ADR futura pode reavaliar a granularidade de escopo, nunca reverter a exigência de versionamento e revisão em si.

---

**Voltar:** [Capítulo 29 — LLM Escalation](../03-llm-escalation.md)
