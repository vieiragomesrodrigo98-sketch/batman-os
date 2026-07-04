# ADR-0009 — Sucesso Parcial como Estado de Primeira Classe

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | V — Workflow Engine |
| **Capítulos relacionados** | 22 (Estratégias de Recuperação e Fallback) |
| **Princípios invocados** | Evidence First, Zero Cognitive Debt |
| **Data de referência** | v0.1 (Draft) |

## Contexto

O modelo original de estados da Missão (Volume II, Cap. 6) contemplava apenas `Completed` ou `Failed` como estados terminais de execução bem-sucedida ou não. Na prática operacional, muitas missões atingem seu objetivo central mesmo quando passos periféricos e não-críticos degradam (ex.: notificação de sucesso falha, mas o rollback em si foi bem-sucedido). Tratar isso como `Failed` seria impreciso e geraria ruído desnecessário em métricas e alarmes; tratar como `Completed` sem registro esconderia degradações reais que merecem acompanhamento.

## Decisão

Introduz-se `PartiallyCompleted` como estado terminal de primeira classe na máquina de estados da Missão (Cap. 22, seção 22.4.1), sempre acompanhado de um ou mais `DegradationRecord`s explícitos, nunca implícito ou inferido a posteriori.

## Alternativas consideradas

1. **Manter apenas `Completed`/`Failed`, tratando qualquer degradação de passo não-crítico como `Failed`** — rejeitada: gera alarmes desproporcionais e mascara a distinção real entre "a missão não atingiu seu objetivo" e "a missão atingiu seu objetivo com efeitos colaterais menores não resolvidos".
2. **Tratar degradações apenas como metadado dentro de `Completed`, sem novo estado** — rejeitada: reduz a visibilidade da degradação nos KPIs e no Scheduler/Governance, que tratam `Completed` uniformemente como sucesso pleno.
3. **Novo estado `PartiallyCompleted` com `DegradationRecord`s obrigatórios** — **decisão aceita**.

## Consequências

**Positivas:**
- KPIs e alarmes podem distinguir com precisão missões plenamente bem-sucedidas de missões com degradação tolerada, sem gerar ruído de falso-negativo em nenhuma das duas direções.
- `DegradationRecord`s com `impact: "requires-follow-up"` alimentam diretamente candidatos de Cognitive Debt (Cap. 22, seção 22.5), fechando o ciclo entre execução real e aprendizado (Volume VI).

**Negativas:**
- Adiciona um estado a mais na máquina de estados do Mission Runtime, exigindo atualização de todo consumidor que assumia apenas dois estados terminais de sucesso/falha (retrocompatibilidade a ser tratada explicitamente na implementação de referência, Volume IX).
- Exige disciplina de design de Playbook para declarar corretamente quais passos toleram `partial-success` (Cap. 22, seção 22.4) — declaração incorreta poderia mascarar falhas reais como degradação tolerável.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Evidence First | ✅ Toda ocorrência de `PartiallyCompleted` exige evidência explícita (`DegradationRecord`) |
| Zero Cognitive Debt | ✅ Degradações recorrentes tornam-se sinal direto e estruturado para o Learning Engine, acelerando a correção da causa raiz |

## Revisão futura

Válida enquanto a distinção entre sucesso pleno e parcial continuar sendo operacionalmente relevante. Se, no futuro, todo passo não-crítico for eliminado do catálogo de Playbooks (hipótese improvável dado que Evolution Never Stops implica crescimento contínuo de composição), esta ADR poderia ser revisitada.

---

**Voltar:** [Capítulo 22 — Estratégias de Recuperação e Fallback](../03-recovery-fallback-strategies.md)
