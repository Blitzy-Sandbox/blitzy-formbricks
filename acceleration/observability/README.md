# Observability — Reused vs Added

This directory hosts the **observability scaffolding** for the Development
Acceleration Analysis pipeline. It satisfies AAP Rule 1 by shipping
structured logging, a metrics manifest, health and readiness checks, and a
self-contained dashboard template alongside the initial implementation rather
than as a follow-up artifact.

This file documents two things:

1. What observability **already exists in the Formbricks application** and is
   therefore reused as a reference.
2. What observability this analysis pipeline **adds** for its own batch-process
   needs, and why each addition was scoped the way it was.

The file is the single place that records the boundary between the two
stacks. The companion decision log
([`acceleration/decision-log.md`](../decision-log.md)) carries the row-level
rationale for each non-trivial choice; this README focuses on **what was
reused** and **what was added**, with cross-references to the decision rows.

---

## 1. TL;DR — Reused vs Added

The table below maps every Rule 1 concern (logging, tracing, metrics endpoint,
exception capture, health and readiness, dashboard, sampler config) to a
reused artifact in the Formbricks application and to a new artifact in this
folder. Each cell points to a real path; no row is hypothetical.

| Concern | Reused from Formbricks app | Added by Acceleration pipeline |
|---------|-----------------------------|---------------------------------|
| Structured logging | `@formbricks/logger` workspace package at [`packages/logger/`](../../packages/logger/) (Pino-based, used by `apps/web` and other workspaces) | [`logger.py`](./logger.py) — Python stdlib `logging` with a JSON formatter and run-scoped correlation IDs |
| Distributed tracing | OpenTelemetry SDK `0.211.0` in [`apps/web/instrumentation-node.ts`](../../apps/web/instrumentation-node.ts) (OTLP trace and metric exporters, Prometheus exporter, Prisma instrumentation, runtime-node metrics) | Degenerate single-process trace: per-script span timing with `run_id` as the trace root, emitted as log lines from `logger.py` |
| Metrics endpoint | Prometheus exporter wired by [`apps/web/instrumentation-node.ts`](../../apps/web/instrumentation-node.ts) and scraped via [`apps/web/prometheus.yml`](../../apps/web/prometheus.yml) at `host.docker.internal:9464/metrics` | Static [`metrics.json`](./metrics.json) manifest — no live HTTP surface, no scrape target; the pipeline is a batch process |
| Error and exception capture | Sentry Next.js `10.5.0` in [`apps/web/sentry.server.config.ts`](../../apps/web/sentry.server.config.ts) and [`apps/web/sentry.edge.config.ts`](../../apps/web/sentry.edge.config.ts), production-only and gated on `SENTRY_DSN` | Exit-code propagation by `run_acceleration_analysis.py` and structured `ERROR` and `CRITICAL` log lines emitted by `logger.py` |
| Health and readiness | Next.js health endpoint at `/api/v2/health` (excluded from OpenTelemetry HTTP instrumentation via the `ignoreIncomingRequestHook` in `instrumentation-node.ts`) | [`health.py`](./health.py) — `check_all()` verifies git availability, repository accessibility, output-directory writability, GitHub token presence, and Python version |
| Dashboard | External: SigNoz for traces (referenced by `instrumentation.ts` comment "SigNoz handles distributed tracing") and Grafana plus Prometheus for metrics | [`dashboard.html`](./dashboard.html) — self-contained single-file HTML template that reads `../data/metrics.json` via `fetch()` |
| Sampler configuration | `OTEL_TRACES_SAMPLER` environment variable with values `always_on`, `always_off`, `traceidratio`, `parentbased_traceidratio`, `parentbased_always_on`, `parentbased_always_off` (see `instrumentation-node.ts` lines 86–122) | Always-on; the analysis is deterministic for a batch run and has no sampling decision to make |
| PII and client-report telemetry | Sentry configs set `sendDefaultPii: false` and `sendClientReports: false` | The analysis emits no PII to any external destination; it writes only to the local filesystem under `acceleration/data/` |

---

## 2. Existing Formbricks Application Observability (READ-ONLY Reference)

The files below define the application's observability stack. They are **not
modified by the acceleration pipeline**. They are inspected only to populate
this disclosure and to confirm that the pipeline does not need to add another
copy of any concern that the application already covers.

### 2.1 `apps/web/instrumentation-node.ts`

Next.js OpenTelemetry instrumentation entry point. It constructs a single
`NodeSDK` instance with the following composition:

- Imports `@opentelemetry/sdk-node 0.211.0`,
  `@opentelemetry/auto-instrumentations-node 0.69.0`,
  `@opentelemetry/exporter-trace-otlp-http 0.211.0`,
  `@opentelemetry/exporter-metrics-otlp-http 0.211.0`,
  `@opentelemetry/exporter-prometheus 0.211.0`,
  `@opentelemetry/sdk-trace-base 2.5.0`,
  `@opentelemetry/sdk-metrics 2.5.0`,
  `@opentelemetry/resources 2.5.0`,
  `@opentelemetry/semantic-conventions 1.38.0`, and
  `@prisma/instrumentation 6.14.0`.
- Conditionally enables OTLP trace and metric exporters when
  `OTEL_EXPORTER_OTLP_ENDPOINT` is set. The metric reader runs
  `PeriodicExportingMetricReader` with a `60000` ms export interval.
- Conditionally enables the Prometheus exporter when `PROMETHEUS_ENABLED=1`,
  binding to `0.0.0.0` on the port given by `PROMETHEUS_EXPORTER_PORT`
  (default `9464`) at endpoint `/metrics`.
- Selects the sampler from `OTEL_TRACES_SAMPLER` (`always_on` by default) with
  optional ratio `OTEL_TRACES_SAMPLER_ARG`. The recognized sampler types are
  `always_on`, `always_off`, `traceidratio`, `parentbased_traceidratio`,
  `parentbased_always_on`, and `parentbased_always_off`.
- Disables the `instrumentation-fs`, `instrumentation-dns`,
  `instrumentation-net`, and `instrumentation-pg` auto-instrumentations
  (Prisma covers database tracing). Enables `instrumentation-runtime-node`
  for Node.js process metrics.
- The HTTP auto-instrumentation drops requests to `/health`, `/metrics`, and
  `/api/v2/health` via `ignoreIncomingRequestHook`.
- Registers a `SIGTERM` handler that calls `sdk.shutdown()` to drain spans
  before the application's own logger flush.

### 2.2 `apps/web/instrumentation.ts`

Next.js instrumentation hook. Defines `register()` which is invoked once per
runtime. The body:

- When `process.env.NEXT_RUNTIME === "nodejs"` and either `PROMETHEUS_ENABLED`
  or `OTEL_EXPORTER_OTLP_ENDPOINT` is set, dynamically imports
  `./instrumentation-node`, causing the OpenTelemetry SDK to start.
- Loads `./sentry.server.config` after OpenTelemetry (Node.js runtime only)
  when `IS_PRODUCTION` and `SENTRY_DSN` are both true. Sentry must load after
  OpenTelemetry to avoid TracerProvider conflicts; Sentry's own tracing is
  disabled (`tracesSampleRate: 0`) because SigNoz handles distributed tracing
  for the application.
- Loads `./sentry.edge.config` for the edge runtime under the same gates.
- Re-exports `onRequestError = Sentry.captureRequestError` so Next.js routes
  surface request-level errors into Sentry.

### 2.3 `apps/web/sentry.server.config.ts`

Sentry server-runtime initialization. Active only when `SENTRY_DSN` is set;
otherwise the file emits a warning via `@formbricks/logger` and returns. The
`Sentry.init` call sets:

- `tracesSampleRate: 0` — Sentry tracing is disabled because the application
  routes distributed traces through OpenTelemetry to SigNoz.
- `skipOpenTelemetrySetup: true` — Sentry must not register its own
  TracerProvider; the one from `instrumentation-node.ts` is authoritative.
- `sendDefaultPii: false` and `sendClientReports: false` — PII and client
  report telemetry are off.
- `beforeSend` — drops events whose `originalException.digest === "NEXT_NOT_FOUND"`
  so 404s do not pollute the error stream.

The `release` and `environment` fields are populated from `SENTRY_RELEASE` and
`SENTRY_ENVIRONMENT` constants in `@/lib/constants`.

### 2.4 `apps/web/sentry.edge.config.ts`

Sentry edge-runtime initialization. Same gates as the server config
(`SENTRY_DSN` and the `@/lib/constants` exports). The `Sentry.init` call sets
the same `tracesSampleRate: 0`, `sendDefaultPii: false`, and
`sendClientReports: false` flags. There is no `skipOpenTelemetrySetup` flag
because the edge runtime does not load the OpenTelemetry SDK.

### 2.5 `apps/web/prometheus.yml`

Prometheus scrape configuration consumed by an external Prometheus server in
development. Single scrape job:

```yaml
scrape_configs:
  - job_name: "nodejs-app"
    scrape_interval: 5s
    static_configs:
      - targets: ["host.docker.internal:9464"]
```

The target `host.docker.internal:9464` matches the default Prometheus
exporter port set in `instrumentation-node.ts`. The file is referenced for
local development; production deployments are expected to use a separate
Prometheus topology.

### 2.6 `apps/web/package.json` (Dependency Pins)

The relevant dependency pins, extracted verbatim:

```json
"@formbricks/logger": "workspace:*",
"@opentelemetry/auto-instrumentations-node": "0.69.0",
"@opentelemetry/exporter-metrics-otlp-http": "0.211.0",
"@opentelemetry/exporter-prometheus": "0.211.0",
"@opentelemetry/exporter-trace-otlp-http": "0.211.0",
"@opentelemetry/resources": "2.5.0",
"@opentelemetry/sdk-metrics": "2.5.0",
"@opentelemetry/sdk-node": "0.211.0",
"@opentelemetry/sdk-trace-base": "2.5.0",
"@opentelemetry/semantic-conventions": "1.38.0",
"@prisma/instrumentation": "6.14.0",
"@sentry/nextjs": "10.5.0"
```

The `@formbricks/logger` workspace package resolves to
[`packages/logger/`](../../packages/logger/) and is a Pino wrapper with a
custom level set (`debug`, `info`, `warn`, `error`, `fatal`, `audit`) plus an
optional `pino-opentelemetry-transport` for SigNoz log correlation when
`OTEL_EXPORTER_OTLP_ENDPOINT` is set. None of these dependencies are
installed or imported by the acceleration pipeline.

---

## 3. Acceleration Pipeline Observability (This Folder)

The four files in `acceleration/observability/` plus this README are the
complete observability surface for the analysis pipeline. They are
stdlib-only on the Python side and CDN-pinned on the HTML side; none of them
introduce a runtime dependency on the Formbricks application or its
`node_modules`.

### 3.1 `logger.py` — Structured JSON Logger

Python stdlib `logging` configured with a custom `JsonFormatter`. Each log
record becomes one JSON object per line, written to `sys.stdout`. Each
record carries BOTH the canonical aggregator-friendly field names AND the
compact pipeline-internal aliases — both sets of names point at the same
byte-for-byte values, so any consumer can key on either set without a
remapping rule.

Canonical names (consumed by Datadog / Loki / OpenSearch / Splunk default
source-type parsers):

- `timestamp` — ISO 8601 UTC with microseconds and a trailing `Z`.
- `level` — `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`.
- `name` — logger name (the caller's `__name__`).
- `message` — the rendered log message body.
- `correlation_id` — run-scoped correlation ID.

Compact aliases (consumed by `observability/dashboard.html` and existing
pipeline scripts):

- `ts` — alias of `timestamp`.
- `logger` — alias of `name`.
- `msg` — alias of `message`.
- `run_id` — alias of `correlation_id`.

Both alias sets agree on every record. The optional `extra` map carries any
structured key-value context the caller passed via `extra=` on a logging
call. Exception traces appear under `exc_info` when the caller invoked
`logger.exception(...)` or supplied `exc_info=`. The trade-off (slightly
larger per-line byte cost for parser-defaults compatibility) is recorded in
[`../decision-log.md`](../decision-log.md) row `D-014`.

The `run_id` / `correlation_id` is a run-scoped correlation ID generated
once per pipeline invocation (UUID4) and injected into every record via a
`logging.Filter`. The ID is read from `ACCEL_RUN_ID` when present and
generated lazily otherwise. The log level is read from `ACCEL_LOG_LEVEL`
(default `INFO`).

Public API:

- `get_logger(name: str, run_id: str | None = None) -> logging.Logger`
- `generate_run_id() -> str`
- `set_default_run_id(run_id: str) -> None`
- `get_default_run_id() -> str`
- `JsonFormatter`, `CorrelationFilter`

Imported by every script in `acceleration/scripts/`. The module is the most
foundational artifact in the pipeline and must not import from any other
`acceleration.*` module.

### 3.2 `health.py` — Health and Readiness Checks

Python stdlib only. The top-level `check_all() -> dict` returns a structured
status object with the keys `git`, `repo`, `output_dir`, `github_token`,
`python`, and `overall`. Each sub-check returns
`{"status": "ok"|"warn"|"fail", "details": "..."}`. The `overall` key is
`"ok"` only when every sub-check is `"ok"`; it degrades to `"warn"` when any
sub-check is `"warn"` and no sub-check is `"fail"`; otherwise `"fail"`.

The module is invoked first by `run_acceleration_analysis.py`. A `"fail"`
overall blocks the pipeline; a `"warn"` overall allows the pipeline to
proceed with the affected metrics degraded to `Insufficient signal — [reason]`
per AAP §0.7.2.1.

### 3.3 `metrics.json` — Static Metrics Manifest

JSON enumerating the twelve user-specified development-acceleration metrics
with `metric_id`, `display_name`, `unit`, `direction`, `confidence_rubric`,
and `data_sources` for each entry. The file is the canonical metric-surface
description and is consumed by:

- [`dashboard.html`](./dashboard.html) for metric-card labels, units, and
  direction arrows.
- `acceleration/scripts/verify_report.py` to assert that the runtime
  `acceleration/data/metrics.json` covers all twelve metrics by `metric_id`.
- `acceleration/scripts/render_report.py` for traceability-matrix column
  headers and section-heading lookups.

The twelve `metric_id` values are `flow_load`, `flow_velocity`,
`flow_predictability`, `flow_active`, `flow_efficiency`, `flow_distribution`,
`flow_time`, `problem_records`, `releases`, `approved_exceptions`,
`escaped_defects`, and `defects_out_of_sla`.

**Not to be confused with `acceleration/data/metrics.json`**: this file is
the **static manifest** (definitions, units, rubrics) created once and
checked into the repository. The runtime `acceleration/data/metrics.json` is
the **single source of truth** for computed metric values, written by
`compute_metrics.py` on every pipeline run.

### 3.4 `dashboard.html` — Self-Contained Dashboard Template

Single HTML5 file. On load it `fetch()`es `../data/metrics.json` and
`./metrics.json` and renders twelve metric cards with multiplier values and
confidence badges, a per-phase Mermaid bar chart, and a tail of the most
recent run log lines from `../data/run_manifest.json`. CDN-pinned Mermaid
`11.15.0` and Lucide `0.460.0` are loaded inline; the file has no local file
dependencies beyond the two JSON inputs it expects to read alongside it.

The Blitzy brand palette and typography are inlined as CSS custom properties
to keep the dashboard visually consistent with the executive presentation
deck (`acceleration/executive-presentation.html`) without depending on a
shared stylesheet.

---

## 4. Why a Self-Contained Python Logger?

The analysis pipeline is a Python batch process. The Formbricks
application's observability stack is a Node.js stack built on Pino and the
OpenTelemetry SDK for Node. Importing `@formbricks/logger` or
`@opentelemetry/sdk-node` into the pipeline would require Node.js as a
runtime dependency for an otherwise stdlib-only Python tool, introducing a
fork/exec boundary and an inversion of language for no operational benefit.

The pipeline is also a single-process, short-lived job. The application's
observability stack is designed for a long-running multi-process Next.js
service that emits distributed traces across HTTP, the Prisma database
client, and runtime-node metrics. The pipeline has none of those boundaries:
it reads the local git history and the GitHub API, writes JSON files under
`acceleration/data/`, and exits.

The AAP §0.6.2 directive "no shared dependency manifest entries" reinforces
the hermeticity requirement. The Formbricks root `package.json`,
`apps/web/package.json`, and the `pnpm-workspace.yaml` workspace catalog are
not modified by the analysis. A stdlib-only Python logger keeps the pipeline
inside the read-only boundary that the AAP requires outside `acceleration/`.

**Trade-off accepted**: log streams from the pipeline are not unified with
the application's traces in SigNoz. The JSON format emitted by `logger.py`
is collector-agnostic (one JSON object per line on `stdout`, with both a
canonical `correlation_id` field and its compact `run_id` alias, plus a
canonical `timestamp` and its compact `ts` alias), so any downstream
collector — Loki, OpenSearch, Datadog, SigNoz — can ingest it without
reformatting if that integration is added later.

**Cross-reference**: [`acceleration/decision-log.md`](../decision-log.md)
row **D-003** ("Self-contained logger instead of importing Formbricks
OpenTelemetry SDK").

---

## 5. Why a Static Metrics Manifest Instead of a Live `/metrics` Endpoint?

AAP Rule 1 requires "a metrics endpoint." For a long-running service this is
typically a `/metrics` HTTP endpoint — the Formbricks application exposes one
at `host.docker.internal:9464/metrics` via the OpenTelemetry Prometheus
exporter wired in `apps/web/instrumentation-node.ts`.

For a batch pipeline that runs once per analysis and exits, a live HTTP
endpoint provides zero runtime utility: no process is alive between runs for
a scraper to target, and starting a sidecar process for the duration of a
several-minute batch job adds operational surface without informational
value.

The static `metrics.json` manifest is the functional equivalent for a batch
process. It enumerates the same metrics surface that a live `/metrics`
endpoint would advertise — metric names, units, confidence rubrics, and
data-source bindings — with one canonical JSON object per metric. The
dashboard reads it. `verify_report.py` reads it. The runtime values are
written next to it at `../data/metrics.json` on every run.

This is an explicit deviation from a literal interpretation of "metrics
endpoint" and is recorded as a non-trivial decision in
[`acceleration/decision-log.md`](../decision-log.md) row **D-002** per AAP
Rule 3 ("Any deviation from a literal or obvious interpretation of the
requirements MUST have an explicit entry in the decision log").

**Trade-off accepted**: there is no live scrape target. The dashboard
mitigates the gap by re-fetching `../data/metrics.json` on every page load,
and `run_acceleration_analysis.py` re-renders the dashboard at the end of
each pipeline invocation so a viewer opening the file after a run sees the
latest values.

---

## 6. Why Degenerate Tracing?

AAP Rule 1 requires "distributed tracing across service boundaries." The
acceleration analysis is a single-process Python pipeline composed of an
orchestrator that sequentially invokes extractors, a classifier, a metric
computer, two renderers, and a verifier. There are no service boundaries to
trace.

The "trace" reduces to per-script span timing within a single process.
`logger.py` emits structured log lines tagged with a shared `run_id` (the
trace root) for every script invocation, allowing a post-run reconstruction
of the pipeline's execution from the JSON log file alone. Each script logs
its start, end, and key transitions; the `run_id` correlates them; the
`ts` field gives wall-clock ordering and duration.

This is an explicit deviation from a literal interpretation of "distributed
tracing." The deviation is recorded in
[`acceleration/decision-log.md`](../decision-log.md) alongside the rationale
for the self-contained logger.

**Trade-off accepted**: there is no flame-graph view of nested function
calls. The diagnostic question the pipeline needs to answer is "which script
took how long?" — per-script span timing answers it. If a future requirement
calls for nested-span tracing, the same `run_id` mechanism can be extended
to nested `OpenTelemetry`-compatible spans without changing the surface that
downstream collectors see.

---

## 7. What This Folder Contains

```
acceleration/observability/
├── README.md          <- this file (reused-vs-added disclosure)
├── logger.py          <- structured JSON logger with run-scoped correlation IDs
├── health.py          <- health and readiness checks
├── metrics.json       <- static metrics manifest (12 metric definitions)
└── dashboard.html     <- self-contained HTML dashboard template
```

Total: five artifacts. The pipeline's orchestrator
(`acceleration/scripts/run_acceleration_analysis.py`) imports `logger.py`
and `health.py`; the renderers read `metrics.json`; the verifier reads both
this folder's `metrics.json` and `../data/metrics.json`; `dashboard.html`
is opened by a human reviewer in a browser.

---

## 8. How to Exercise Locally

Every artifact in this folder has a copy-pasteable smoke test. AAP Rule 1
mandates local exercisability: "If you cannot exercise it locally, it is not
delivered." All commands below are run from the repository root.

### 8.1 Logger Smoke Test

```bash
python3 -c "from acceleration.observability.logger import get_logger; \
  log = get_logger('smoke', run_id='abc-123'); \
  log.info('hello', extra={'k': 'v'})"
```

Expected: a single JSON object on `stdout` containing both
`"correlation_id": "abc-123"` and `"run_id": "abc-123"` (compact alias),
both `"name": "smoke"` and `"logger": "smoke"` (compact alias),
both `"message": "hello"` and `"msg": "hello"` (compact alias),
both `"timestamp": "..."` and `"ts": "..."` (compact alias),
`"level": "INFO"`, and the `extra` map. The `timestamp` and `ts` values are
identical ISO 8601 UTC strings ending in `Z`.

### 8.2 Health Check

```bash
python3 -c "from acceleration.observability.health import check_all; \
  import json; print(json.dumps(check_all(), indent=2))"
```

Expected: a JSON object with the keys `git`, `repo`, `output_dir`,
`github_token`, `python`, and `overall`. Each sub-check has a `status` of
`ok`, `warn`, or `fail` and a human-readable `details` string. On a clean
machine without a `GITHUB_TOKEN`, the `github_token` sub-check returns
`warn` (the pipeline still runs; metrics that require GitHub API access
degrade to `Insufficient signal — [reason]`).

### 8.3 Metrics Manifest Validity

```bash
python3 -c "import json; \
  m = json.load(open('acceleration/observability/metrics.json')); \
  ids = sorted([entry['metric_id'] for entry in m['metrics']]); \
  assert len(ids) == 12, f'expected 12 metrics, found {len(ids)}'; \
  print('OK:', len(ids), 'metrics:', ids)"
```

Expected:

```
OK: 12 metrics: ['approved_exceptions', 'defects_out_of_sla', 'escaped_defects', 'flow_active', 'flow_distribution', 'flow_efficiency', 'flow_load', 'flow_predictability', 'flow_time', 'flow_velocity', 'problem_records', 'releases']
```

### 8.4 Dashboard Open

The dashboard is a single HTML file with two relative `fetch()` calls
(`./metrics.json` and `../data/metrics.json`). Some browsers block
`fetch()` against `file://` URLs; serve over HTTP if so.

```bash
# Option 1 — open directly (works in Firefox; some Chromium builds block fetch)
xdg-open acceleration/observability/dashboard.html       # Linux
open acceleration/observability/dashboard.html           # macOS

# Option 2 — serve over HTTP (recommended; works in every browser)
python3 -m http.server 8000
# then visit:
#   http://localhost:8000/acceleration/observability/dashboard.html
```

Expected: twelve metric cards render with multiplier values and confidence
badges, a per-phase Mermaid bar chart renders below, and the run-log tail
shows the most recent JSON log lines from the last pipeline run.

### 8.5 End-to-End Pipeline (Exercises Every Artifact)

The orchestrator exercises all four observability artifacts in one
invocation:

```bash
python3 acceleration/scripts/run_acceleration_analysis.py
```

Expected: the orchestrator runs `health.check_all()`, generates a `run_id`
via `logger.generate_run_id()`, writes JSON log lines through `logger.py`
for every sub-step, regenerates `data/metrics.json`, and exits with status
`0` on success or a non-zero status on the first `fail`-level health check
or extractor error.

---

## 9. Trade-Off Summary

The three additions in this folder accept three trade-offs against the
Formbricks application's observability stack. Each trade-off is deliberate
and documented in [`acceleration/decision-log.md`](../decision-log.md).

- **Self-contained Python logger** is not unified with the Formbricks app's
  Pino/OpenTelemetry/SigNoz pipeline. Accepted: the analysis is a hermetic
  batch process that should not import Node.js packages.
- **Static `metrics.json` manifest** is not a live `/metrics` HTTP endpoint.
  Accepted: a batch process has no long-running surface for a scraper to
  target; the dashboard re-fetches the manifest on every page load.
- **Degenerate per-script span timing** is not a multi-service distributed
  trace. Accepted: the pipeline is single-process; the diagnostic question
  "which script took how long?" is answered by `run_id`-correlated log
  lines.

If a future deployment of this pipeline introduces a service boundary — for
example, a separate worker that consumes extractor output — the same
`run_id` mechanism extends to nested spans without changing the surface
that downstream collectors see.

---

## 10. Cross-References

### Existing Formbricks observability (READ-ONLY references)

- [`apps/web/instrumentation-node.ts`](../../apps/web/instrumentation-node.ts) — OpenTelemetry SDK initialization, OTLP and Prometheus exporters, sampler selection, Prisma instrumentation.
- [`apps/web/instrumentation.ts`](../../apps/web/instrumentation.ts) — Next.js `register()` hook, OpenTelemetry-then-Sentry load order, edge vs. server runtime gates.
- [`apps/web/sentry.server.config.ts`](../../apps/web/sentry.server.config.ts) — Sentry server runtime (`tracesSampleRate: 0`, `skipOpenTelemetrySetup: true`, PII off).
- [`apps/web/sentry.edge.config.ts`](../../apps/web/sentry.edge.config.ts) — Sentry edge runtime (same PII and tracing gates).
- [`apps/web/prometheus.yml`](../../apps/web/prometheus.yml) — Prometheus scrape config for the `nodejs-app` job at `host.docker.internal:9464`.
- [`apps/web/package.json`](../../apps/web/package.json) — OpenTelemetry and Sentry version pins, `@formbricks/logger` workspace reference.
- [`packages/logger/`](../../packages/logger/) — the workspace Pino logger consumed by `apps/web` and other application packages.

### Acceleration pipeline files

- [`acceleration/decision-log.md`](../decision-log.md) — trade-off rationale for the static metrics manifest (row **D-002**) and the self-contained logger (row **D-003**).
- [`acceleration/README.md`](../README.md) — pipeline onboarding (prerequisites, environment variables, end-to-end run).
- [`acceleration/scripts/run_acceleration_analysis.py`](../scripts/run_acceleration_analysis.py) — orchestrator that exercises `logger.py`, `health.py`, and the dashboard refresh sequence.
- [`acceleration/scripts/verify_report.py`](../scripts/verify_report.py) — consumer of the static `metrics.json` manifest for traceability-matrix validation.
- [`acceleration/observability/logger.py`](./logger.py) — structured JSON logger.
- [`acceleration/observability/health.py`](./health.py) — health and readiness checks.
- [`acceleration/observability/metrics.json`](./metrics.json) — static metrics manifest.
- [`acceleration/observability/dashboard.html`](./dashboard.html) — self-contained dashboard template.
