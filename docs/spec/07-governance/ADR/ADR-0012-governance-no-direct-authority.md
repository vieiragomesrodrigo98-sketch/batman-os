# ADR-0012 — Governance Engine sem Autoridade Executiva Direta sobre o Kernel

| Campo | Valor |
|---|---|
| **Status** | Accepted |
| **Volume** | VII — Governance |
| **Capítulos relacionados** | 27 (Governance Engine) |
| **Princípios invocados** | Full Governance, Determinism First |
| **Data de referência** | v0.1 (Draft) |

## Contexto

Um Governance Engine com poder de agir diretamente sobre o Kernel (pausar um Operador, suspender uma Capability, reverter uma regra) pareceria, à primeira vista, mais eficiente para conter incidentes rapidamente. Mas isso recriaria, em um componente novo, exatamente o risco que a ADR-0004 (Volume III) já identificou e rejeitou para a Operational Memory: uma camada de observação com poder de mutação direta remove o próprio checkpoint de revisão que justifica sua existência.

## Decisão

O Governance Engine tem autoridade apenas para **levantar alertas e abrir solicitações de Human Review** (Cap. 27, seção 27.7). Toda ação de mutação real sobre o Kernel ou Runtime (quarentena de Operador, depreciação de Capability, suspensão de regra) continua sendo executada exclusivamente pelos mecanismos já especificados em cada volume correspondente — nunca por uma chamada direta originada do Governance Engine.

## Alternativas consideradas

1. **Governance Engine com poder de execução direta (kill switch automático) para incidentes de severidade `critical`** — rejeitada: mesmo para incidentes graves, uma ação automática de contenção sem revisão humana pode causar dano operacional próprio (ex.: quarentenar um Operador crítico com base em um falso-positivo do próprio Governance Engine) — o remédio se tornaria uma nova superfície de risco não auditada da mesma forma que as demais decisões do sistema.
2. **Governance Engine estritamente observacional, com toda mutação passando por Human Review ou pelos mecanismos de enforcement já existentes (`healthCheck`, certificação, depreciação)** — **decisão aceita**.

## Consequências

**Positivas:**
- Nenhum componente novo do sistema ganha um caminho de mutação direta sobre o Kernel que não passe pelos processos já auditados de cada volume — preserva a garantia de que existe um número finito e bem conhecido de formas de o comportamento do sistema mudar.
- Um incidente de configuração ou bug no próprio Governance Engine não pode, por construção, causar uma ação destrutiva direta no Kernel.

**Negativas:**
- Tempo de resposta a incidentes graves depende da disponibilidade de Human Review (Cap. 28) — não há contenção automática instantânea para casos de severidade `critical`.
- Exige que o backlog de Human Review tenha capacidade de resposta rápida o suficiente para incidentes críticos, o que é, em si, monitorado como um KPI de governança (Cap. 27, seção 27.10) — a mitigação do risco de lentidão é visibilidade, não automação de contenção.

## Conformidade com princípios

| Princípio | Conformidade |
|---|---|
| Full Governance | ✅ Nenhuma mutação de comportamento contorna o processo de revisão já estabelecido em cada volume |
| Determinism First | ✅ O Governance Engine não introduz um caminho adicional e paralelo de mudança de comportamento do Kernel |

## Revisão futura

Uma futura ADR poderia introduzir uma exceção estreita e explicitamente escopada — por exemplo, um "modo de contenção temporária automática" limitado a isolar tráfego de um único Operador claramente identificado como comprometido, com reversão automática e obrigatória em janela curta, sujeito a Human Review retroativa imediata — mas isso exigiria evidência concreta de que o SLA de Human Review é estruturalmente insuficiente para os incidentes reais observados, nunca uma decisão de conveniência antecipada.

---

**Voltar:** [Capítulo 27 — Governance Engine](../01-governance-engine.md)
