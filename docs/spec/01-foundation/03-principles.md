# Capítulo 3 — Princípios Fundamentais

**Volume:** I — Foundation
**Status da especificação:** v0.1 (Draft)

---

## 3.0 Objetivo do capítulo

Converter a filosofia do Capítulo 2 em dez princípios operacionais, testáveis e citáveis. A partir deste capítulo, **qualquer ADR nos volumes seguintes deve declarar explicitamente com quais princípios está alinhada** e, se violar algum, justificar a excepcionalidade.

## 3.1 Tabela-resumo

| # | Princípio | Uma frase |
|---|---|---|
| 1 | Knowledge First | Conhecimento vale mais que respostas |
| 2 | Determinism First | Mesma entrada, mesma saída, sempre |
| 3 | Evidence First | Nenhuma conclusão sem evidência rastreável |
| 4 | Mission Driven | Nada é executado fora do contexto de uma Missão |
| 5 | Human Last | Humanos são escassos; só entram quando o conhecimento se esgota |
| 6 | LLM Last | LLMs são conhecimento externo, não dependência central |
| 7 | Learn Forever | Toda intervenção externa gera patrimônio permanente |
| 8 | Zero Cognitive Debt | Repetição de problema = falha sistêmica a corrigir |
| 9 | Full Governance | Toda decisão é auditável |
| 10 | Evolution Never Stops | O sistema nunca é "versão final" |

## 3.2 Princípio 1 — Knowledge First

**Definição:** o objetivo primário de qualquer componente do Batman nunca é "produzir uma resposta". É produzir ou consumir conhecimento estruturado.

**Teste de conformidade:** um componente está alinhado com este princípio se, ao ser removido, o sistema perde uma capacidade *permanente* — e não apenas deixa de responder a uma pergunta pontual.

## 3.3 Princípio 2 — Determinism First

**Definição:** dada uma entrada e um estado de conhecimento fixos, o Batman deve produzir exatamente a mesma saída, em qualquer execução, em qualquer momento.

**Consequência arquitetural:** qualquer componente que introduza aleatoriedade (incluindo chamadas a LLMs) deve ser posicionado na periferia do sistema, isolado por um contrato determinístico (entrada validada → saída validada), nunca no caminho crítico de decisão.

## 3.4 Princípio 3 — Evidence First

**Definição:** nenhuma decisão, classificação ou ação do Batman existe sem evidência associada. Toda decisão deve carregar:

- **Origem** (qual regra, Capability ou fonte gerou a decisão)
- **Evidências** (dados concretos que sustentam a decisão)
- **Confiança** (grau de certeza, quando aplicável)
- **Histórico** (decisões anteriores relacionadas)

**Teste de conformidade:** se uma decisão não pode responder "por quê" com uma cadeia verificável de evidências, ela não está em conformidade — independentemente de estar correta.

## 3.5 Princípio 4 — Mission Driven

**Definição:** o Batman nunca executa comandos isolados. Toda atividade pertence a uma **Missão** (ver glossário, Capítulo 4).

**Consequência arquitetural:** não existe endpoint ou interface que aceite uma ação "solta" sem contexto de missão — mesmo ações triviais são modeladas como missões de baixo custo, o que garante rastreabilidade uniforme.

## 3.6 Princípio 5 — Human Last

**Definição:** especialistas humanos são o recurso mais escasso e mais caro do sistema. Devem ser acionados **apenas** quando todo o conhecimento estruturado existente (regras, Capabilities, Playbooks) já foi consultado e esgotado.

**Não é** um princípio anti-humano — é o oposto: cada acionamento humano é tratado como valioso o suficiente para ser transformado permanentemente em patrimônio (ver Princípio 7), exatamente por ser escasso.

## 3.7 Princípio 6 — LLM Last

**Definição:** modelos de linguagem representam uma forma de conhecimento externo, generalista e probabilístico. Devem ser consultados apenas quando as capacidades determinísticas internas do Batman se esgotarem.

**Distinção crítica com o Princípio 5:** LLM Last não compete com Human Last — na hierarquia de escalonamento (ver Capítulo 2, seção 2.5), a ordem específica entre consultar um humano ou um LLM depende do custo, latência e reversibilidade da decisão em questão, e será formalizada no Decision Engine (Volume II). O que é inegociável é que **nenhum dos dois é o mecanismo primário de operação**.

## 3.8 Princípio 7 — Learn Forever

**Definição:** toda vez que uma intervenção humana ou de LLM resolve um problema, essa resolução deve, por padrão, gerar ao menos um Knowledge Asset permanente (regra, teste, Capability, Workflow, ADR ou Playbook).

**Teste de conformidade:** se uma intervenção externa termina sem produzir nenhum artefato rastreável, o processo está fora de especificação — independente de o problema ter sido "resolvido" no sentido imediato.

## 3.9 Princípio 8 — Zero Cognitive Debt

**Definição:** a recorrência de um mesmo problema, exigindo a mesma classe de intervenção humana ou de LLM mais de uma vez, é tratada como **falha do sistema**, não como comportamento esperado.

Este princípio introduz a métrica formal de **Cognitive Debt** (ver Capítulo 3 — Definições, seção 4.x, e detalhamento completo no Volume VII — Governance), que mede a proporção de missões resolvidas sem intervenção externa.

## 3.10 Princípio 9 — Full Governance

**Definição:** toda decisão tomada pelo Batman — autônoma, humana ou assistida por LLM — deve ser auditável: quem/o quê decidiu, com base em quê, e quando.

**Consequência arquitetural:** governança não é um módulo adicional opcional; é um requisito transversal que atravessa Kernel, Runtime e Learning Engine (formalizado no Volume VII).

## 3.11 Princípio 10 — Evolution Never Stops

**Definição:** o Batman nunca atinge um estado "completo". A arquitetura deve assumir, desde o desenho, que novas Capabilities, regras e Workflows serão adicionados continuamente, sem exigir reescrita do núcleo.

**Consequência arquitetural:** interfaces entre Kernel e Capabilities devem ser estáveis e versionadas (ver ADRs do Volume II); a evolução acontece na periferia extensível, não no núcleo.

## 3.12 Interações entre princípios

Os dez princípios não são independentes — alguns criam tensão produtiva que o sistema deve resolver explicitamente, nunca implicitamente:

- **Determinism First vs. LLM Last:** resolvido isolando o LLM como componente periférico com contrato de entrada/saída validado (Princípio 2, seção 3.3).
- **Human Last vs. Learn Forever:** resolvido garantindo que toda escalação humana, mesmo sendo rara, seja tratada como evento de alto valor de aquisição de conhecimento, não como incômodo a minimizar sem registro.
- **Zero Cognitive Debt vs. Evolution Never Stops:** o objetivo não é "zero Cognitive Debt de uma vez" — é uma trajetória monotonicamente decrescente ao longo do tempo, à medida que o sistema evolui (Princípio 10).

## 3.13 Status da Implementação

| Já existe | Precisa refatorar | Ainda não existe |
|---|---|---|
| Os dez princípios, formalizados e testáveis | — | Mecanismos concretos de enforcement (linter arquitetural que verifica conformidade de ADRs com os princípios) — candidato a Volume VII |

---

**Capítulo anterior:** [Capítulo 2 — A Filosofia Batman](./02-philosophy.md)
**Próximo capítulo:** [Capítulo 4 — Definições Oficiais (Glossário)](./04-terminology.md)
