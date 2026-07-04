# Capítulo 36 — Glossário Consolidado

**Volume:** X — Appendices
**Status da especificação:** v0.1 (Draft)
**Depende de:** Toda a obra — este capítulo não introduz nenhum termo novo, apenas consolida

---

## 36.0 Objetivo do capítulo

Reunir, em um único lugar, todos os termos oficiais definidos ao longo dos nove volumes anteriores. Nenhuma definição aqui substitui a definição original em seu capítulo-fonte — em caso de qualquer divergência de leitura, o capítulo-fonte é a autoridade (consistente com a "regra de ouro" do `README.md`).

## 36.1 Termos fundacionais (Volume I)

| Termo | Definição resumida | Fonte |
|---|---|---|
| **Missão** | Maior unidade operacional do Batman; nada executa fora do contexto de uma Missão | Vol. I, Cap. 4 |
| **Capability** | Capacidade permanente e determinística do sistema, catalogada e versionada | Vol. I, Cap. 4; Vol. III, Cap. 11 |
| **Skill** | Conhecimento técnico especializado, usado internamente por Capabilities | Vol. I, Cap. 4; Vol. IV, Cap. 17 |
| **Operador** | Executor especializado que possui Capacidades, Ferramentas, Memória, Estado e Permissões | Vol. I, Cap. 4; Vol. IV, Cap. 15 |
| **Workflow** | Sequência determinística de execução seguida por uma Missão | Vol. I, Cap. 4 |
| **Playbook** | Estratégia operacional reutilizável da qual Workflows são instanciados | Vol. I, Cap. 4; Vol. V, Cap. 21 |
| **Knowledge Asset** | Qualquer artefato que aumenta permanentemente o conhecimento do sistema (regra, teste, Capability, Skill, Workflow, evidência, ADR, Playbook) | Vol. I, Cap. 4 |
| **Cognitive Debt** | Proporção de missões que ainda dependem de intervenção humana ou de LLM, em vez de resolução autônoma | Vol. I, Cap. 4, seção 4.9.1 |
| **Patrimônio Cognitivo** | O conjunto acumulado de Knowledge Assets do sistema ao longo do tempo | Vol. I, Cap. 4, seção 4.9.2 |

## 36.2 Termos do Kernel (Volume II)

| Termo | Definição resumida | Fonte |
|---|---|---|
| **ExecutionPlan** | Estrutura ordenada de passos gerada pelo Planning Engine a partir de um `MissionIntent` | Vol. II, Cap. 7 |
| **DecisionPoint** | Ponto de ambiguidade em um plano que exige resolução via hierarquia Knowledge → Human → LLM | Vol. II, Cap. 7, 8 |
| **RecoveryStrategy** | Mecanismo de recuperação de falha de um passo (`retry`, `compensate`, `skip-if-optional`, `escalate`) | Vol. II, Cap. 9; estendido em Vol. V, Cap. 22 (`fallback-capability`) |
| **KernelEvent** | Unidade imutável publicada no Event Bus, base do event sourcing do Kernel | Vol. II, Cap. 10 |

## 36.3 Termos do Runtime (Volume III)

| Termo | Definição resumida | Fonte |
|---|---|---|
| **CapabilityDefinition** | Registro versionado (SemVer) de uma Capability, com schemas de entrada/saída | Vol. III, Cap. 11 |
| **ExecutionResult** | Resultado de uma invocação de Operador, validado contra `outputSchema` | Vol. III, Cap. 12 |
| **OperationalRecord** | Projeção derivada de eventos, usada como evidência histórica (nunca fonte de comportamento autônomo) | Vol. III, Cap. 13 |
| **tenantId** | Campo obrigatório propagado estruturalmente por toda entidade do Kernel/Runtime | Vol. III, Cap. 14; ADR-0005 |

## 36.4 Termos da Periferia Extensível (Volume IV)

| Termo | Definição resumida | Fonte |
|---|---|---|
| **PermissionSet / SandboxPolicy** | Contrato de menor privilégio e isolamento físico de um Operador | Vol. IV, Cap. 15 |
| **CapabilityImplementation** | Artefato de implementação de uma Capability, com checklist obrigatório de certificação | Vol. IV, Cap. 16 |
| **Tool** | Binding concreto e escopado por credenciais que conecta uma Skill ao mundo externo | Vol. IV, Cap. 18 |
| **Sub-missão** | Mecanismo de delegação governada entre Operadores, via `parentMissionId` | Vol. IV, Cap. 19 |

## 36.5 Termos do Workflow Engine (Volume V)

| Termo | Definição resumida | Fonte |
|---|---|---|
| **MissionTypeDefinition** | Taxonomia de missão com criticidade, SLA e política de escalonamento | Vol. V, Cap. 20 |
| **IntentMatcher** | Condição estrutural de casamento entre um Playbook e um `MissionIntent` | Vol. V, Cap. 21 |
| **FallbackChain** | Cadeia ordenada de `RecoveryStrategy`s com degradação controlada | Vol. V, Cap. 22 |
| **PartiallyCompleted** | Estado terminal de sucesso parcial, sempre acompanhado de `DegradationRecord` | Vol. V, Cap. 22; ADR-0009 |

## 36.6 Termos do Learning Engine (Volume VI)

| Termo | Definição resumida | Fonte |
|---|---|---|
| **KnowledgeNode / KnowledgeEdge** | Nós e arestas do grafo unificado de conhecimento | Vol. VI, Cap. 23 |
| **RuleDefinition** | Regra versionada, promovida via Human Review + shadow mode | Vol. VI, Cap. 24 |
| **Shadow mode** | Validação empírica de uma regra proposta contra decisões reais, antes de ativação | Vol. VI, Cap. 24, seção 24.4; ADR-0011 |
| **WorkflowEvolutionProposal** | Proposta de inversão de fallback, fusão ou depreciação de Playbooks | Vol. VI, Cap. 25 |

## 36.7 Termos de Governança (Volume VII)

| Termo | Definição resumida | Fonte |
|---|---|---|
| **GovernanceDecision / GovernanceAlert** | Registro formal de decisão ou alarme de conformidade | Vol. VII, Cap. 27 |
| **HumanReviewRequest / HumanReviewRef** | Solicitação e referência de aprovação humana obrigatória | Vol. VII, Cap. 28 |
| **LLMEscalationPolicy** | Artefato único e versionado que consolida toda a política de uso de LLM | Vol. VII, Cap. 29 |
| **ReviewerRole** | Papel de revisor com escopo de autoridade específico (`domain-expert`, `security-reviewer`, `architecture-reviewer`, `governance-lead`) | Vol. VII, Cap. 28 |

## 36.8 Termos de Infraestrutura (Volume VIII)

| Termo | Definição resumida | Fonte |
|---|---|---|
| **SecretVaultIntegration** | Abstração de resolução de credenciais, nunca armazenadas em texto plano | Vol. VIII, Cap. 33 |
| **SupplyChainIntegrity** | Verificação de hash de artefato certificado vs. artefato em produção | Vol. VIII, Cap. 33; ADR-0015 |

## 36.9 Termos de Anexos (`ADDENDA.md`)

| Termo | Definição resumida | Status |
|---|---|---|
| **Goal** | Objetivo de alto nível, decomposto pelo Goal Engine em uma ou mais Missões | ADD-0001, `Proposed` |
| **WorldEntity / WorldModel** | Representação versionada do ambiente externo ao Batman | ADD-0002, `Proposed` |
| **Continuous Mission** | `MissionType` que gera sub-missões continuamente via `TriggerPolicy` | ADD-0005, `Proposed` |

## 36.10 Regra de precedência

Sempre que um termo aparecer neste glossário consolidado com qualquer nuance textual diferente do capítulo-fonte, **o capítulo-fonte prevalece** — este capítulo é um índice de navegação, não uma segunda definição autoritativa (mesmo padrão já aplicado ao Knowledge Graph, ADR-0010: nunca uma segunda fonte de verdade).

---

**Capítulo anterior:** [Capítulo 35 — Casos de Uso Ponta a Ponta](../09-reference-implementation/02-end-to-end-use-cases.md)
**Próximo capítulo:** [Capítulo 37 — Índice de ADRs e Anexos](./02-adr-addenda-index.md)
