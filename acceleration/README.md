# Development Acceleration Analysis

This directory contains a self-contained, read-only analysis pipeline that measures development acceleration across twelve metrics by comparing a Baseline period (before an AI tool was introduced into the Formbricks engineering workflow) against the period after introduction, segmented into Ramp-Up (first 90 days) and Steady State (90+ days). The pipeline reads the local git history and selected GitHub APIs, derives every number from a documented extraction command, and produces a Markdown report ([`acceleration-report.md`](./acceleration-report.md)), an executive HTML deck ([`executive-presentation.html`](./executive-presentation.html)), and a self-contained run dashboard ([`observability/dashboard.html`](./observability/dashboard.html)). The audience is engineering leadership reviewing the acceleration result and acceleration researchers reproducing or extending the methodology.

---

## 1. What's In Here

```
acceleration/
├── README.md                       # This file — onboarding entry point
├── acceleration-report.md          # Primary deliverable (12 metrics × 3 phases)
├── decision-log.md                 # Non-trivial decisions + traceability matrix (Rule 3)
├── executive-presentation.html     # Reveal.js leadership deck (Rule 5)
├── requirements.txt                # Optional Python pins (stdlib-only by default)
├── data/                           # Runtime extraction output (created on first run)
│   ├── inflection.json             # Detected AI-introduction date + rationale
│   ├── commits.jsonl               # Normalized commit records
│   ├── prs.jsonl                   # Normalized PR records
│   ├── reviews.jsonl               # PR review timestamps
│   ├── releases.jsonl              # Release records (GitHub Releases API)
│   ├── reverts.jsonl               # Revert commits with attribution
│   ├── issues.jsonl                # Bug-labeled issue records
│   ├── test_results.jsonl          # CI test transitions (when retrievable)
│   ├── branch_protection.json      # Branch-protection config (when accessible)
│   ├── audit_log.jsonl             # Admin audit log (when accessible)
│   ├── sla_source.json             # SLA-policy discovery result
│   ├── actor_aliases.json          # Resolved (email → display name) map
│   ├── github_access.json          # API capability probe result
│   ├── metrics.json                # Single source of truth — all 12 metric values
│   ├── run_manifest.json           # Pipeline start/end/env/exit-code metadata
│   └── reproduce.sh                # Ordered shell script to re-derive every number
├── observability/
│   ├── logger.py                   # Structured-JSON logger with run-scoped correlation IDs (Rule 1)
│   ├── health.py                   # Health and readiness checks (Rule 1)
│   ├── metrics.json                # Static metrics manifest (Rule 1)
│   ├── dashboard.html              # Self-contained pipeline dashboard (Rule 1)
│   └── README.md                   # Reused-vs-added observability disclosure (Rule 1)
├── scripts/
│   ├── run_acceleration_analysis.py  # Orchestrator — single entry point
│   ├── detect_inflection.py          # Inflection-date detection
│   ├── extract_git.py                # Git-history extractor
│   ├── extract_github.py             # GitHub REST/GraphQL extractor
│   ├── extract_ci_tests.py           # GitHub Actions Artifacts extractor
│   ├── extract_issues.py             # GitHub Issues extractor
│   ├── classify_prs.py               # Metric 6 work-type classifier
│   ├── compute_metrics.py            # 12-metric computation
│   ├── render_report.py              # acceleration-report.md renderer
│   ├── render_deck.py                # executive-presentation.html renderer
│   └── verify_report.py              # Rule 1–6 verification
└── templates/
    ├── mermaid/                    # Inline Mermaid diagrams for the report
    └── deck/                       # Reveal.js slide templates and theme CSS
```

For Formbricks application setup, see the repository root [`README.md`](../README.md). For monorepo conventions, see [`AGENTS.md`](../AGENTS.md) at the repository root. For contribution guidelines, see [`CONTRIBUTING.md`](../CONTRIBUTING.md) at the repository root. This directory does not duplicate those documents — it is strictly the analysis-pipeline onboarding surface.

---

## 2. Prerequisites

| Tool                | Required Version   | Purpose                                                                                                | Verification                      |
| ------------------- | ------------------ | ------------------------------------------------------------------------------------------------------ | --------------------------------- |
| `git`               | ≥ 2.40             | Primary data source for commit history, branches, reverts, and PR-merge identification.                | `git --version`                   |
| `python3`           | ≥ 3.10             | Pipeline interpreter. Standard library covers all 12 metrics — no third-party packages are required.   | `python3 --version`               |
| `curl`              | ≥ 7.80             | GitHub REST and GraphQL HTTP calls in `extract_github.py`, `extract_ci_tests.py`, `extract_issues.py`. | `curl --version`                  |
| `gh` CLI (optional) | ≥ 2.50             | Alternative HTTP client. When present, the scripts prefer it over `curl` for authenticated calls.      | `gh --version`                    |
| `matplotlib` (opt.) | 3.9.2              | Static PNG export of the Acceleration Curve. Without it, the Mermaid inline diagram is the rendering.  | `python3 -c "import matplotlib"`  |
| Web browser         | Any modern build   | Open `executive-presentation.html` and `observability/dashboard.html`. No local server required.       | Open the file with `file://` URL. |
| Operating system    | macOS, Linux, WSL2 | The pipeline uses POSIX shell semantics. Native Windows (cmd.exe) is not supported.                    | `uname -a`                        |

The runtime health module (`observability/health.py`) re-verifies each prerequisite at the start of every pipeline run and refuses to proceed if any required tool is missing.

Node.js is not a prerequisite for this pipeline. The Formbricks application pins Node `22.1.0` via [`.nvmrc`](../.nvmrc), but the acceleration pipeline does not invoke any Node code.

---

## 3. Environment Variables

| Name              | Required | Default             | Description                                                                                                                                                                                                                                                                                                  |
| ----------------- | -------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GITHUB_TOKEN`    | No       | unset               | GitHub personal access token. Recommended scopes: `repo`, `read:org`, `read:audit_log`. Without it, the pipeline falls back to unauthenticated calls (60 req/hour) and downgrades Metrics 1, 8, 9, 10, 11, 12 to Medium or Insufficient confidence per the rubric in [`decision-log.md`](./decision-log.md). |
| `REPO_OWNER`      | No       | `formbricks`        | GitHub repository owner (organization or user). Consumed as the default for `--owner`.                                                                                                                                                                                                                       |
| `REPO_NAME`      | No       | `formbricks`        | GitHub repository name. Consumed as the default for `--repo`.                                                                                                                                                                                                                                                 |
| `ACCEL_LOG_LEVEL` | No       | `INFO`              | Verbosity of the structured logger. Accepted values: `DEBUG`, `INFO`, `WARNING`, `ERROR`. Read by [`acceleration/observability/logger.py`](./observability/logger.py).                                                                                                                                       |
| `ACCEL_RUN_ID`    | No       | auto-generated UUID | Correlation ID injected into every log line. Override to group logs across multiple invocations of the same pipeline run. The orchestrator publishes its resolved value to the environment so every subprocess inherits the same ID.                                                                          |

The output directory is configured via the `--output-dir` flag (not an environment variable). To run offline, pass `--skip-network` to disable all GitHub API calls, or `--skip-github` / `--skip-ci-tests` / `--skip-issues` to drop one extractor at a time.

Create a fine-grained personal access token at <https://github.com/settings/tokens?type=beta>. Limit the token to the single repository under analysis. Expiration: 30 days is sufficient for one-off acceleration analyses.

---

## 4. Setup (Clean Machine → Ready in 5 Minutes)

Run these steps in order from a fresh shell. The pipeline is read-only — no `git add`, `git commit`, or `git push` is invoked at any point.

```bash
# 1. Clone the Formbricks repository
git clone https://github.com/formbricks/formbricks.git
cd formbricks

# 2. Verify prerequisites (each command prints a version line)
git --version
python3 --version
curl --version

# 3. (Optional) Install the optional Python pins for static-chart export
python3 -m pip install -r acceleration/requirements.txt

# 4. (Optional but recommended) Export a GitHub token to lift the
#    rate limit from 60/hour to 5,000/hour and enable Metrics 8–12
export GITHUB_TOKEN=ghp_your_token_here

# 5. Run the full pipeline end-to-end
python3 acceleration/scripts/run_acceleration_analysis.py

# 6. Read the report
cat acceleration/acceleration-report.md
#   or, on macOS:
open acceleration/acceleration-report.md
#   or, in a browser:
open acceleration/executive-presentation.html
```

Total elapsed time on a clean clone with a valid `GITHUB_TOKEN`: approximately 3–5 minutes for the Formbricks repository (5,178 commits at HEAD `bb1acd083`). Without a token, the same run completes in approximately 90 seconds but reports several metrics as `Insufficient signal`.

---

## 5. How to Run

The orchestrator [`scripts/run_acceleration_analysis.py`](./scripts/run_acceleration_analysis.py) sequences the entire pipeline. It is the only command a typical user needs to invoke.

```bash
# Default — produces every artifact under acceleration/
python3 acceleration/scripts/run_acceleration_analysis.py

# Skip every network-bound extractor at once (offline smoke test)
python3 acceleration/scripts/run_acceleration_analysis.py --skip-network

# Skip a single network-bound extractor (others still attempt their calls)
python3 acceleration/scripts/run_acceleration_analysis.py --skip-github
python3 acceleration/scripts/run_acceleration_analysis.py --skip-ci-tests
python3 acceleration/scripts/run_acceleration_analysis.py --skip-issues

# Direct artifacts to an alternate output directory
python3 acceleration/scripts/run_acceleration_analysis.py --output-dir /tmp/accel-run

# Increase log verbosity to DEBUG (environment variable, not a flag)
ACCEL_LOG_LEVEL=DEBUG python3 acceleration/scripts/run_acceleration_analysis.py

# Run only specific steps (canonical order is preserved; unlisted steps emit status=skipped)
python3 acceleration/scripts/run_acceleration_analysis.py --only render_report,render_deck,verify_report

# Override repository identifiers (defaults: REPO_OWNER env → 'formbricks', REPO_NAME env → 'formbricks')
python3 acceleration/scripts/run_acceleration_analysis.py --owner formbricks --repo formbricks --branch main

# Combine flags — full offline run against an alternate output dir
ACCEL_LOG_LEVEL=DEBUG \
python3 acceleration/scripts/run_acceleration_analysis.py \
    --skip-network --output-dir /tmp/accel-run
```

Full list of orchestrator flags (always available via `--help`):

| Flag                    | Default              | Purpose                                                                                                                                                                       |
| ----------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--repo-root`           | `.`                  | Path to the repository root.                                                                                                                                                  |
| `--output-dir`          | `acceleration/data`  | Directory under which all extractor outputs (`*.jsonl`, `*.json`, `metrics.json`, `run_manifest.json`) are written. The orchestrator creates the directory if it is missing.   |
| `--accel-dir`           | `acceleration`       | Path to the acceleration root containing `scripts/`, `observability/`, `templates/`. Renderers write `acceleration-report.md` and `executive-presentation.html` into this dir. |
| `--owner`               | env `REPO_OWNER`     | GitHub repository owner.                                                                                                                                                      |
| `--repo`                | env `REPO_NAME`      | GitHub repository name.                                                                                                                                                       |
| `--branch`              | `main`               | Git branch / ref to log.                                                                                                                                                      |
| `--skip-network`        | `false`              | Pass `--skip-network` to every network-bound extractor.                                                                                                                       |
| `--skip-github`         | `false`              | Skip the `extract_github` step entirely (still records a `skipped` entry in `run_manifest.json`).                                                                              |
| `--skip-ci-tests`       | `false`              | Skip the `extract_ci_tests` step entirely.                                                                                                                                    |
| `--skip-issues`         | `false`              | Skip the `extract_issues` step entirely.                                                                                                                                      |
| `--only`                | (run all)            | Comma-separated list of step names to run (e.g. `render_report,verify_report`). Steps not listed emit `status=skipped`.                                                       |
| `--continue-on-error`   | `false`              | Do not halt the pipeline on a non-optional step failure. Useful for forensic runs that need to inspect every step.                                                            |
| `--no-readonly-check`   | `false`              | Disable the pre/post git-status diff that enforces AAP §0.5.2 read-only-outside-`acceleration/`. CI runs MUST NOT use this; intended for development convenience only.        |

Every individual step script is independently runnable for debugging or partial reruns. Each script accepts `--help` and writes a deterministic output file.

```bash
# Detect the AI-introduction inflection date in isolation
python3 -m acceleration.scripts.detect_inflection --help
python3 -m acceleration.scripts.detect_inflection \
    --data-dir acceleration/data \
    --output acceleration/data/inflection.json

# Re-extract git history only (no GitHub API)
python3 -m acceleration.scripts.extract_git --output-dir acceleration/data

# Re-render the report from an existing acceleration/data/metrics.json
python3 -m acceleration.scripts.render_report \
    --metrics acceleration/data/metrics.json \
    --inflection acceleration/data/inflection.json \
    --manifest acceleration/data/run_manifest.json \
    --templates-dir acceleration/templates/mermaid \
    --output acceleration/acceleration-report.md

# Verify report-internal Rules 1–6 against an existing report
python3 -m acceleration.scripts.verify_report \
    --report acceleration/acceleration-report.md \
    --deck acceleration/executive-presentation.html \
    --metrics acceleration/data/metrics.json
```

---

## 6. Outputs

Every artifact below is written under `acceleration/`. The pipeline does not modify any file outside this directory.

| Artifact                                                         | Producer                                | Consumer                                | One-Line Description                                                                      |
| ---------------------------------------------------------------- | --------------------------------------- | --------------------------------------- | ----------------------------------------------------------------------------------------- |
| [`acceleration-report.md`](./acceleration-report.md)             | `render_report.py`                      | Human readers                           | Primary deliverable. 12 metric deep-dives, traceability matrix, reproducibility appendix. |
| [`executive-presentation.html`](./executive-presentation.html)   | `render_deck.py`                        | Engineering leadership                  | Reveal.js HTML deck (16 slides, CDN-pinned, Blitzy brand palette, zero text-only slides). |
| [`decision-log.md`](./decision-log.md)                           | (committed)                             | Reviewers, future maintainers           | Decision table + bidirectional traceability matrix (Rule 3).                              |
| [`observability/dashboard.html`](./observability/dashboard.html) | committed; consumes `data/metrics.json` | Pipeline operators                      | Self-contained run dashboard rendering the 12 metric values and run-log tail.             |
| [`data/inflection.json`](./data/)                                | `detect_inflection.py`                  | `compute_metrics.py`, renderers         | Detected inflection date, method, and rejected candidates.                                |
| [`data/commits.jsonl`](./data/)                                  | `extract_git.py`                        | `classify_prs.py`, `compute_metrics.py` | One JSON line per commit: SHA, author, date, files, trailers.                             |
| [`data/prs.jsonl`](./data/)                                      | `extract_git.py` + `extract_github.py`  | `classify_prs.py`, `compute_metrics.py` | One JSON line per merged PR with reviews and draft transitions.                           |
| [`data/reviews.jsonl`](./data/)                                  | `extract_github.py`                     | `compute_metrics.py`                    | One JSON line per PR review event (timestamp, reviewer, state).                           |
| [`data/releases.jsonl`](./data/)                                 | `extract_github.py`                     | `compute_metrics.py`                    | One JSON line per release with `target_commitish`, prerelease flag, and tag.              |
| [`data/reverts.jsonl`](./data/)                                  | `extract_git.py`                        | `compute_metrics.py`                    | One JSON line per revert with original SHA and attributed release.                        |
| [`data/issues.jsonl`](./data/)                                   | `extract_issues.py`                     | `compute_metrics.py`                    | One JSON line per bug-labeled issue with timestamps and labels.                           |
| [`data/test_results.jsonl`](./data/)                             | `extract_ci_tests.py`                   | `compute_metrics.py`                    | One JSON line per CI test transition on `main`.                                           |
| [`data/branch_protection.json`](./data/)                         | `extract_github.py`                     | `compute_metrics.py`                    | Branch-protection configuration for `main` (when token scope permits).                    |
| [`data/audit_log.jsonl`](./data/)                                | `extract_github.py`                     | `compute_metrics.py`                    | Admin audit-log entries used for Metric 10 (when accessible).                             |
| [`data/sla_source.json`](./data/)                                | `extract_issues.py`                     | `compute_metrics.py`                    | Discovered SLA policy source or `null` if absent.                                         |
| [`data/actor_aliases.json`](./data/)                             | `extract_git.py`                        | `compute_metrics.py`, renderers         | Resolved alias map for per-actor breakdowns.                                              |
| [`data/github_access.json`](./data/)                             | `extract_github.py`                     | `compute_metrics.py`, renderers         | Recorded API capability probe (token scopes, rate-limit headers, accessible endpoints).   |
| [`data/metrics.json`](./data/)                                   | `compute_metrics.py`                    | All renderers + `verify_report.py`      | **Single source of truth.** Every reported number originates here.                        |
| [`data/run_manifest.json`](./data/)                              | `run_acceleration_analysis.py`          | Operators, post-run validation          | Run start, end, environment fingerprint, per-step exit codes, total wall time.            |
| [`data/reproduce.sh`](./data/)                                   | `compute_metrics.py`                    | Future re-runs, the report's appendix   | Ordered shell script that re-derives every number from a clean clone.                     |

---

## 7. Troubleshooting

| Symptom                                                     | Cause                                                                                        | Fix                                                                                                                                                                                      |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `git: command not found` or version `< 2.40`                | `git` is missing or too old for `--reverse` + `--name-only` semantics used by the extractor. | Install git 2.40 or later. On Debian/Ubuntu: `sudo apt-get install -y git`. On macOS: `brew install git`. Re-run the health check with `python3 acceleration/observability/health.py`.   |
| `GITHUB_TOKEN not set; falling back to unauthenticated API` | Environment variable is unset.                                                               | Create a fine-grained PAT at <https://github.com/settings/tokens?type=beta> with `repo`, `read:org`, `read:audit_log` scopes, then `export GITHUB_TOKEN=ghp_...` and re-run.             |
| `403 Forbidden — rate limit exceeded`                       | Unauthenticated limit (60 req/hour) or authenticated limit (5,000 req/hour) was reached.     | Wait until the `X-RateLimit-Reset` epoch printed in the log. Export `GITHUB_TOKEN` if not already set. The orchestrator emits a `Retry-After` log line — pause for the duration printed. |
| `Insufficient signal — CI test history unavailable`         | GitHub Actions Artifacts retention is 90 days; older runs do not retain JUnit XML.           | Expected for analyses spanning more than 90 days of CI history. Metric 11 reports `Insufficient signal` and the gap is recorded in the report's Limitations section.                     |
| `Insufficient signal — no SLA source`                       | Neither an issue-tracker SLA field nor an in-repo SLA policy doc was discovered.             | Expected for Formbricks today. Adding `docs/policies/sla.md` (with severity tiers and target restore times) enables Metric 12 at High confidence on the next run.                        |
| `Insufficient signal — audit log not accessible`            | Token lacks `read:audit_log` scope or the org admin has not granted access.                  | Regenerate the token with `read:audit_log` scope, or accept the gap. Metric 10 falls back to label-based signal at Low confidence when audit-log access is absent.                       |
| `verify_report.py FAILED: subjective qualifier found`       | A phrase from the prohibited list appeared in the report body.                               | Inspect the matched line. Replace the qualifier with a numeric statement (Rule 2). Re-run `render_report.py` and then `verify_report.py`.                                                |
| `verify_report.py FAILED: numeric mismatch across sections` | A metric value differs between the Executive Summary and a Metric Deep-Dive.                 | The renderer should never produce this. If it does, delete `acceleration/acceleration-report.md` and re-run the orchestrator — the renderer is idempotent.                               |

When in doubt, inspect `acceleration/data/run_manifest.json` for the per-step exit code and consult the JSON log lines for the failed step. Every log line carries the `ACCEL_RUN_ID` for correlation across the run.

---

## 8. Domain Context

The pipeline measures development acceleration across twelve metrics. They group into three families:

- **Flow metrics (1–7)** align with the Flow Framework taxonomy: Flow Load, Flow Velocity, Flow Predictability, Flow Active, Flow Efficiency, Flow Distribution, Flow Time. They describe how much work is in progress, how fast it moves, how predictable its delivery is, how much of the wall-clock time is active engineering effort, how that effort is distributed across work types, and how long a unit of work takes end-to-end.
- **DORA-adjacent metrics (8, 9, 11)** mirror the DORA four keys partially: Problem Records (Metric 8) maps to Change Failure Rate at the incident-record level; Releases (Metric 9) maps to Deployment Frequency; Escaped Defects (Metric 11) maps to Change Failure Rate at the test-signal level.
- **Governance metrics (10, 12)** measure risk and SLA compliance: Approved Exceptions (Metric 10) counts merge-protection bypasses with explicit approval; Defects Out of SLA (Metric 12) counts bug-labeled issues whose time-to-restore exceeded a published SLA target.

Every metric is reported as an **after-period / before-period multiplier**, with the after period further split into **Ramp-Up** (the first 90 days after the AI-introduction inflection date) and **Steady State** (90+ days after). When fewer than six 2-week windows of post-introduction data exist, the report falls back to **Baseline vs Post-Introduction** and notes the rationale in the Methodology section.

The **inflection date** is the single dimension that divides every metric. The pipeline detects it deterministically by scanning every commit's trailers for AI-tool email patterns (`agent@blitzy.com`, `noreply@anthropic.com`, `copilot@github.com`, `blitzy[bot]`) and, in parallel, computing a rolling 14-day commit-velocity series to locate the sharpest sustained inflection. The chosen date and the rejected candidate are written to `data/inflection.json` along with the selection method.

Every metric carries a **confidence tag** assigned at runtime based on the data source actually used:

- **High** — direct counts from an issue tracker or a fully accessible API surface. Example: Releases (Metric 9) is High when the GitHub Releases API is reachable and returns release records with `target_commitish` SHAs.
- **Medium** — approximated from git commit patterns. Example: Flow Velocity (Metric 2) is Medium when counted as PR-merge commits per Monday-aligned 2-week window rather than as story points closed.
- **Low** — inferred from indirect proxies. Example: Approved Exceptions (Metric 10) is Low when only label-based signal is available because admin audit-log access was not granted.

The pipeline applies **identical methodology before and after** the inflection. The same extractor runs with only the actor identity substituted: human author emails in the baseline, `agent@blitzy.com` in the after period. Per-actor breakdowns for Metrics 2, 4, 5, 6, and 10 include `Blitzy Agent` as one row in the after period alongside human contributors.

For the full per-metric definition and the rationale behind each extraction choice, see [`acceleration-report.md`](./acceleration-report.md) and [`decision-log.md`](./decision-log.md).

---

## 9. Common Pitfalls

The pipeline enforces several invariants from the Agent Action Plan. Violating any of them produces a failed verification run.

- **Do not modify files outside `acceleration/`.** The read-only boundary is enforced post-run. The orchestrator computes a checksum manifest of every file outside `acceleration/` before the pipeline starts and re-checks them on exit; any change aborts the run with a non-zero exit code.
- **Do not add metrics beyond the twelve specified.** AAP §0.7.2.1 forbids it: _"MUST NOT add metrics beyond the 12 specified."_ The `compute_metrics.py` registry is closed-membership and refuses unknown metric IDs.
- **Do not estimate or extrapolate missing values.** AAP §0.7.2.1: _"MUST NOT fabricate, estimate, or extrapolate."_ When a data source is unavailable, the affected metric must report `Insufficient signal — [reason]` with the `tried` and `needed` fields populated in `data/metrics.json`.
- **Do not selectively omit data that contradicts a pattern.** Every commit, PR, release, and issue in the resolved time range must be counted. The classifiers may flag a record as `unattributable`, `unreleased`, or `unknown work type`, but the record must remain in the dataset and be disclosed in the report's Limitations section.
- **Do not use subjective qualifiers in the report.** `verify_report.py` greps the report body against a fixed allow-deny list of opinion-bearing adjectives and adverbs (the full list is defined as `SUBJECTIVE_TOKENS` at the top of `verify_report.py`). Any match fails the run. Replace such terms with numeric statements grounded in `data/metrics.json`.
- **Do not bypass identical methodology.** The before-period and after-period extractors run the same code path with only the actor parameter substituted. Do not branch the extraction logic on the period; branch only on the actor identity passed in.
- **Mind the Mermaid version floor.** The Acceleration Curve diagram uses `xychart-beta`, which requires Mermaid ≥ 11.0. The deck pins Mermaid `11.15.0` via CDN per Rule 5. Older Mermaid versions silently fail to render the chart.
- **Network-bound extractors use stdlib `urllib`, not `curl` or `gh`.** All HTTP calls are made by `urllib.request.urlopen` inside the extractor scripts. There is no `gh`/`curl` selection knob. If outbound HTTPS is restricted, pass `--skip-network` (or the per-extractor skip flag) to the orchestrator so the relevant metrics degrade to `Insufficient signal` instead of failing the run.

---

## 10. How to Extend

The pipeline is structured to make the following extensions straightforward. Each one is bounded to a single script.

- **Add a new pipeline step.** The orchestrator's canonical sequence is defined as the module-level `PIPELINE: list[Step]` constant in [`run_acceleration_analysis.py`](./scripts/run_acceleration_analysis.py). Append a new `Step(name=..., description=..., runner="python_module"|"python_function", target="acceleration.scripts.your_step", args_factory="your_step_args", optional=False, skip_when=None)` entry and add the matching `your_step_args` method to `PipelineContext`. The new step is picked up automatically; supply `--only your_step` to drive it in isolation.
- **Add a new data source.** Extend the relevant `extract_*.py` script with a new fetch function, normalize its output into a `*.jsonl` file under `data/`, and add an entry to [`observability/metrics.json`](./observability/metrics.json) documenting the source binding. Update the file inventory table in §6 of this README.
- **Refine an existing metric's extraction.** Locate the metric in `compute_metrics.py` (each metric has a `compute_<name>(ctx)` function: `compute_flow_load`, `compute_flow_velocity`, …, `compute_defects_out_of_sla`). Update the function in place. Re-run the full pipeline; the renderer rereads `metrics.json` without code changes.
- **Add a new diagram to the report.** Drop a `.mmd.tmpl` file into [`templates/mermaid/`](./templates/mermaid). Render templates are picked up by name from `render_report.compose_report()` via the `--templates-dir` argument. Provide a descriptive title and a legend per Rule 4.
- **Add a new slide to the deck.** Drop a `slide_NN_<topic>.html.tmpl` into [`templates/deck/`](./templates/deck), then append its filename to the `SLIDE_FILENAMES` list in `render_deck.py`. The slide count must stay within 12–18 inclusive per Rule 5; `verify_report.py` enforces this.
- **Add a new verification check.** In `verify_report.py`, add a new function matching the existing check style and append it to the `CHECKS` registry at the bottom of the file. The orchestrator exit code becomes non-zero if any registered check fails.
- **Add a new troubleshooting entry to this README.** When a new failure mode is observed, document the symptom, cause, and fix in §7 above. Keep the table sorted by frequency.

For governance reasons, **adding a thirteenth metric is forbidden** by AAP §0.7.2.1. The metric registry in `compute_metrics.py` validates membership against the twelve specified IDs and rejects additions. If a stakeholder requests an additional metric, surface the request as a follow-up task in §11 below rather than implementing it inline.

---

## 11. Suggested Next Tasks

These items were discovered during development of the analysis pipeline. They are out of scope for this iteration but are documented here per Rule 2 (_"Include suggested next tasks — improvements discovered during development that were out of scope but worth pursuing."_).

1. **Establish an SLA policy document at `docs/policies/sla.md`.** Define severity tiers and target restore times. This upgrades Metric 12 (Defects Out of SLA) from `Insufficient signal — no SLA source` to High confidence and removes a Limitations entry.
2. **Adopt annotated git tags for releases (in addition to GitHub Releases).** Pattern: `v?\d+\.\d+\.\d+`. Tags provide a local-only fallback for Metric 9 (Releases) when the GitHub API is unreachable, eliminating the network dependency for that metric.
3. **Add `exception`, `waiver`, and `override` labels to [`.github/labeler.yml`](../.github/labeler.yml).** Once labels exist and PR authors apply them, Metric 10 (Approved Exceptions) gains a label-based signal that runs at Medium confidence without requiring admin audit-log access.
4. **Pin a CI workflow that publishes JUnit XML to a long-lived artifact.** The default GitHub Actions retention is 90 days; pinning a workflow that uploads JUnit XML to an external store (S3, GCS) enables Metric 11 (Escaped Defects) longitudinal analysis beyond the 90-day window.
5. **Add a per-PR `flow_active_ms` step in CI.** A small GitHub Actions step can compute the working span between consecutive commits and the first review-request and emit a workflow summary line. With direct measurement available, Metric 4 (Flow Active) upgrades from Medium (proxy-based) to High confidence.
6. **Provision a token with `read:audit_log` scope for the analysis run.** When organization admins approve, Metric 10 (Approved Exceptions) can read merge-protection bypasses directly from the audit log and upgrade from Low to High confidence.
7. **Add a Linear or Jira link in PR descriptions** if external issue tracking is adopted. The PR classifier in `classify_prs.py` will pick up the linked-issue labels and upgrade Metric 6 (Flow Distribution) classification fidelity.
8. **Cache extractor output between runs.** Today every run re-extracts the full history. A content-addressed cache keyed by `git rev-parse HEAD` and the `since` window would let incremental reruns complete in seconds.

---

## 12. License & Authority

This directory contains analytical artifacts produced by a read-only analysis of the Formbricks repository. No file outside `acceleration/` is modified by the pipeline. The repository's root [`LICENSE`](../LICENSE) governs the underlying source code and continues to apply to all files in this directory. The analysis is non-deployable, performs zero write operations against external systems, and produces no merge commits.

For the rationale behind every non-trivial implementation decision, see [`decision-log.md`](./decision-log.md). For observability scope and the reused-vs-added disclosure, see [`observability/README.md`](./observability/README.md). For the full primary deliverable, see [`acceleration-report.md`](./acceleration-report.md).
