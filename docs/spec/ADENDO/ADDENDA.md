# ADDENDA — Índice de Anexos

Este documento indexa todos os **Anexos (Addenda)** da obra: propostas de extensão arquitetural que **nunca alteram o texto original de nenhum capítulo já certificado**. Um anexo é sempre um documento novo, versionado, que se conecta a um ou mais capítulos existentes por referência — nunca por edição.

## Por que anexos, e não edição direta

A obra já estabelece, desde o Volume II (ADR-0003, Event Sourcing) e reforça no Volume V (Rule Evolution, Workflow Evolution) e no Volume VI (Knowledge Graph como projeção derivada), que **conhecimento nunca reescreve o passado — apenas acrescenta uma nova camada auditável sobre ele**. Aplicar esse mesmo princípio ao processo de escrita deste livro é consistente com a própria filosofia do Batman OS: a especificação evolui do mesmo jeito que o sistema que ela descreve evolui.

## Ciclo de vida de um Anexo

Espelhando o Capítulo 16 (certificação de Capability) e o Capítulo 24 (Rule Evolution), todo Anexo nasce com status **`Proposed`** — nunca `Accepted` diretamente. Um Anexo só se torna parte vinculante da especificação (ou seja, algo que capítulos futuros devem respeitar como já decidido) após passar por revisão explícita — o equivalente, no processo real de escrita desta obra, à Human Review que o próprio Volume VII formaliza.

| Status | Significado |
|---|---|
| `Proposed` | Anexo escrito e coerente com a arquitetura existente, aguardando validação/aceite explícito antes de influenciar volumes futuros |
| `Accepted` | Validado; capítulos futuros podem e devem referenciá-lo como parte estável da arquitetura |
| `Superseded` | Substituído por uma versão posterior do mesmo anexo ou incorporado formalmente a um capítulo em uma revisão futura do volume |
| `Rejected` | Avaliado e descartado, mantido apenas para registro histórico da decisão (Evidence First) |

## Índice

| ID | Título | Estende | Status |
|---|---|---|---|
| [ADD-0001](./02-kernel/ADDENDA/ADD-0001-goal-engine.md) | Goal Engine | Volume II, antes do Cap. 6 (Mission Runtime) | `Proposed` |
| [ADD-0002](./03-runtime/ADDENDA/ADD-0002-world-model.md) | World Model | Volume III; consultado pelo Volume II, Cap. 7 (Planning Engine) | `Proposed` |
| [ADD-0003](./03-runtime/ADDENDA/ADD-0003-operational-memory-inference-rejected.md) | Operational Memory ativa (inferência autônoma) | Volume III, Cap. 13 | `Rejected` (registrado para histórico) |
| [ADD-0004](./04-capabilities/ADDENDA/ADD-0004-cognitive-roles-extension.md) | Papéis Cognitivos (extensão do Scheduler via cooperação) | Volume IV, Cap. 19 (Cooperação entre Operadores) | `Proposed` |
| [ADD-0005](./05-workflow/ADDENDA/ADD-0005-continuous-mission.md) | Continuous Mission (Patrol / Curiosidade) | Volume V, Cap. 20 (Missões: Modelagem Formal) | `Proposed` |
| [ADD-0006](./01-foundation/ADDENDA/ADD-0006-executable-cognitive-asset.md) | Patrimônio Cognitivo Executável (reenquadramento) | Volume I, Cap. 4 (Definições Oficiais) | `Proposed` |

## Regra de leitura

Nenhum capítulo numerado (1–26) neste repositório deve ser lido como desatualizado por causa de um anexo `Proposed` — ele continua sendo a especificação vigente até que o anexo correspondente seja aceito. Anexos `Proposed` são material de discussão arquitetural rigorosa, não uma segunda versão silenciosa do capítulo que estendem.

---

**Ver também:** [SUMMARY.md](./SUMMARY.md) — índice dos capítulos e ADRs da obra principal.
