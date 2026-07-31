# Monitor funcional / sintético (funcionalidades entregues ao usuário)

Requisito (Rodrigo, 2026-07-22): monitorar as funcionalidades do site **como
um todo, e principalmente as entregues ao usuário**; rodar **a cada 5
minutos**; quando algo cair, **notificar o Batman** (GovernanceAlert →
DiscordAlertSink). E o Batman OS **deve ser atualizado sempre que o site
muda**, para que os alertas reflitam a realidade.

Isto é distinto do watcher `observe` (infra: CPU/RAM/porta). Aqui é
**monitoramento sintético**: exercita a jornada do usuário e falha quando a
funcionalidade não é entregue — mesmo com CPU baixo e HTTP 200.

## 1. Manifesto de funcionalidades (a fonte da verdade)

`FeatureManifest` — declarativo, versionado no repo, **por tenant**. Cada
`FeatureCheck`:

| Campo | Significado |
|---|---|
| `id` | slug estável (ex.: `login`, `dashboard`, `lista-sinais`, `assistente-chat`) |
| `descricao` | o que o usuário faz/recebe |
| `metodo` + `caminho` | requisição (GET/POST + rota relativa à base do tenant) |
| `espera_status` | status HTTP esperado (default 200) |
| `espera_conteudo` | asserção opcional no corpo (substring/regex) — prova que a feature ENTREGA, não só responde |
| `auth` | `none` \| `sessao` (usa credencial sintética de monitor) |
| `severidade_se_cair` | CRITICAL para jornada crítica (login, dashboard), WARNING para secundária |
| `timeout_s` | teto de latência aceitável (latência acima = degradação) |
| `habilitado` | permite desligar um check sem apagá-lo |

Base do tenant (ex.: `https://exemplo.test`) + webhook Discord vêm da
config do tenant (roteamento por tenant, ADR-0005).

## 2. Execução a cada 5 minutos + notificação na queda

- **Cadência:** cron/systemd-timer no VPS chamando `batman monitor --tenant <id>`
  a cada 5 min (paridade com o modelo `batman patrol` do legado, que já roda
  por cron). Alternativa: `FunctionalMonitor.run_forever(intervalo=300)` como
  serviço. O ciclo é `run_once()` — determinístico e testável.
- **Notificação:** cada `FeatureCheck` que falha (status ≠ esperado, conteúdo
  ausente, timeout, ou down real) vira um `GovernanceAlert` com fonte
  `FEATURE_DOWN`, severidade do check, e `Evidence` com o que se esperava vs.
  o que veio (status, trecho do corpo, latência). O `GovernanceEngine.raise_alert`
  entrega via `DiscordAlertSink` (dedupe por estado já evita spam: só re-notifica
  se o estado do check mudou).
- **Recuperação:** quando um check volta a passar após ter falhado, emite um
  `GovernanceAlert` INFO de recuperação (fecha o ciclo — o operador sabe que
  voltou, sem precisar checar).

## 3. "Sempre atualizado quando o site muda" — salvaguarda de drift

Manifesto versionado no repo já força a disciplina (mudou o site → PR ao
manifesto). Mas para não depender só de disciplina, o monitor **detecta o
próprio drift**:

- **Feature removida ainda listada:** um check que passa a dar 404/410 de
  forma consistente (N ciclos) não é "site caído" — é **manifesto defasado**.
  Emite `GovernanceAlert` fonte `MANIFEST_DRIFT` (WARNING), pedindo revisão,
  em vez de alarme falso de outage.
- **Feature nova não coberta:** cross-check opcional entre o manifesto e a
  lista real de rotas do site (sitemap/OpenAPI/`/openapi.json` do FastAPI, ou
  a lista de rotas do frontend). Rota de usuário presente no site e **ausente**
  do manifesto → `MANIFEST_DRIFT` (WARNING): "há funcionalidade sem cobertura
  de monitor".
- **Selo de revisão:** o manifesto carrega `site_version`/`revisado_em`; se
  ficar velho além de um limite, um `OBSERVE_HEARTBEAT` lembra de revisar.

Assim o Batman OS **cobra** a atualização em vez de silenciosamente
monitorar uma realidade que não existe mais.

## 4. Arquitetura / restrições

- Vive em `src/batman_os/observe/functional_monitor.py` + `feature_manifest.py`
  (o manifesto como dados) — reusa `EndpointCollector`/probe HTTP do watcher
  `observe`, o `ObservabilityEngine` (latência das features vira métrica/série)
  e o caminho `GovernanceEngine.raise_alert` → `DiscordAlertSink`.
- **Não importa `batman_os.kernel`** (ADR-0012); multi-tenant (ADR-0005);
  best-effort (falha de um check nunca derruba o ciclo dos outros).
- CLI `batman monitor --tenant <id> [--manifest <path>]` roda um ciclo (para
  o cron). Novas fontes de alerta: `FEATURE_DOWN`, `FEATURE_RECOVERED`,
  `MANIFEST_DRIFT`.
- Credencial sintética de monitor (usuário dedicado só-leitura por tenant)
  para checks com `auth=sessao` — nunca credencial de usuário real; segredo
  fora do repo (env/secret store).

## Decisão de auth (Rodrigo, 2026-07-22): conta VIEWER sintética, não admin

Confirmado usar **conta viewer sintética** (não a visão admin). Motivo,
verificado no código do radar: (1) admin **exige 2FA** (`api/dependencies.py:178`)
→ não automatiza por cron; (2) admin **bypassa o plan-gating**
(`api/routers/area-f.py:348` "Admin/super_admin bypassam") → não testaria a
experiência real do usuário. A conta viewer passa pelos guards e pelo
mascaramento, então enxerga quebras que só o usuário sofre. É o que o
`FunctionalMonitor` já implementa (auth `sessao`/`sessao-prime` via env).
Rodrigo provisiona: `BATMAN_MONITOR_EXEMPLO_CPF`/`_SENHA` (viewer) e
`_PRIME_CPF`/`_PRIME_SENHA` (Prime, para o check de carteira).

## 5. Critério de aceite

(1) manifesto tipado + carregado de arquivo por tenant; (2) `run_once` sobre
um manifesto + probe fake produz os `GovernanceAlert` certos (falha,
recuperação, drift); (3) dedupe não spamma check que segue caído; (4)
cross-check de drift detecta feature removida e feature nova não coberta;
(5) CLI `batman monitor` roda um ciclo; (6) suíte verde, ruff limpo, mypy sem
erro novo. Manifesto real do exemplo.test seeded a partir da descoberta
das rotas de usuário (frontend + API).
