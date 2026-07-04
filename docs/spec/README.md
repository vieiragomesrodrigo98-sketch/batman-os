# Batman OS

**Engineering an Autonomous Deterministic Operating System**

*Arquitetura, Runtime, Governança e Evolução de um Sistema Cognitivo Determinístico*

> "Um sistema inteligente não é aquele que responde todas as perguntas. É aquele que reduz continuamente a quantidade de perguntas que precisam ser feitas."

---

## O que é este repositório

Este repositório é a **especificação oficial de arquitetura** do Batman OS — não um manual, não uma coleção de anotações, mas o documento canônico que qualquer engenheiro (humano ou agente) deve conseguir usar para implementar, auditar ou evoluir o sistema.

**Regra de ouro:** sempre que houver divergência entre o código em produção e este documento, o documento vence, até que uma nova ADR (Architecture Decision Record) aprove formalmente a mudança.

## Autoria

- **Autor:** Rodrigo Vieira
- **Coautor Técnico:** Claude (Anthropic)
- **Versão atual:** v0.1 (Draft) — Obra completa (Volumes I–X)

## Estrutura da obra

O livro é dividido em 10 volumes. Cada volume é um diretório neste repositório; cada capítulo é um arquivo Markdown dentro do volume.

| Volume | Título | Status |
|---|---|---|
| I | Foundation | ✅ Completo |
| II | Kernel Architecture | ✅ Completo (este commit) |
| III | Runtime | ✅ Completo (este commit) |
| IV | Capabilities | ✅ Completo (este commit) |
| V | Workflow Engine | ✅ Completo (este commit) |
| VI | Learning Engine | ✅ Completo (este commit) |
| VII | Governance | ✅ Completo (este commit) |
| VIII | Infrastructure | ✅ Completo (este commit) |
| IX | Reference Implementation | ✅ Completo (este commit) |
| X | Appendices | ✅ Completo (este commit) |

Ver [`SUMMARY.md`](./SUMMARY.md) para o índice detalhado de capítulos, e [`ADDENDA.md`](./ADDENDA.md) para propostas de extensão arquitetural que ainda não foram incorporadas aos capítulos (World Model, Goal Engine, Continuous Mission, entre outras).

## Convenções usadas na obra

- **ADRs** ficam em `NN-volume/ADR/ADR-XXXX-titulo.md`, numeração global sequencial (ADR-0001, ADR-0002, ...).
- **Diagramas** são escritos em Mermaid (renderizam nativamente em GitHub/GitLab) com fallback em ASCII quando a relação é simples.
- **Pseudocódigo** segue estilo TypeScript-like, independente de linguagem de implementação real.
- Cada capítulo termina com a seção **"Status da Implementação"**, com três colunas: *Já existe*, *Precisa refatorar*, *Ainda não existe*.
- Termos oficiais (Missão, Capability, Skill, Operador, Workflow, Playbook, Knowledge Asset) seguem a definição do [Capítulo 3 — Glossário Oficial](./01-foundation/04-terminology.md) e não podem ser usados com outro sentido em nenhum capítulo.
- **Anexos (Addenda)** ficam em `NN-volume/ADDENDA/ADD-XXXX-titulo.md`, numeração global sequencial (ADD-0001, ADD-0002, ...). Um Anexo propõe uma extensão arquitetural sem jamais editar o texto de um capítulo já certificado — nasce com status `Proposed` e só se torna vinculante para volumes futuros após aceite explícito. Ver [`ADDENDA.md`](./ADDENDA.md).

## Como contribuir com este documento

1. Nenhuma decisão arquitetural nova entra sem uma ADR.
2. Nenhum capítulo é aceito sem a seção "Status da Implementação".
3. Mudanças em terminologia exigem atualização do glossário oficial e busca por todas as ocorrências anteriores no livro.
