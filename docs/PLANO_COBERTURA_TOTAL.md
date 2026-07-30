# Plano — Cobertura Total: agentes para onde o Batman OS é cego

> Ordem do DEV (2026-07-30, S162 do radar): "criar agentes para atuar onde o
> Batman OS é cego — a ideia é o Batman OS cobrir tudo."
> Contexto: hoje o Batman cobre CÓDIGO ESTÁTICO (282 specs), roda ruff/pytest
> como regras-subprocesso, e opera monitor (*/5) + observe na VPS. Três
> incidentes recentes provam as cegueiras: (a) menu cortado a 100% passou por
> tudo (ninguém renderiza); (b) pipeline de 29/07 terminou `status: error`
> (fsim_mark_to_market) e o monitor deu 0 alertas; (c) 44 HIGH do 1º scan
> completo incluem falsos positivos estruturais (QA-RUN trata timeout como
> suite quebrada).

## Princípio de arquitetura

Todo agente novo é uma **capability no padrão existente** (subprocess/checagem
→ achado com severidade + fingerprint + inbox + Discord). Nada de framework
novo: o Mission Runtime, o inbox e o monitor já são o chassi. "LLM Last"
permanece — todos os agentes abaixo são determinísticos.

## As 8 cegueiras e seus agentes

| # | Cegueira (prova) | Agente/capability | Como funciona | Esforço |
|---|---|---|---|---|
| 1 | **Renderizado/visual** (menu cortado) | `qa-visual` (card BATMAN_QAVIS01 já aberto) | Roda os specs Playwright do repo-alvo (viewports 1366/1920/mobile + jornadas da ARVORE_JORNADAS) contra o STAGING pós-deploy; spec quebrado = achado. Conta de teste isenta já existe | M |
| 2 | **Saúde dos dados em produção** (pipeline error sem alerta) | `dados-sentinela` | No monitor da VPS: lê `update_log.jsonl` (status≠ok = HIGH), idade máxima por fonte vs cadência esperada do crontab (prices_20y ≤1 pregão, price_bars cripto ≤5min, events ≤1h...), contagem de linhas anômala (queda >20% dia a dia). Tabela fonte→cadência declarada em spec | S |
| 3 | **Segurança dinâmica** (sweeps ethical-hacker eram manuais) | `sec-dinamica` | Matriz rota→role esperada (gerada dos routers FastAPI): para cada rota, prova no STAGING que 401/403 corretos valem (sem auth, com viewer, com admin); rate-limits respondem 429; headers de segurança presentes. Achado por divergência | M |
| 4 | **Performance/orçamentos** (bundle cresce sem teto) | `perf-orcamento` | Regras de budget: tamanho do bundle (dist/*.js ≤ teto por chunk), p95 de latência dos endpoints core no staging (curl temporizado ×N), tempo de build. Estourou o teto = achado MEDIUM/HIGH | S |
| 5 | **Verdade Única** (CLAUDE.md já ficou defasado dezenas de sessões) | `gov-verdade` | Checa: STATE.md "Atualizado em" vs data do último commit (>7 dias de gap com commits = achado); cards `deploy_realizado` cujo ID não aparece em nenhum commit; ADRs referenciando arquivos inexistentes; contagem do backlog vs declarada no STATE | S |
| 6 | **Guarda estatística do MIE** (kill switch é do próprio radar — falta o vigia independente) | `ml-guarda` | Lê `MIE3_*/MIE_CRIPTO_*.json`, ledgers e o placar semanal: Brier do forward divergindo >20% do treino = achado; kill switch a 1 desvio de disparar = aviso; manifest do modelo em PRD com hash ≠ do repo = HIGH (integridade) | S |
| 7 | **Supply chain** (react-router com CVE moderate conhecido) | `dep-auditoria` | `npm audit --json` + `pip-audit` como regras-subprocesso; severidade mapeada (critical/high = achado HIGH); allowlist de aceites com validade (deferimento expira) | S |
| 8 | **Infra/continuidade** (PRD já ficou 1 mês sem backup; crontab aplicado à mão) | `infra-sentinela` | No monitor: idade do último backup (>24h = HIGH) + `PRAGMA integrity_check` do backup + **drill mensal de restauração** em arquivo temp; drift do crontab VIVO vs `infra/crontab.prod` do commit deployado; validade do certificado TLS (<15 dias = HIGH); disco (<15% livre) | M |

## Consertos de regras existentes (entram junto)

- **QA-RUN**: timeout do pytest interno ≠ "suite quebrada" — rodar com
  `--changed`-scope ou marcar `timeout` como achado próprio LOW ("suite lenta
  demais p/ o scanner"), nunca HIGH falso (lição dos 44 HIGH).
- **SD-*/FUI-***: reescopar para arquivos de PÁGINA (não API clients) — 20 dos
  44 HIGH eram isso.
- Windows `communicate()` pós-kill: matar árvore com `taskkill /T` (bomba
  latente documentada no diagnóstico de 2026-07-30).

## Ordem de execução (3 ondas)

1. **Onda 1 — o que dói agora (S+1)**: `dados-sentinela` (o pipeline error de
   ontem não pode se repetir mudo) · `qa-visual` v1 (nav-overflow.spec já
   existe como payload) · consertos QA-RUN/SD/FUI (fecha a triagem dos 44).
2. **Onda 2 — segurança e continuidade (S+2)**: `sec-dinamica` ·
   `infra-sentinela` (backup drill + crontab drift + TLS) · `dep-auditoria`.
3. **Onda 3 — governança e ML (S+3)**: `gov-verdade` · `ml-guarda` ·
   integração CI (fecha `GOV_BATMANOS_GATE01` — o scan volta ao CI com
   `--changed` no PR e completo no merge).

Cada onda = pacotes fechados no batman-os com a suíte dele (1.418 testes)
verde, no português da casa, e specs novas com prova de fogo própria (regra
nova nasce com teste de falso positivo).

## Critério de "coberto tudo"

O Batman OS enxerga as 6 dimensões: código (estático) · execução (testes) ·
tela (renderizado) · dados (frescor/integridade) · perímetro (segurança
dinâmica/infra) · verdade (docs=código=backlog). Um incidente que escape das
6 vira, por doutrina, uma regra nova na dimensão que falhou — o sistema
aprende por incidente, nunca repete cegueira.
