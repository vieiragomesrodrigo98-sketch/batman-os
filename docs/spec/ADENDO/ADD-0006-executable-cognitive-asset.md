# ADD-0006 — Patrimônio Cognitivo Executável (Reenquadramento)

| Campo | Valor |
|---|---|
| **Status** | Proposed |
| **Estende** | Volume I, Capítulo 4 (Definições Oficiais — conceito de Knowledge Asset) |
| **Não altera** | A definição de Knowledge Asset no Capítulo 4 permanece válida como está. Este anexo propõe um **reenquadramento de nomenclatura e ênfase**, não uma mudança de mecanismo — nenhuma estrutura de dados especificada em qualquer volume precisa mudar |
| **Princípios invocados** | Knowledge First, Learn Forever, Evolution Never Stops |

---

## 1. A observação central desta proposta

A proposta original argumenta que o Batman não deveria "aprender apenas informação", mas **comportamentos executáveis** — e sugere o termo **Patrimônio Cognitivo Executável** como conceito central do Learning Engine.

## 2. Avaliação: o mecanismo já existe; o que falta é o enquadramento

Comparando o ciclo proposto:

```
Incidente → Investigação → Hipótese → Validação → Capability → Workflow → Teste → Playbook → Métrica → Knowledge Asset
```

com o que já está especificado no Volume VI, Capítulo 26 (seção 26.2, "O ciclo completo de aprendizado operacional") e no Volume I, Capítulo 4 (seção 4.7, definição de Knowledge Asset) — **os nós são os mesmos**. A definição de Knowledge Asset já lista exclusivamente artefatos executáveis ou diretamente acionáveis: Regra, Teste, Workflow, Capability, Skill, Evidência, ADR, Playbook. Nenhum desses é "informação passiva" — uma Regra é consumida pelo Decision Engine (Vol. II, Cap. 8); um Playbook é instanciado pelo Planning Engine (Vol. II, Cap. 7). O mecanismo que a proposta pede **já é, estruturalmente, executável de ponta a ponta**.

O que genuinamente falta não é mecanismo — é **nome e ênfase explícita**. "Knowledge Asset" comunica "conhecimento registrado"; não comunica, só pelo nome, que o critério de aceitação de todo artefato é "isto muda o comportamento futuro do sistema", não "isto documenta o que aconteceu".

## 3. Mudança de nomenclatura proposta (não estrutural)

| Termo atual (Vol. I, Cap. 4) | Termo proposto | Mudança de definição? |
|---|---|---|
| Knowledge Asset | Patrimônio Cognitivo Executável | Nenhuma — mesma estrutura, mesmo conjunto de exemplos (Regra, Teste, Workflow, Capability, Skill, Evidência, ADR, Playbook) |

Esta seria uma mudança puramente de rótulo, com uma adição textual explícita ao Capítulo 4 (a ser feita, se aceita, como revisão do capítulo em uma versão futura — nunca silenciosamente):

> "Todo Patrimônio Cognitivo Executável deve, por definição, ser capaz de influenciar o comportamento de uma execução futura do sistema — nunca ser apenas um registro passivo de algo que já aconteceu. Um documento que apenas descreve um incidente, sem se conectar a uma Capability, Regra, Teste ou Playbook consultável pelo Kernel, não é, por si só, Patrimônio Cognitivo — é, no máximo, evidência de apoio a um."

## 4. Onde isso reforça (sem contradizer) decisões já tomadas

- **ADR-0004 (Volume III):** já distingue Operational Memory (registro passivo) de Knowledge Asset (comportamento ativo) — o reenquadramento proposto apenas nomeia essa distinção de forma mais direta.
- **Capítulo 26 (Volume VI), seção 26.3:** já afirma que "Operational Learning não é um componente novo de software" — o mesmo espírito se aplica aqui: este anexo não pede um componente novo, pede clareza de linguagem sobre o que já existe.

## 5. O que este anexo explicitamente não muda

- Não introduz uma nova estrutura de dados.
- Não altera o pipeline de certificação de Capability (Vol. IV, Cap. 16), Playbook (Vol. V, Cap. 21) ou Rule (Vol. VI, Cap. 24).
- Não reabre a ADR-0004 nem a ADR-0011 — apenas reforça textualmente o motivo por trás delas.

## 6. Impacto de aceitação (se aceito)

Se este anexo for aceito, o único artefato que precisaria de revisão de texto (não de estrutura) seria o próprio Capítulo 4 do Volume I, para incorporar a frase da seção 3 acima como parte da definição oficial de Knowledge Asset — a ser tratada, se e quando aceito, como uma revisão de capítulo versionada (nunca uma edição silenciosa), seguindo a mesma disciplina de versionamento que a obra já aplica a Capabilities, Playbooks e Regras.

## 7. Status da Implementação

| Já existe | Precisa refatorar | Ainda não existe |
|---|---|---|
| O mecanismo completo (Vol. I, Cap. 4; Vol. VI, Cap. 26) | Apenas o texto do Capítulo 4, se este anexo for aceito | Nada em termos de mecanismo — este anexo é puramente conceitual/textual |

---

**Para aceitar este anexo:** é o de aceitação mais simples desta leva — não requer ADR, apenas uma revisão de texto explícita e versionada do Capítulo 4, já que não introduz nenhuma mudança de comportamento do sistema, apenas de como a obra descreve um comportamento que já existe.
