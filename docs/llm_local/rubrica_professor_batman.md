# Rubrica do Professor — Dataset do LLM Local do Batman OS (F1, 2026-07-21)

O professor (Claude) rotula a **decisão operacional correta ex-ante** para um
DecisionPoint de governança: dado apenas o achado e seu contexto (`dados`),
qual das opções fechadas um operador experiente escolheria — sem re-auditar o
código, sem opinar sobre gosto. O professor não decide "se o achado é bonito";
decide **o que fazer com ele agora**. A confiança faz parte do rótulo: um gold
com `confidence` mal calibrada ensina o aluno a escalar na hora errada — e o
gatilho de fallback local→Anthropic em produção é exatamente o estrato de
confiança (`LLM_LOCAL_MIN_CONFIDENCE`).

Formato de saída: **exatamente** o JSON de `RespostaLlmCandidata`
(`opcao{id, descricao}`, `confidence`, `evidencia_bruta`) com `opcao.id`
restrito às opções fornecidas no ponto. Nunca inventar opção.

## Campos do gabarito

- **`opcao.id`** — enum canônico deste dataset:
  - `remediar` — o achado é um verdadeiro positivo acionável: a remediação
    descrita (ou óbvia pela regra) deve ser aplicada. É o default quando o
    achado é substantivo e o projeto não documentou exceção.
  - `suprimir-fp` — o padrão detectado NÃO se aplica a este projeto/contexto:
    convenção local resolve o risco de outro jeito, ou a regra disparou em
    código que não tem o problema. Supressão é por fingerprint e permanente —
    só escolher com evidência clara no próprio contexto.
  - `adiar` — verdadeiro positivo, mas com justificativa operacional para não
    agir agora (débito deliberado, dependência externa, item rastreado em
    backlog, área congelada). Adiar exige uma razão nomeável; "não estou a
    fim" não é razão.
  - `escalar-humano` — o contexto fornecido não permite decidir entre as
    outras opções com confiança ≥ 0.6. Escolher esta opção é uma decisão de
    primeira classe, não uma derrota.
- **`confidence`** — certeza na opção ESCOLHIDA (0.0–1.0):
  - `0.90+` — fato operacional inequívoco no contexto (ex.: o próprio `dados`
    diz que o item está em backlog com razão registrada → `adiar` 0.95).
  - `0.75–0.89` — padrão forte, leitura direta do achado.
  - Regra de troca: se a melhor opção técnica (`remediar`/`suprimir-fp`/
    `adiar`) ficaria abaixo de **0.60**, NÃO a emita — mude para
    `escalar-humano` e dê a confiança da meta-decisão (tipicamente 0.7–0.9).
    O aluno precisa aprender a "saber quando não sabe".
- **`evidencia_bruta`** — 1 a 3 frases apontando o FATO decisivo (campo do
  contexto, convenção, razão do adiamento). Curta por design: tokens de saída
  custam latência de CPU no aluno. Não reescrever a remediação inteira.

## Armadilhas catalogadas (usar nos gabaritos)

1. **Convenção local vence a regra genérica.** Regra detecta padrão que o
   projeto resolve por outro mecanismo documentado no contexto →
   `suprimir-fp`. Sem evidência da convenção no contexto → `escalar-humano`,
   nunca supressão "no palpite".
2. **Débito deliberado ≠ achado novo.** Contexto menciona decisão registrada,
   item de backlog ou `reason` de adiamento → `adiar` com confiança alta;
   rotular `remediar` aqui ensina o aluno a brigar com decisão já tomada.
3. **Reincidência agrava.** Contexto indica regressão/reincidência (achado já
   resolvido que voltou) → `remediar` com confiança alta; nunca `adiar` de
   novo — adiamento repetido é o anti-padrão GOVDEBT que o Batman existe para
   impedir.
4. **Severidade dramática não muda a substância.** Título alarmista com
   descrição trivial (ou vice-versa): decidir pela descrição/causa, não pelo
   adjetivo. Se título e descrição se contradizem → `escalar-humano`.
5. **Contexto vago é bloqueante.** `descricao` sem arquivo/linha/fato
   verificável e sem `causa` → `escalar-humano` (armadilha nº 1 de um modelo
   3B é preencher lacuna com imaginação; o gold nunca deve premiar isso).
6. **Supressão é exceção, não atalho.** Na dúvida entre `suprimir-fp` e
   qualquer outra opção, `suprimir-fp` perde — falso negativo permanente custa
   mais caro que uma remediação desnecessária.

## O que o dataset de treino consome disto

- `opcao.id` → métrica principal de promoção (acurácia ≥ 90% no holdout;
  ≤ 3 p.p. abaixo do Haiku no mesmo conjunto).
- `confidence` → calibração por estrato: acurácia ≥ 95% no estrato
  `confidence ≥ 0.75` (é só esse estrato que vira decisão local sem fallback);
  exemplos `escalar-humano` ensinam o desvio barato ANTES do fallback pago.
- `evidencia_bruta` → sem métrica própria; mantida curta para limitar tokens
  de saída (latência p95 em CPU ≤ `LLM_LOCAL_TIMEOUT` − 20%).
- Exemplos onde professor e fato operacional divergem (Fonte A vs Fonte B no
  mesmo fingerprint) valem auditoria manual — são os "exemplos difíceis" que
  entram no gold humano (~100).
