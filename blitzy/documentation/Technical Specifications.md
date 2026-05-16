# Technical Specification

# 0. Agent Action Plan

## 0.1 Intent Clarification

### 0.1.1 Core Objective

Based on the provided requirements, the Blitzy platform understands that the objective is to produce a **Blitzy Profile Document** — a structured, evidence-grounded characterization of how the AI agent committing as `agent@blitzy.com` makes engineering decisions inside this Formbricks repository. The deliverable is descriptive, not evaluative: it captures recurring preferences, trade-off tendencies, and architectural biases that emerge across all commits authored by Blitzy, and it lets a reader predict how Blitzy would approach a novel technical decision in this codebase.

The platform understands the analysis surface to be:

- **Git log corpus** — every commit whose author email is `agent@blitzy.com`, including SHA, message, timestamp, file list, insertion/deletion counts, and full diff body. The local clone at `/tmp/blitzy/blitzy-formbricks/main_0d6e40` carries 208 such commits reachable from `main` [.git:`HEAD = c06879940eaaf0c98fbd373f1884b5852522ecc4`] and a total of 640 unique SHAs reachable from `--all` refs [inferred — derived from `git log --all --author="agent@blitzy.com" --oneline | sort -u | wc -l`].
- **Blitzy branches** — every branch whose name is prefixed `blitzy-`. The repository carries 8 such branches under `remotes/origin/blitzy-*` [.git/refs/remotes/origin/blitzy-*].
- **Project Guides** — `blitzy/documentation/Project Guide.md` on each `blitzy-*` branch. All 8 are present and sized 18,435-30,981 bytes [blitzy/documentation/Project Guide.md:branch-scoped].
- **Commit-to-branch correlation** — each unique SHA is mapped back to one or more originating `blitzy-*` branches so each commit can be associated with the Project Guide that scoped it.

Implicit requirements surfaced from the prompt:

- A deterministic commit taxonomy is required because frequency claims must be quantified; ambiguity in categorization invalidates ratios.
- Commits that appear on multiple branches must be deduplicated by SHA and attributed to every containing branch.
- Each `blitzy-*` branch's directives must be machine-readable enough to support a DIRECTED / AUTONOMOUS / AMBIGUOUS classification for the patterns it produced.
- Read-only execution implies the use of `git show <ref>:<path>` rather than `git checkout` when accessing per-branch files, so `HEAD` never moves.
- Per-branch HEAD restoration is required even if a checkout is performed for any reason; the validation checklist explicitly tests this.

Dependencies and prerequisites identified:

- Git 2.43.0 CLI (already installed) [`/usr/bin/git`]
- Python 3.12 (already installed) [`/usr/bin/python3 --version`]
- Read access to all `blitzy-*` remote refs (already fetched into `remotes/origin/blitzy-*`)
- Output workspace outside the tracked tree — required so `git status` remains clean per the user's read-only rule

### 0.1.2 Task Categorization

- **Primary task type**: Documentation / Behavioral Analysis. The output is a knowledge artifact (a profile document), not a code change. The analysis pipeline is the means; the markdown report and its companion deliverables are the ends.
- **Secondary aspects**:
  - Tooling — a Python-based git inspection pipeline is created from scratch to enumerate, categorize, and cluster commit observations.
  - Build / packaging — the reveal.js HTML deck mandated by the Executive Presentation rule is a build artifact in its own right (CDN-loaded, no bundler).
  - Decision logging — the Explainability rule introduces a parallel Decision Log deliverable for every non-trivial choice the analysis pipeline makes.
- **Scope classification**: Isolated change. The analysis touches zero tracked files in the Formbricks repository. All artifacts land in a sibling directory outside the working tree. The `git status` invariant is therefore preserved by construction.

### 0.1.3 Special Instructions and Constraints

The user-prompt rules and validation checklist constrain the analysis pipeline as follows. The Blitzy platform preserves these directives verbatim because each one is a non-negotiable acceptance criterion:

- **User Directive (Read-only execution)**: *"MUST NOT modify repository state. `git status` MUST show zero changes after completion. Scope: all git operations during this run."*
- **User Directive (Evidence threshold)**: *"Every preference or tendency claim MUST cite ≥2 distinct commit SHAs from ≥2 distinct branches where possible. Scope: Sections 3, 4, and 5 of the output document. Does not apply to Section 6 (Notable Findings)."*
- **User Directive (Quantified frequency)**: *"MUST express all frequency claims as counts, percentages, or ratios. 'Blitzy chose X in 7/10 cases (70%)' — never 'Blitzy frequently chose X.' Scope: all sections of the output document."*
- **User Directive (Project Guide primacy)**: *"When reconstructing intent behind a decision, MUST consult the corresponding branch's `blitzy/documentation/Project Guide.md` before inferring from code context. If the Project Guide prescribes a specific approach and Blitzy followed it, that is a directed decision, not a preference."*
- **User Directive (Directed vs. autonomous classification)**: *"Each identified pattern MUST be labeled as DIRECTED (Project Guide prescribed it), AUTONOMOUS (Blitzy chose it without instruction), or AMBIGUOUS (insufficient evidence to classify). Only AUTONOMOUS patterns count as preferences."*
- **User Directive (No value judgments)**: *"Zero evaluative adjectives (good, bad, optimal, suboptimal, elegant, hacky, clean, messy) in the output. The profile describes, it does not assess."*
- **User Directive (Branch state restoration)**: *"After reading each `blitzy-` branch's Project Guide, MUST checkout the previous branch before proceeding to the next. After all branches are read, MUST return to the original HEAD."*

User-provided examples and preserved phrasing:

- **User Example (frequency phrasing)**: *"'Blitzy chose X in 7/10 cases (70%)' — never 'Blitzy frequently chose X.'"* — adopted verbatim as the frequency-claim template throughout the profile.
- **User Example (Project Guide absence handling)**: *"If a `blitzy-` branch lacks `blitzy/documentation/Project Guide.md`, note the absence in the Decision Inventory and classify all commits on that branch as AMBIGUOUS for directed/autonomous determination."* — adopted verbatim as the missing-guide protocol. In this repository all 8 branches carry the guide [blitzy/documentation/Project Guide.md:branch-scoped], so the AMBIGUOUS branch path is documented but not exercised.

Methodological requirements detected:

- Minimum two occurrences before any pattern is promoted from observation to preference.
- Single-instance observations land in the Notable Findings section, not in the preference sections.
- Per-claim citations are required for sections 3, 4, and 5 of the profile.

Web search requirements: none for the analysis itself (the corpus is fully local). Web research is permitted only for CDN version validation on the reveal.js HTML deck (reveal.js 5.1.0, Mermaid 11.4.0, Lucide 0.460.0) — these versions are pinned by the Executive Presentation rule and re-verified at delivery time.

### 0.1.4 Technical Interpretation

These requirements translate to the following technical implementation strategy:

- **To enumerate the commit corpus**, the pipeline shells out to `git log --all --author="agent@blitzy.com" --pretty=format:'%H|%P|%an|%ae|%ai|%s'` and writes the rows to `data/commits_inventory.csv`. Diff bodies are fetched per-SHA with `git show --stat --pretty=format:'' <SHA>` and parsed for path lists and numstat totals.
- **To classify each commit by type**, a deterministic taxonomy is applied to the subject line and changed-file footprint: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `build`, `style`, `dep`, `merge`, `other`. The taxonomy regex set is recorded in the Decision Log so the categorization is reproducible.
- **To correlate each SHA with its originating branch**, the pipeline runs `git branch -a --contains <SHA>` and filters to `blitzy-*` + `main` refs. SHAs appearing on multiple branches are attributed to all of them; this preserves the "≥2 distinct branches" denominator for evidence-threshold checks.
- **To extract each branch's directives**, the pipeline reads `git show remotes/origin/<branch>:blitzy/documentation/Project Guide.md` (no checkout, no HEAD movement) and parses headings, bullet lists, and tables for prescribed technologies, framework choices, file targets, and explicit constraints. Results land in `data/project_guides_index.json`.
- **To classify DIRECTED vs. AUTONOMOUS vs. AMBIGUOUS**, each commit's diff is intersected with its branch's Project Guide directives. Direct matches (the Project Guide named the file, framework, or pattern) → DIRECTED. Diff content with no corresponding directive → AUTONOMOUS. Diff content where the Project Guide is silent but a plausible inference exists → AMBIGUOUS.
- **To cluster observations into tendencies**, the pipeline groups patterns by axis (architectural choice, trade-off lean, library affinity, refactoring trigger, scope behavior, commit granularity) and filters to clusters with ≥2 occurrences across ≥2 branches. Below-threshold observations are diverted to the Notable Findings track.
- **To assemble the profile deliverable**, `Blitzy_Profile_Formbricks.md` is rendered with seven mandated sections (Executive Summary, Decision Inventory, Architectural Preferences, Trade-off Profile, Behavioral Tendencies, Notable Findings, Evidence Appendix) using the patterns and the per-claim SHA list.
- **To satisfy the Explainability rule**, `Decision_Log.md` is emitted with a row for every non-trivial choice made by the pipeline (taxonomy regexes, threshold values, classification heuristics, output path, deduplication strategy).
- **To satisfy the Executive Presentation rule**, `Executive_Summary.html` is rendered as a self-contained 16-slide reveal.js deck using the Blitzy brand tokens, CDN-pinned dependencies, and Mermaid + Lucide visuals on every slide.
- **To satisfy the read-only invariant**, a verification step at the tail of the pipeline asserts `git status --porcelain` returns empty and `git rev-parse HEAD` equals the recorded baseline `c06879940eaaf0c98fbd373f1884b5852522ecc4`.

## 0.2 Repository Scope Discovery

### 0.2.1 Comprehensive File Analysis

The analysis pipeline reads from the Formbricks repository at `/tmp/blitzy/blitzy-formbricks/main_0d6e40` and writes exclusively to a sibling output directory at `/tmp/blitzy/blitzy-formbricks/blitzy-profile-output/`. The following surfaces were exhaustively inspected to confirm scope:

**Git reference surface (READ-only inputs)**

| Surface | Discovery Command | Result |
|---|---|---|
| Author commits on `main` | `git log --author="agent@blitzy.com" --oneline \| wc -l` | 208 commits [.git:`refs/heads/main`] |
| Author commits across all refs | `git log --all --author="agent@blitzy.com" --oneline \| sort -u \| wc -l` | 640 unique SHAs [.git:`refs/remotes/origin/**`] |
| `blitzy-*` branch refs | `git branch -a \| grep blitzy-` | 8 branches present [.git/packed-refs:`remotes/origin/blitzy-*`] |
| Project Guide presence | `git cat-file -e <branch>:blitzy/documentation/Project Guide.md` | 8 / 8 branches present (no AMBIGUOUS branches) [blitzy/documentation/Project Guide.md:per-branch] |

**Per-branch inventory**

| Branch | Project Guide Size | Commit Count (`agent@blitzy.com`) |
|---|---|---|
| `blitzy-1329c936-76aa-4f15-8106-ff4ddc8a5e6c` | 23,004 B | 208 |
| `blitzy-242072a5-c376-446a-af06-485d4f2946f1` | 28,141 B | 144 |
| `blitzy-62760c9b-b9b1-4afd-9103-880bac62d3a7` | 26,183 B | 67 |
| `blitzy-6caab670-2057-4154-b254-e2a0f6ba7f68` | 18,494 B | 360 |
| `blitzy-7a9d25be-d124-40bf-b715-2cf66eb7b11a` | 30,981 B | 199 |
| `blitzy-81b655fe-d459-4b7e-ace6-e1e10f71ccbe` | 26,707 B | 113 |
| `blitzy-a86e4cfe-648d-4396-8ff7-49d26abf2bb1` | 23,608 B | 142 |
| `blitzy-f7252deb-b311-42d3-b05e-998ae767c0fd` | 18,435 B | 24 |

Counts are per-branch view (commits reachable from the branch tip), not unique counts; the unique-across-`--all` total is 640.

**Repository structure surveyed for file-touch frequency analysis**

The repository is a `pnpm` + `turbo` TypeScript monorepo:

- `apps/web/` — primary Next.js application surface [.git:tree `apps/web`]
- `apps/storybook/` — component playground [.git:tree `apps/storybook`]
- `packages/cache`, `packages/database`, `packages/email`, `packages/i18n-utils`, `packages/js-core`, `packages/logger`, `packages/storage`, `packages/survey-ui`, `packages/surveys`, `packages/types`, `packages/vite-plugins`, `packages/config-eslint`, `packages/config-prettier`, `packages/config-typescript` — shared packages [.git:tree `packages/*`]
- `charts/`, `docker/`, `docker-compose.dev.yml`, `Dockerfile*` — deployment artifacts
- `docs/`, `blitzy-docs/`, `mkdocs.yml`, `openapi.yml` — documentation surfaces
- `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md` — root contributor docs
- `package.json`, `pnpm-lock.yaml`, `turbo.json`, `playwright.config.ts`, `vitest.workspace.ts`, `sonar-project.properties`, `.nvmrc`, `.eslintrc.cjs`, `.prettierrc.js` — tooling and configuration

Each path touched by any agent commit will appear in the file-touch frequency table of the Decision Inventory; no path is excluded a priori.

**Related-file discovery**

- `AGENTS.md` — root-level agent guidance; consulted as reference for the conventions Blitzy was instructed to follow
- `blitzy-docs/index.md`, `blitzy-docs/project-guide.md`, `blitzy-docs/technical-specifications.md` — top-level published guides on `main` (distinct from per-branch `blitzy/documentation/*`); referenced for the "stated intent" baseline on `main`
- `.changeset/` — release notes folder; signals when Blitzy authored a changeset entry alongside code
- `.cursor/`, `.gitpod/`, `.husky/`, `.devcontainer/` — IDE / lifecycle hooks; referenced when commits modify them

### 0.2.2 Web Search Research Conducted

No external research is needed for the commit-pattern analysis itself; the corpus is fully local and self-contained. Web research is restricted to the validation of CDN-pinned dependencies for the executive HTML deck, which the Executive Presentation rule already pins by version:

- reveal.js 5.1.0 — verify CDN URL at delivery time (`cdnjs.cloudflare.com/ajax/libs/reveal.js/5.1.0/`)
- Mermaid 11.4.0 — verify CDN URL at delivery time (`cdn.jsdelivr.net/npm/mermaid@11.4.0/`)
- Lucide 0.460.0 — verify CDN URL at delivery time (`cdn.jsdelivr.net/npm/lucide@0.460.0/`)
- Google Fonts — Inter, Space Grotesk, Fira Code families (loaded via the standard Google Fonts `<link>` mechanism)

### 0.2.3 Existing Infrastructure Assessment

- **Project structure and organization**: monorepo managed by `pnpm` workspaces (`pnpm-workspace.yaml`) and `turbo` (`turbo.json`). Conventional commits are the observed message style in the sampled `agent@blitzy.com` log (`fix(test-infra): …`, `feat: …`).
- **Existing patterns and conventions to follow**: this AAP applies them only to deliverable filenames and decision-log style. The analysis pipeline is generated from scratch — it does not pretend to fit into the Formbricks build system.
- **Build and deployment configurations**: irrelevant to the analysis; no Formbricks build is invoked. The reveal.js deck is a static HTML file with CDN dependencies and ships without a build step.
- **Testing infrastructure present**: Vitest workspace (`vitest.workspace.ts`) and Playwright (`playwright.config.ts`) exist in the repo; the analysis pipeline itself ships with a small `pytest`-equivalent self-check (Python `unittest` suite over the taxonomy regexes) that runs in-process. No test files are added to Formbricks.
- **Documentation system in use**: `mkdocs.yml` is present, plus a Mintlify-style guide under `blitzy-docs/`. The Blitzy Profile artifact is intentionally placed outside both — it is a derivative analysis, not Formbricks user documentation.

## 0.3 Scope Boundaries

### 0.3.1 Exhaustively In Scope

The following surfaces are inside the change boundary. Every output file is created in a sibling directory outside the tracked Formbricks tree so the read-only invariant on the Formbricks working tree is preserved.

**Output workspace (CREATE — outside tracked tree)**

- `<repo_parent>/blitzy-profile-output/` — the deliverable root, where:
  - `<repo_parent>` resolves to `/tmp/blitzy/blitzy-formbricks/`, sibling to `main_0d6e40/`

**Analysis scripts (CREATE — outside tracked tree)**

- `<repo_parent>/blitzy-profile-output/scripts/inventory_commits.py` — enumerate every `agent@blitzy.com` commit reachable from any ref, dedupe by SHA, write `commits_inventory.csv`
- `<repo_parent>/blitzy-profile-output/scripts/extract_diffs.py` — for each unique SHA, capture changed files, insertion/deletion counts, and the diff body, writing `commits_inventory.json`
- `<repo_parent>/blitzy-profile-output/scripts/categorize_commits.py` — apply the deterministic taxonomy (`feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `build`, `style`, `dep`, `merge`, `other`) using subject-line and path heuristics
- `<repo_parent>/blitzy-profile-output/scripts/map_commits_to_branches.py` — run `git branch -a --contains <SHA>` for each unique SHA; preserve every containing `blitzy-*` ref
- `<repo_parent>/blitzy-profile-output/scripts/load_project_guides.py` — fetch `blitzy/documentation/Project Guide.md` from every `blitzy-*` ref via `git show <ref>:<path>` (no checkout); write `project_guides_index.json` with extracted directives
- `<repo_parent>/blitzy-profile-output/scripts/classify_directed_autonomous.py` — intersect each commit's diff with its branch's Project Guide directives; emit DIRECTED / AUTONOMOUS / AMBIGUOUS labels per commit per branch
- `<repo_parent>/blitzy-profile-output/scripts/extract_patterns.py` — cluster classified commits into pattern axes (architectural choices, trade-off leans, library affinities, refactoring triggers, scope behavior, commit granularity); enforce the ≥2-occurrence ≥2-branch threshold
- `<repo_parent>/blitzy-profile-output/scripts/build_profile.py` — render `Blitzy_Profile_Formbricks.md` with the seven mandated sections and the evidence appendix
- `<repo_parent>/blitzy-profile-output/scripts/build_decision_log.py` — render `Decision_Log.md` with every non-trivial pipeline decision per the Explainability rule
- `<repo_parent>/blitzy-profile-output/scripts/build_presentation.py` — render `Executive_Summary.html` as a 16-slide reveal.js deck per the Executive Presentation rule
- `<repo_parent>/blitzy-profile-output/scripts/verify_clean_state.py` — assert `git status --porcelain` is empty and `git rev-parse HEAD` matches the recorded baseline
- `<repo_parent>/blitzy-profile-output/scripts/run.sh` — orchestration entry point that invokes the above in order
- `<repo_parent>/blitzy-profile-output/scripts/lib/taxonomy.py` — shared taxonomy regexes
- `<repo_parent>/blitzy-profile-output/scripts/lib/git_helpers.py` — read-only git wrappers
- `<repo_parent>/blitzy-profile-output/scripts/lib/prose_validator.py` — Asimov-agent rule checks for generated markdown (Prose rule)

**Intermediate data artifacts (CREATE — outside tracked tree)**

- `<repo_parent>/blitzy-profile-output/data/commits_inventory.csv` — one row per unique SHA with metadata
- `<repo_parent>/blitzy-profile-output/data/commits_inventory.json` — same plus diff body
- `<repo_parent>/blitzy-profile-output/data/branch_map.json` — SHA-to-branches index
- `<repo_parent>/blitzy-profile-output/data/project_guides_index.json` — per-branch directives extracted from each Project Guide
- `<repo_parent>/blitzy-profile-output/data/classifications.json` — DIRECTED / AUTONOMOUS / AMBIGUOUS label per commit per branch
- `<repo_parent>/blitzy-profile-output/data/patterns_extracted.json` — clustered patterns above the threshold
- `<repo_parent>/blitzy-profile-output/data/evidence_appendix.csv` — claim → SHA mapping

**Primary deliverables (CREATE — outside tracked tree)**

- `<repo_parent>/blitzy-profile-output/Blitzy_Profile_Formbricks.md` — the primary deliverable named in the user's prompt
- `<repo_parent>/blitzy-profile-output/Decision_Log.md` — mandated by the Explainability rule
- `<repo_parent>/blitzy-profile-output/Executive_Summary.html` — mandated by the Executive Presentation rule

**Workspace orientation (CREATE — outside tracked tree)**

- `<repo_parent>/blitzy-profile-output/README.md` — quick orientation: pipeline order, deliverable locations, refresh procedure

**Read-only references (REFERENCE — never modified)**

- `/tmp/blitzy/blitzy-formbricks/main_0d6e40/.git/` — entire git database via CLI commands
- `/tmp/blitzy/blitzy-formbricks/main_0d6e40/AGENTS.md` — root agent guidance (used to seed Project-Guide-equivalent directives on `main` if needed)
- `/tmp/blitzy/blitzy-formbricks/main_0d6e40/README.md`, `CONTRIBUTING.md`, `SECURITY.md` — root contributor docs (referenced for repo context only)
- `/tmp/blitzy/blitzy-formbricks/main_0d6e40/package.json`, `.nvmrc`, `pnpm-workspace.yaml`, `turbo.json` — tooling context (referenced for dependency baselines)
- `/tmp/blitzy/blitzy-formbricks/main_0d6e40/apps/`, `/tmp/blitzy/blitzy-formbricks/main_0d6e40/packages/` — file-touch frequency analysis surface
- `/tmp/blitzy/blitzy-formbricks/main_0d6e40/blitzy-docs/` — published guides on `main` (orientation only)
- `blitzy/documentation/Project Guide.md` on each of the 8 `remotes/origin/blitzy-*` refs — directive source for DIRECTED/AUTONOMOUS classification

### 0.3.2 Explicitly Out of Scope

- **Modifying any tracked file in the Formbricks repository**. The user's "Read-only execution" rule applies to "all git operations during this run." The pipeline never invokes `git add`, `git commit`, `git checkout` (for working-tree mutation), `git reset`, `git rebase`, or any tool that would alter index, HEAD, or working tree state. Project Guides are read via `git show <ref>:<path>` precisely to avoid `git checkout`.
- **Analyzing commits from authors other than `agent@blitzy.com`**. The user's "MUST NOT analyze commits by authors other than `agent@blitzy.com`" rule excludes the broader Formbricks contributor base entirely.
- **Reading `blitzy/documentation/Technical Specifications.md`** on `blitzy-*` branches. The user's prompt names only `Project Guide.md` as the directive source.
- **Reasoning about commits before evidence is established**. Single-instance observations are routed to Notable Findings, never to the architectural-preferences, trade-off-profile, or behavioral-tendencies sections.
- **Evaluating Blitzy's output**. The user's "No value judgments" rule prohibits adjectives such as `good`, `bad`, `optimal`, `suboptimal`, `elegant`, `hacky`, `clean`, `messy`. The pipeline's Prose validator includes a banned-word list that fails the build if any of these appears in the generated profile, log, or deck text.
- **Refactoring or instrumenting Formbricks source code**. No `apps/` or `packages/` files are modified.
- **Performance optimization, security enhancement, or feature work** in Formbricks. None of these were requested.
- **Adding tests to Formbricks**. The analysis pipeline has its own self-checks but does not extend `apps/web/**/*.test.*` or `packages/**/*.test.*`.
- **Publishing or committing the Blitzy Profile deliverables to the Formbricks repository**. The deliverables live outside the tracked tree and are not staged for commit.
- **Branch creation, deletion, or push operations**. Only read operations (`git log`, `git show`, `git rev-parse`, `git cat-file`, `git branch --contains`, `git status --porcelain`) are used.
- **Operations on remotes** (`git fetch`, `git pull`, `git push`). The corpus is whatever was fetched before the pipeline ran; the pipeline does not refresh remotes.
- **Mutating environment variables, secrets, or configuration outside the output directory**.

## 0.4 Dependencies

### 0.4.1 Key Packages and Runtimes

The analysis pipeline uses only runtimes and libraries already present in the execution environment. No additions, updates, or removals are required against the Formbricks `package.json` or `pnpm-lock.yaml`, and no Python virtual environment is provisioned because the pipeline relies on the standard library.

| Registry | Package / Runtime | Version | Purpose |
|---|---|---|---|
| System | `git` CLI | 2.43.0 | All commit, branch, and ref inspection (`log`, `show`, `cat-file`, `rev-parse`, `branch --contains`, `status`) [`/usr/bin/git --version`] |
| System | `python3` | 3.12.3 | Orchestration of the analysis pipeline, CSV / JSON emission, markdown and HTML generation [`/usr/bin/python3 --version`] |
| Python stdlib | `subprocess`, `csv`, `json`, `re`, `collections`, `argparse`, `pathlib`, `datetime`, `hashlib`, `textwrap`, `html`, `unittest` | bundled with 3.12 | Pipeline implementation; no third-party Python packages introduced |
| CDN | `reveal.js` | 5.1.0 | Slide framework for the executive HTML deck; loaded from `cdnjs.cloudflare.com` per the Executive Presentation rule |
| CDN | `mermaid` | 11.4.0 | Architecture and pipeline diagrams inside the deck; loaded from `cdn.jsdelivr.net` per the Executive Presentation rule |
| CDN | `lucide` | 0.460.0 | Slide icons in lieu of emoji, per the Executive Presentation rule |
| CDN | Google Fonts: Inter (400/500/600/700), Space Grotesk (500/600/700), Fira Code (400/500) | latest stable Google-served | Typography for the executive deck per the Executive Presentation rule |

Runtime version selection follows the "highest explicitly documented supported version" rule in the Environment Setup Checklist:

- The Formbricks repository pins Node 22.1.0 in `.nvmrc` [.nvmrc:1]. The analysis pipeline does not execute Node code, so this constraint applies only to any optional verification that exercises Formbricks scripts. No Formbricks scripts are invoked.
- Python is not pinned by the Formbricks repository; the analysis pipeline uses 3.12.3 (the highest explicitly documented version installed in the execution environment), which satisfies the standard-library APIs in use (`pathlib`, f-strings, type hints).
- CDN library versions are exactly those pinned by the Executive Presentation rule. The pipeline does not "round up to latest" — the rule is the upper bound.

### 0.4.2 Dependency Changes

No dependency changes are made to the Formbricks repository.

- New dependencies to add: none
- Dependencies to update: none
- Dependencies to remove: none
- Import / reference updates required: none

All analysis-pipeline imports live in scripts under `<repo_parent>/blitzy-profile-output/scripts/`, which is outside the tracked Formbricks tree and outside the Formbricks dependency graph. No Formbricks `import` or `require` statement is touched.

### 0.4.3 Compatibility Notes

- The pipeline runs against any Formbricks checkout where `git` 2.x is available; older `git` versions that lack `git branch -a --contains <SHA>` are not supported.
- The pipeline assumes that `agent@blitzy.com` is the canonical author email; if Blitzy commits under additional aliases in future runs, the inventory step is the single point of update.
- The Project Guide path (`blitzy/documentation/Project Guide.md`) is hard-coded in `load_project_guides.py`; relocating the guide on future branches requires updating that one constant and is logged as a decision in `Decision_Log.md`.

## 0.5 Design System Compliance

The Executive Presentation rule defines a proprietary design system — the **Blitzy reveal.js theme** — that governs the executive HTML deck. This sub-section catalogs the system so downstream rendering of `Executive_Summary.html` resolves every value to a system token. The other two deliverables (`Blitzy_Profile_Formbricks.md`, `Decision_Log.md`) are plain markdown and do not engage a visual design system.

### 0.5.1 System Identification

- **Library**: Blitzy reveal.js theme (proprietary, inline CSS), composed of reveal.js + Mermaid + Lucide
- **Versions**: reveal.js 5.1.0, Mermaid 11.4.0, Lucide 0.460.0 (pinned by the Executive Presentation rule)
- **Status**: to-be-loaded via CDN at presentation time (no install step, no `node_modules`)
- **Package source**: `cdnjs.cloudflare.com/ajax/libs/reveal.js/5.1.0/`, `cdn.jsdelivr.net/npm/mermaid@11.4.0/`, `cdn.jsdelivr.net/npm/lucide@0.460.0/`
- **Source**: Executive Presentation rule body (rules input), specifically the "Inline CSS" and "Technical delivery" subsections

### 0.5.2 Component Mapping

The executive deck composes reveal.js `<section>` elements with Blitzy slide-type classes and Lucide icons. The table below maps each on-deck UI element to the corresponding library construct.

| UI Element | Library Construct | Import / Markup | Props / Variant | Notes |
|---|---|---|---|---|
| Title slide | reveal.js `<section>` + `slide-title` class | `<section class="slide-title">` | hero gradient `linear-gradient(68deg, #7A6DEC 15.56%, #5B39F3 62.74%, #4101DB 84.44%)` background | Eyebrow text in Fira Code teal |
| Section divider | reveal.js `<section>` + `slide-divider` class | `<section class="slide-divider">` | dark purple `#2D1C77` or gradient background | Large centered heading + thematic Lucide icon |
| Content slide | reveal.js `<section>` (default class) | `<section>` | max 4 bullets / max 40 words / min 1 non-text visual | Body in Inter; headings in Space Grotesk |
| Closing slide | reveal.js `<section>` + `slide-closing` class | `<section class="slide-closing">` | navy `#1A105F` background | 3-6 word takeaway + max 3 bullets + brand lockup + gradient accent bar |
| KPI summary block | Blitzy KPI component | `<div class="kpi-grid"><div class="kpi-card">…</div></div>` | child slots: `.kpi-value`, `.kpi-label`, `.kpi-icon` | Use for "208 commits" / "8 branches" / "640 unique SHAs" |
| Eyebrow label | Blitzy eyebrow class | `<span class="eyebrow">` | Fira Code, teal `#94FAD5` on dark backgrounds | Used on title and divider slides |
| Accent bar | Blitzy accent bar component | `<div class="accent-bar">` | gradient `linear-gradient(90deg, #5B39F3 0%, #94FAD5 100%)` | Used on closing slide |
| Brand lockup | Blitzy brand lockup component | `<div class="brand-lockup">` | text + Lucide mark | Used on closing slide |
| Architecture diagram | Mermaid embed | `<pre class="mermaid">graph LR …</pre>` | Mermaid theme variables: `primaryColor: '#F2F0FE'`, `primaryTextColor: '#333333'`, `primaryBorderColor: '#5B39F3'`, `lineColor: '#999999'`, `secondaryColor: '#F4EFF6'` | Initialize `startOnLoad: false`; call `mermaid.run()` after reveal.js `ready` and on each `slidechanged` |
| Slide icons | Lucide SVG | `<i data-lucide="icon-name"></i>` | call `lucide.createIcons()` after `ready` and on each `slidechanged` | Replaces all emoji (zero emoji allowed per rule) |
| Slide icon row | Blitzy icon row component | `<div class="icon-row">` | hosts multiple `<i data-lucide="…"/>` | Used for visual reinforcement |
| Hero icon | Blitzy hero icon component | `<i class="hero-icon" data-lucide="…"></i>` | larger Lucide rendering | Used on title or divider slides |

Raw HTML elements (`<button>`, `<input>`, `<table>` outside reveal.js sections) are not used; this is a presentation deck, not an interactive form. Tables inside content slides are styled via the inline theme's table classes.

### 0.5.3 Token Mapping

The Executive Presentation rule prescribes the exact CSS custom properties; every value in the deck must resolve to one of these tokens. The table preserves the rule's source-of-truth definitions verbatim.

| Category | Token Name | Value | Resolution / Use Site |
|---|---|---|---|
| Color | `--blitzy-primary` | `#5B39F3` | Primary actions, links, Mermaid borders |
| Color | `--blitzy-primary-dark` | `#2D1C77` | Divider backgrounds |
| Color | `--blitzy-primary-navy` | `#1A105F` | Closing slide background |
| Color | `--blitzy-primary-light` | `#7A6DEC` | Hero gradient stop |
| Color | `--blitzy-primary-deep` | `#4101DB` | Hero gradient stop |
| Color | `--blitzy-accent-teal` | `#94FAD5` | Eyebrows, accent bar terminus |
| Color (surface) | `--blitzy-surface-0` | `#FFFFFF` | Card backgrounds |
| Color (surface) | `--blitzy-surface-1` | `#F4EFF6` | Soft surfaces |
| Color (surface) | `--blitzy-surface-2` | `#F2F0FE` | Mermaid primary color |
| Color (surface) | `--blitzy-surface-3` | `#F5F5F5` | Page neutrals |
| Color | `--blitzy-border` | `#D9D9D9` | Card and table borders |
| Color | `--blitzy-border-soft` | `rgba(91, 57, 243, 0.18)` | Subtle outlines on primary surfaces |
| Color | `--blitzy-text` | `#333333` | Body text |
| Color | `--blitzy-text-muted` | `#999999` | Captions, eyebrows on light surfaces |
| Color | `--blitzy-text-invert` | `#FFFFFF` | Text on dark backgrounds (title, divider, closing) |
| Typography | `--ff-body` | `'Inter', system-ui, sans-serif` | Body copy, KPI labels |
| Typography | `--ff-display` | `'Space Grotesk', 'Inter', sans-serif` | Slide headings |
| Typography | `--ff-mono` | `'Fira Code', 'Courier New', monospace` | Eyebrows, inline mono spans (commit SHAs) |
| Gradient | `--gradient-hero` | `linear-gradient(68deg, #7A6DEC 15.56%, #5B39F3 62.74%, #4101DB 84.44%)` | Title slide background |
| Gradient | `--gradient-divider` | `linear-gradient(135deg, #2D1C77 0%, #5B39F3 100%)` | Divider slide background |
| Gradient | `--gradient-accent-bar` | `linear-gradient(90deg, #5B39F3 0%, #94FAD5 100%)` | Closing slide accent bar |

No Figma source is attached to this project; the Figma → token resolution column is therefore not exercised. All deck values resolve to one of the listed tokens directly.

### 0.5.4 Gaps Inventory

No gaps. Every visual requirement of the executive deck — the four slide types, the KPI cards, the accent bar, the brand lockup, the Mermaid diagram styling, the Lucide icons, and the typography stack — is fully covered by the Blitzy reveal.js theme tokens and component classes prescribed by the Executive Presentation rule.

One implementation note carried forward to the decision log: Mermaid 11.x parses themes per-call rather than per-page, so the deck initializes Mermaid with `startOnLoad: false` and re-invokes `mermaid.run()` on each reveal.js `slidechanged` event to ensure diagrams render on slide entry rather than on initial page load only.

### 0.5.5 Compliance Summary

The Blitzy reveal.js theme covers 100% of the executive deck's visual requirements with zero gaps. All four mandatory slide types (`slide-title`, `slide-divider`, default content, `slide-closing`), all CSS custom properties (`--blitzy-*` plus three gradient tokens), all three typography families (Inter, Space Grotesk, Fira Code), and all three CDN dependencies (reveal.js 5.1.0, Mermaid 11.4.0, Lucide 0.460.0) are accounted for. No new tokens, no new components, no new dependencies need to be introduced. The deck ships as a single self-contained HTML file with no build step, satisfying the "Technical delivery" clause of the rule.

## 0.6 Implementation Design

### 0.6.1 Technical Approach

The Blitzy platform achieves the behavioral-profile objective by composing five purpose-built stages into a one-shot, read-only pipeline. Each stage is a Python script that reads from the git database and writes to the sibling output workspace. Stages communicate via deterministic file artifacts (CSV and JSON) so the pipeline is restartable from any stage boundary and so every intermediate result is auditable.

Logical implementation flow (sequence, not schedule):

- **First, establish the inventory baseline** by enumerating every `agent@blitzy.com` SHA reachable from `--all` refs in `inventory_commits.py` and writing one row per unique SHA to `data/commits_inventory.csv`. Diff bodies and changed-file lists are then appended into `data/commits_inventory.json` by `extract_diffs.py`. This stage answers "what was committed" with full fidelity.
- **Next, integrate categorical structure** by running `categorize_commits.py` (deterministic taxonomy regexes over subject lines and path footprints) and `map_commits_to_branches.py` (`git branch -a --contains` per SHA, filtered to `blitzy-*` and `main`). This stage answers "what kind of work" and "which branch scoped it".
- **Then, anchor intent** by loading every branch's `blitzy/documentation/Project Guide.md` through `load_project_guides.py` using `git show <ref>:<path>` so HEAD never moves. The script parses headings, bullet lists, and tables for prescribed technologies, file targets, and explicit constraints into `data/project_guides_index.json`. This stage answers "what was Blitzy told to do".
- **Then, classify directed vs. autonomous** in `classify_directed_autonomous.py`. Each commit's diff is intersected with its branch's directives. Direct overlap → DIRECTED. Diff content with no overlapping directive → AUTONOMOUS. Diff content where the guide is silent but a plausible inference exists → AMBIGUOUS. The classification is per-commit-per-branch because a single SHA may be DIRECTED on its origin branch and AMBIGUOUS on a downstream branch that inherited it via fast-forward.
- **Then, cluster observations into tendencies** in `extract_patterns.py`. Single instances are routed to a `notable_findings` bucket. Two or more occurrences across two or more branches qualify as a tendency and are emitted into `data/patterns_extracted.json` with quantified counts and ratios.
- **Finally, assemble the deliverables**: `build_profile.py` renders `Blitzy_Profile_Formbricks.md` with the seven mandated sections and the evidence appendix; `build_decision_log.py` renders `Decision_Log.md`; `build_presentation.py` renders `Executive_Summary.html`. `verify_clean_state.py` asserts `git status --porcelain` is empty and `git rev-parse HEAD == c06879940eaaf0c98fbd373f1884b5852522ecc4` before the pipeline exits zero.

Rationale for the technical decisions:

- **`git show <ref>:<path>` over `git checkout <ref>`** — eliminates the working-tree mutation risk entirely. HEAD never moves, no stash is needed, no `--detach` shows up in `reflog`.
- **Per-commit-per-branch classification rather than per-commit** — the same SHA can have different directive contexts on different branches; collapsing the dimension would force-pick a single classification arbitrarily.
- **Filesystem-as-message-bus between stages** — every intermediate is reproducible, diffable, and re-runnable; this satisfies the Explainability rule's requirement that every non-trivial choice be auditable.
- **Standard library only for Python** — zero install footprint, zero supply-chain risk, zero need to provision a virtualenv inside an analysis whose primary boundary is "do not modify state".
- **Deterministic regex taxonomy with the regex set declared in the Decision Log** — guarantees reproducibility of the count tables that anchor every frequency claim in the profile.

### 0.6.2 Component Impact Analysis

**Direct creations**

- `inventory_commits.py` — owns the unique-SHA enumeration; collapses 8 branch views into a single deduplicated list keyed by `%H`.
- `extract_diffs.py` — fetches per-SHA diffs via `git show --no-color --pretty=format:'' <SHA>`; large diffs are truncated to the first N=2,000 lines per file with a continuation marker logged for the Decision Log.
- `categorize_commits.py` — applies the taxonomy regexes; ambiguous matches surface in a tie-break log so the Decision Log records every contested categorization.
- `map_commits_to_branches.py` — single source of truth for SHA → branch mapping; consumed by every downstream stage that needs branch context.
- `load_project_guides.py` — parses each Project Guide into a directive list with location anchors (heading path + line range) so the classifier can cite directives back to the guide.
- `classify_directed_autonomous.py` — implements the DIRECTED / AUTONOMOUS / AMBIGUOUS decision tree; emits a per-classification confidence score for the Decision Log.
- `extract_patterns.py` — enforces the ≥2-occurrence ≥2-branch threshold by construction; below-threshold observations are diverted to `notable_findings`.
- `build_profile.py` — owns the markdown rendering for the seven profile sections; assembles the evidence appendix table by joining `patterns_extracted.json` with `commits_inventory.csv`.
- `build_decision_log.py` — owns the decision log markdown rendering; pulls decisions from every other stage's structured `decisions` field.
- `build_presentation.py` — owns the reveal.js HTML rendering using the Blitzy brand tokens; embeds Mermaid sources as `<pre class="mermaid">` blocks.
- `verify_clean_state.py` — final invariant check; exits non-zero if either git invariant fails.
- `lib/taxonomy.py`, `lib/git_helpers.py`, `lib/prose_validator.py` — shared utilities; the Prose validator implements the Asimov-agent rules for the generated text (sentence length cap, banned-word list, hedge-word detection).

**Indirect impacts and dependencies**

- The Formbricks repository is **not** modified. The `.git/` database is read-only inputs only. No `apps/`, `packages/`, `charts/`, `docker/`, `docs/`, `blitzy-docs/`, or root configuration files are touched.
- The Project Guides on the `blitzy-*` branches are read in place; no per-branch checkout is performed.
- `AGENTS.md` on `main` is referenced for repo-level conventions but not parsed as a directive source; only per-branch `Project Guide.md` files feed the classifier.

**New components introduction**

- A full Python analysis pipeline (12 scripts + 3 library modules) is introduced in `<repo_parent>/blitzy-profile-output/scripts/`.
- A data directory at `<repo_parent>/blitzy-profile-output/data/` holds seven intermediate artifacts.
- Three primary deliverables and one orientation README live in `<repo_parent>/blitzy-profile-output/`.
- Rationale: the analysis must be reproducible, auditable, and read-only. Embedding the tooling inside the Formbricks tree would violate the read-only invariant; a sibling output directory keeps the boundary explicit.

### 0.6.3 User Interface Design

The only user-facing surface is `Executive_Summary.html`. Its goals, derived from the Executive Presentation rule and the user's success criteria, are:

- Translate a behavioral-analysis artifact into 12-18 slides (target 16) consumable by non-technical leadership.
- Cover scope of work, business value, architectural impact, risks, and onboarding within the slide budget.
- Use the Blitzy brand visual identity throughout (no off-system colors, no emoji, no fenced code blocks).
- Provide at least one non-text visual element on every slide — KPI card, Mermaid diagram, styled table, or Lucide icon.

Slide ordering plan (16 slides, matches the rule's "Slide ordering convention"):

- Slide 1 — Title: "Blitzy Profile — Formbricks", scope eyebrow, audience framing, hero gradient background
- Slide 2 — Content: headline findings (top 3 falsifiable AUTONOMOUS preferences) as a KPI grid
- Slide 3 — Content: Mermaid architecture diagram of the analysis pipeline (5 stages, arrows)
- Slide 4 — Section divider: "What was analyzed", Lucide `git-branch` icon
- Slide 5 — Content: corpus inventory KPIs (commits, branches, Project Guides, unique SHAs)
- Slide 6 — Content: commits-by-type styled table
- Slide 7 — Section divider: "What Blitzy chose", Lucide `compass` icon
- Slide 8 — Content: architectural preferences summary with supporting SHA counts
- Slide 9 — Content: trade-off profile (Mermaid quadrant or radial)
- Slide 10 — Section divider: "How Blitzy works", Lucide `git-commit` icon
- Slide 11 — Content: behavioral tendencies (commit granularity, scope behavior, refactoring triggers)
- Slide 12 — Content: notable findings (single-instance items) styled table
- Slide 13 — Section divider: "Risks and onboarding", Lucide `shield-alert` icon
- Slide 14 — Content: validation framework table — every checklist item with a tick
- Slide 15 — Content: onboarding next steps (re-run procedure, refresh cadence)
- Slide 16 — Closing: 5-word takeaway, brand lockup, accent bar, navy `#1A105F` background

Each slide's text body is capped at 40 words; bullets are capped at 4; no slide is text-only. Mermaid initialization re-runs on `slidechanged` so diagrams render correctly when navigating.

### 0.6.4 User-Provided Examples Integration

- **User Example (frequency phrasing)**: *"'Blitzy chose X in 7/10 cases (70%)' — never 'Blitzy frequently chose X.'"* — this template is implemented as a Prose-validator banned-pattern rule: any sentence in the generated profile containing an unquantified frequency adverb (`frequently`, `often`, `sometimes`, `rarely`, `occasionally`) triggers a build failure that names the offending sentence and demands a count / percentage / ratio rewrite.
- **User Example (Project Guide absence handling)**: *"If a `blitzy-` branch lacks `blitzy/documentation/Project Guide.md`, note the absence in the Decision Inventory and classify all commits on that branch as AMBIGUOUS for directed/autonomous determination."* — implemented in `load_project_guides.py`: if `git cat-file -e <branch>:blitzy/documentation/Project Guide.md` exits non-zero, the branch is flagged with `project_guide_present=false` and every SHA reachable from that branch carries an automatic AMBIGUOUS label until evidence promotes it. The Decision Inventory section of the profile lists such branches explicitly. In this repository the path is exercised defensively but never triggered, since all 8 branches carry the guide.

### 0.6.5 Critical Implementation Details

- **Deduplication strategy**: SHAs are the canonical identity. The pipeline never collapses two branches' identical commits into one observation; instead it records every branch-commit pairing so the per-branch denominator for AUTONOMOUS-rate ratios is correct.
- **Branch traversal protocol**: `load_project_guides.py` never invokes `git checkout`. It reads each branch's Project Guide via `git show remotes/origin/<branch>:blitzy/documentation/Project Guide.md`. The user's rule about "checkout the previous branch before proceeding to the next" applies to any pipeline path that requires real checkout — none does. The protocol is documented in the Decision Log as a deliberate deviation from the literal-checkout phrasing.
- **Data flow modifications**: each stage writes a deterministic, version-stamped header into its output file (`# generated by <script>@<timestamp> against HEAD <SHA>`) so re-runs are distinguishable without git involvement.
- **Error handling and edge cases**:
  - Empty diff (a merge or revert with no content delta): commit is categorized `merge` or `other` and excluded from line-count averages.
  - Binary file diffs: counted in the changed-files total but excluded from insertions / deletions averages.
  - Project Guide parser fails on a branch: the branch is treated as if its Project Guide were absent (AMBIGUOUS-by-default), and the parser failure is logged.
  - Mermaid render failure in the deck: the slide gracefully falls back to a styled table rendering of the same data structure; the rule's "at least one non-text visual element" invariant is preserved.
- **Performance considerations**: 640 unique SHAs × per-SHA `git show` is the dominant cost. The pipeline streams `git log --name-status --numstat` once at the start to amortize the per-SHA cost; diff bodies are fetched lazily only for commits that survive into pattern extraction.
- **Security considerations**: the pipeline never executes arbitrary code from the repository. It does not source `.env` files, does not invoke `pnpm`, `npm`, or any project build, and does not open files via shell evaluation. All file access goes through Python's `pathlib` with explicit paths.
- **Prose-rule integration**: the Prose validator (`lib/prose_validator.py`) runs after every markdown render. It applies the Asimov-agent principles to all generated text (A1 plate-glass clarity → 30-word sentence cap, A2 short words → flag any 4+ syllable word with a shorter synonym, A8 anticipate reader questions → flag unsupported claims). Hard violations fail the build. The blog rules B1 (no em dashes) and B2 (no "It / This" starters) are likewise applied to the deck's body text where short-form rules govern.

## 0.7 File Transformation Mapping

### 0.7.1 File-by-File Execution Plan

Every file the pipeline touches is listed below. The convention follows the prompt: target file first, then transformation mode, then source/reference, then purpose. `<repo>` resolves to `/tmp/blitzy/blitzy-formbricks/main_0d6e40/`. `<repo_parent>` resolves to `/tmp/blitzy/blitzy-formbricks/`.

| Target File | Transformation | Source File / Reference | Purpose / Changes |
|---|---|---|---|
| `<repo_parent>/blitzy-profile-output/scripts/inventory_commits.py` | CREATE | — | Enumerate every `agent@blitzy.com` SHA reachable from `--all` refs; dedupe by `%H`; emit `data/commits_inventory.csv` |
| `<repo_parent>/blitzy-profile-output/scripts/extract_diffs.py` | CREATE | — | For each unique SHA, capture changed files, insertions/deletions, and diff body; emit `data/commits_inventory.json` |
| `<repo_parent>/blitzy-profile-output/scripts/categorize_commits.py` | CREATE | — | Apply taxonomy regexes from `lib/taxonomy.py`; emit a `category` column on every inventory row |
| `<repo_parent>/blitzy-profile-output/scripts/map_commits_to_branches.py` | CREATE | — | Run `git branch -a --contains <SHA>` per unique SHA; emit `data/branch_map.json` keyed by SHA |
| `<repo_parent>/blitzy-profile-output/scripts/load_project_guides.py` | CREATE | `<repo>/blitzy/documentation/Project Guide.md` on each `remotes/origin/blitzy-*` ref (READ via `git show`) | Fetch and parse every per-branch Project Guide; emit `data/project_guides_index.json` |
| `<repo_parent>/blitzy-profile-output/scripts/classify_directed_autonomous.py` | CREATE | `data/commits_inventory.json`, `data/branch_map.json`, `data/project_guides_index.json` | Intersect each commit's diff with its branch's directives; emit `data/classifications.json` |
| `<repo_parent>/blitzy-profile-output/scripts/extract_patterns.py` | CREATE | `data/classifications.json`, `data/commits_inventory.csv` | Cluster classified commits into pattern axes; enforce ≥2-occurrence ≥2-branch threshold; emit `data/patterns_extracted.json` |
| `<repo_parent>/blitzy-profile-output/scripts/build_profile.py` | CREATE | `data/patterns_extracted.json`, `data/commits_inventory.csv`, `data/classifications.json` | Render `Blitzy_Profile_Formbricks.md` with seven sections + evidence appendix |
| `<repo_parent>/blitzy-profile-output/scripts/build_decision_log.py` | CREATE | every pipeline stage's structured `decisions` field | Render `Decision_Log.md` with decided / alternatives / why / risks |
| `<repo_parent>/blitzy-profile-output/scripts/build_presentation.py` | CREATE | `Blitzy_Profile_Formbricks.md`, `Decision_Log.md` | Render `Executive_Summary.html` as a 16-slide reveal.js deck using the Blitzy brand tokens |
| `<repo_parent>/blitzy-profile-output/scripts/verify_clean_state.py` | CREATE | `<repo>/.git/` (READ) | Assert `git status --porcelain` is empty and `git rev-parse HEAD == c06879940eaaf0c98fbd373f1884b5852522ecc4`; exit non-zero otherwise |
| `<repo_parent>/blitzy-profile-output/scripts/run.sh` | CREATE | — | Orchestrate the stages in order; halts on first non-zero exit |
| `<repo_parent>/blitzy-profile-output/scripts/lib/taxonomy.py` | CREATE | observed commit subject samples from this AAP's discovery (e.g., `fix(test-infra):`, `feat:`, `fix(docs):`) | Hosts the deterministic taxonomy regexes |
| `<repo_parent>/blitzy-profile-output/scripts/lib/git_helpers.py` | CREATE | — | Read-only git wrappers (`git show`, `git log`, `git cat-file`, `git branch --contains`, `git rev-parse`, `git status`) with subprocess-level guarantees of no working-tree mutation |
| `<repo_parent>/blitzy-profile-output/scripts/lib/prose_validator.py` | CREATE | Prose rule (Asimov agent principles, banned-word list, frequency-adverb detector) | Validates all generated markdown; fails the build on hard violations |
| `<repo_parent>/blitzy-profile-output/data/commits_inventory.csv` | CREATE | output of `inventory_commits.py` | One row per unique `agent@blitzy.com` SHA |
| `<repo_parent>/blitzy-profile-output/data/commits_inventory.json` | CREATE | output of `extract_diffs.py` | Same as CSV plus parsed diff body |
| `<repo_parent>/blitzy-profile-output/data/branch_map.json` | CREATE | output of `map_commits_to_branches.py` | SHA → containing-branch list |
| `<repo_parent>/blitzy-profile-output/data/project_guides_index.json` | CREATE | output of `load_project_guides.py` | Per-branch directives, prescriptions, and constraints |
| `<repo_parent>/blitzy-profile-output/data/classifications.json` | CREATE | output of `classify_directed_autonomous.py` | DIRECTED / AUTONOMOUS / AMBIGUOUS labels per commit per branch |
| `<repo_parent>/blitzy-profile-output/data/patterns_extracted.json` | CREATE | output of `extract_patterns.py` | Clustered patterns with quantified counts and ratios |
| `<repo_parent>/blitzy-profile-output/data/evidence_appendix.csv` | CREATE | output of `build_profile.py` | Claim → supporting SHA list, written as a side artifact of profile assembly |
| `<repo_parent>/blitzy-profile-output/Blitzy_Profile_Formbricks.md` | CREATE | output of `build_profile.py` | **Primary deliverable** — Executive Summary, Decision Inventory, Architectural Preferences, Trade-off Profile, Behavioral Tendencies, Notable Findings, Evidence Appendix |
| `<repo_parent>/blitzy-profile-output/Decision_Log.md` | CREATE | output of `build_decision_log.py` | Explainability-rule deliverable: every non-trivial pipeline choice as a row in a Markdown table |
| `<repo_parent>/blitzy-profile-output/Executive_Summary.html` | CREATE | output of `build_presentation.py` | Executive Presentation rule deliverable: 16-slide reveal.js HTML deck using Blitzy brand tokens |
| `<repo_parent>/blitzy-profile-output/README.md` | CREATE | — | Orientation document: pipeline order, deliverable locations, refresh procedure |
| `<repo>/.git/**` | REFERENCE | `<repo>/.git/` | Read-only inspection: `git log`, `git show`, `git cat-file`, `git branch --contains`, `git rev-parse`, `git status --porcelain` |
| `<repo>/blitzy/documentation/Project Guide.md` (on each `remotes/origin/blitzy-*` ref) | REFERENCE | branch-scoped via `git show <ref>:<path>` | Directive source for DIRECTED / AUTONOMOUS classification |
| `<repo>/AGENTS.md` | REFERENCE | path on `main` | Repo-level agent conventions; consulted for orientation only, not parsed as directives |
| `<repo>/README.md` | REFERENCE | path on `main` | Repo orientation |
| `<repo>/package.json`, `<repo>/pnpm-lock.yaml`, `<repo>/turbo.json`, `<repo>/.nvmrc`, `<repo>/pnpm-workspace.yaml` | REFERENCE | path on `main` | Tooling baseline; consulted for environment context only |
| `<repo>/apps/**`, `<repo>/packages/**`, `<repo>/docs/**`, `<repo>/blitzy-docs/**`, `<repo>/charts/**`, `<repo>/docker/**` | REFERENCE | paths on `main` and on commits' touched-file lists | Touched-path frequency analysis surface |

No file in `<repo>/**` is UPDATEd or DELETEd. The transformation matrix above is exhaustive — there is no "pending" or "to-be-discovered" entry.

### 0.7.2 New Files Detail

- **`scripts/inventory_commits.py`** — Content type: source (Python). Based on: standard `subprocess` + `csv` patterns. Key sections: `enumerate_unique_shas()`, `fetch_commit_metadata(sha)`, `write_inventory_csv()`. Inputs: `<repo>/.git/`. Outputs: `data/commits_inventory.csv`.

- **`scripts/extract_diffs.py`** — Content type: source (Python). Key sections: `fetch_diff(sha)` with truncation marker for diffs over N=2,000 lines per file, `parse_numstat(sha)`, `write_inventory_json()`. Inputs: `data/commits_inventory.csv`. Outputs: `data/commits_inventory.json`.

- **`scripts/categorize_commits.py`** — Content type: source (Python). Key sections: `apply_taxonomy(row)` using regexes from `lib/taxonomy.py`, `tie_break(matches)` for multi-match cases, `write_categorized()`. Inputs: `data/commits_inventory.json`. Outputs: updated `data/commits_inventory.json` with a `category` column.

- **`scripts/map_commits_to_branches.py`** — Content type: source (Python). Key sections: `containing_branches(sha)` calling `git branch -a --contains <SHA>` and filtering to `blitzy-*`+`main`. Inputs: SHA list. Outputs: `data/branch_map.json`.

- **`scripts/load_project_guides.py`** — Content type: source (Python). Key sections: `list_blitzy_branches()` via `git for-each-ref refs/remotes/origin/blitzy-*`, `fetch_guide(branch)` via `git show <ref>:blitzy/documentation/Project Guide.md`, `parse_directives(text)` extracting headings, bullet directives, and constraint tables. Inputs: branch list. Outputs: `data/project_guides_index.json`.

- **`scripts/classify_directed_autonomous.py`** — Content type: source (Python). Key sections: `classify(sha, branch)` returning `(label, confidence, evidence)` where `label ∈ {DIRECTED, AUTONOMOUS, AMBIGUOUS}`. Inputs: `commits_inventory.json`, `branch_map.json`, `project_guides_index.json`. Outputs: `data/classifications.json`.

- **`scripts/extract_patterns.py`** — Content type: source (Python). Key sections: `cluster_architectural(rows)`, `cluster_trade_offs(rows)`, `cluster_library_affinities(rows)`, `cluster_refactoring_triggers(rows)`, `cluster_scope_behavior(rows)`, `cluster_commit_granularity(rows)`, `enforce_thresholds(clusters)`. Inputs: classifications. Outputs: `data/patterns_extracted.json`.

- **`scripts/build_profile.py`** — Content type: source (Python). Key sections: `render_executive_summary()`, `render_decision_inventory()`, `render_architectural_preferences()`, `render_trade_off_profile()`, `render_behavioral_tendencies()`, `render_notable_findings()`, `render_evidence_appendix()`. Inputs: pattern + inventory data. Outputs: `Blitzy_Profile_Formbricks.md`, `data/evidence_appendix.csv`.

- **`scripts/build_decision_log.py`** — Content type: source (Python). Key sections: `collect_decisions()` aggregating from every stage's `decisions.json` sidecar, `render_decision_table()` producing the Markdown table `| Decision | Alternatives | Rationale | Risk |`. Inputs: per-stage decision sidecars. Outputs: `Decision_Log.md`.

- **`scripts/build_presentation.py`** — Content type: source (Python emitting HTML). Key sections: `slide_title()`, `slide_divider(title, icon)`, `slide_content(...)`, `slide_closing(...)`, `inline_theme_css()`, `mermaid_init_script()`, `lucide_init_script()`. Outputs: `Executive_Summary.html` (single self-contained file).

- **`scripts/verify_clean_state.py`** — Content type: source (Python). Key sections: `assert_clean_porcelain()`, `assert_head_matches(baseline_sha)`. Inputs: live git database. Outputs: exit code 0 on success, non-zero on failure; prints offending state to stderr.

- **`scripts/run.sh`** — Content type: shell. Key sections: `set -euo pipefail`, ordered invocations of the 11 stages above, final `verify_clean_state.py` gate.

- **`scripts/lib/taxonomy.py`** — Content type: source (Python). Key sections: regex map for `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `build`, `style`, `dep`, `merge`, `other`. Each regex has a docstring stating its rationale (logged into the Decision Log).

- **`scripts/lib/git_helpers.py`** — Content type: source (Python). Key sections: thin wrappers around `subprocess.run([...], check=True, text=True, capture_output=True)` for `git log`, `git show`, `git cat-file`, `git rev-parse`, `git status --porcelain`, `git branch -a --contains`. Asserts `cwd` is the repo root before each call.

- **`scripts/lib/prose_validator.py`** — Content type: source (Python). Key sections: `validate(markdown_text, agent="Asimov")`, banned-word list (`good`, `bad`, `optimal`, `suboptimal`, `elegant`, `hacky`, `clean`, `messy`), unquantified-frequency-adverb list (`frequently`, `often`, `sometimes`, `rarely`, `occasionally`), 30-word sentence cap (A2). Returns verdict (`CLEAN`, `NEEDS WORK`, `ROUGH DRAFT`) plus violation list.

- **`Blitzy_Profile_Formbricks.md`** — Content type: documentation (Markdown). Sections per the user's prompt: Executive Summary (3-5 sentences), Decision Inventory (quantified table), Architectural Preferences (≥3 falsifiable AUTONOMOUS claims, each with ≥2 SHAs), Trade-off Profile (≥2 trade-off axes), Behavioral Tendencies, Notable Findings, Evidence Appendix.

- **`Decision_Log.md`** — Content type: documentation (Markdown). Single Markdown table with columns Decision / Alternatives / Rationale / Risk per the Explainability rule. Bidirectional traceability matrix not required (this is an analysis, not a migration); the absence is itself logged as a decision.

- **`Executive_Summary.html`** — Content type: self-contained HTML. 16 reveal.js slides per the Executive Presentation rule. Inline CSS holds the full Blitzy theme; Mermaid and Lucide loaded via pinned CDN URLs; Google Fonts loaded via `<link>`.

- **`README.md`** — Content type: documentation (Markdown). Sections: Quickstart (`bash scripts/run.sh`), Deliverables (file list with descriptions), Refresh Procedure (how to re-run when new `agent@blitzy.com` commits land), Read-only Guarantee (the git invariants and verification gate).

### 0.7.3 Files to Modify Detail

None. The pipeline does not modify any file inside `<repo>/`. The Decision Log records this as a deliberate decision (the alternative — embedding the pipeline inside `<repo>/scripts/` — was rejected because it would violate the user's read-only rule).

### 0.7.4 Configuration and Documentation Updates

No configuration in `<repo>/` is changed. The only "configuration" the pipeline owns is `scripts/lib/taxonomy.py` (regex declarations) and `scripts/run.sh` (stage order) — both inside the output workspace. The orientation `README.md` in the output workspace serves as the documentation surface for the analysis pipeline itself.

### 0.7.5 Cross-File Dependencies

- `inventory_commits.py` → `extract_diffs.py` → `categorize_commits.py` are a strict left-to-right dependency: each consumes the prior's output. The orchestrator (`run.sh`) enforces the order.
- `load_project_guides.py` and `map_commits_to_branches.py` are independent of the diff pipeline and run in parallel under `run.sh` if needed.
- `classify_directed_autonomous.py` joins the diff pipeline output with the branch map and project guide index.
- `extract_patterns.py` depends on classifications + inventory.
- `build_profile.py` depends on patterns + inventory + classifications.
- `build_decision_log.py` depends on the `decisions.json` sidecars emitted by every prior stage.
- `build_presentation.py` depends on the rendered profile and decision log so it can summarize them.
- `verify_clean_state.py` is the final gate; every other stage must complete before it runs.
- Import / reference updates: all imports live within `scripts/lib/`; no `import` from outside `<repo_parent>/blitzy-profile-output/`.

## 0.8 Rules

Two rule sets bind this work: the user's seven prompt-level rules and the three project-level rules supplied via the implementation rules input. Both are preserved verbatim where they constrain output and accompanied by an implementation note that names the script or scope responsible for enforcement.

### 0.8.1 User-Specified Rules (from the prompt)

- **User Directive (Read-only execution)**: *"MUST NOT modify repository state. `git status` MUST show zero changes after completion. Scope: all git operations during this run."*
  - Implementation: `lib/git_helpers.py` wraps every git invocation; no command in the wrapper set mutates state. `verify_clean_state.py` asserts `git status --porcelain` is empty at pipeline exit.

- **User Directive (Evidence threshold)**: *"Every preference or tendency claim MUST cite ≥2 distinct commit SHAs from ≥2 distinct branches where possible. Scope: Sections 3, 4, and 5 of the output document. Does not apply to Section 6 (Notable Findings)."*
  - Implementation: `extract_patterns.py` enforces the threshold at cluster construction time; below-threshold observations are routed to the Notable Findings bucket. `build_profile.py` refuses to emit a preference row whose evidence list has fewer than two SHAs and fewer than two distinct branches.

- **User Directive (Quantified frequency)**: *"MUST express all frequency claims as counts, percentages, or ratios. 'Blitzy chose X in 7/10 cases (70%)' — never 'Blitzy frequently chose X.' Scope: all sections of the output document."*
  - Implementation: `lib/prose_validator.py` carries a banned-word list including `frequently`, `often`, `sometimes`, `rarely`, `occasionally` and fails the build when any such adverb appears outside a quoted user example.

- **User Directive (Project Guide primacy)**: *"When reconstructing intent behind a decision, MUST consult the corresponding branch's `blitzy/documentation/Project Guide.md` before inferring from code context. If the Project Guide prescribes a specific approach and Blitzy followed it, that is a directed decision, not a preference. Scope: all pattern classification in Step 3."*
  - Implementation: `classify_directed_autonomous.py` reads from `data/project_guides_index.json` before it touches the diff body. Diff-derived inference cannot promote a commit to AUTONOMOUS if a Project Guide directive overlaps.

- **User Directive (Directed vs. autonomous classification)**: *"Each identified pattern MUST be labeled as DIRECTED (Project Guide prescribed it), AUTONOMOUS (Blitzy chose it without instruction), or AMBIGUOUS (insufficient evidence to classify). Only AUTONOMOUS patterns count as preferences. Scope: Sections 3 and 5."*
  - Implementation: classifications are first-class in `data/classifications.json`. `extract_patterns.py` filters Architectural Preferences (Section 3) and Behavioral Tendencies (Section 5) to AUTONOMOUS-only rows; DIRECTED rows still feed the Decision Inventory but never the preference tables.

- **User Directive (No value judgments)**: *"Zero evaluative adjectives (good, bad, optimal, suboptimal, elegant, hacky, clean, messy) in the output. The profile describes, it does not assess. Scope: entire output document."*
  - Implementation: `lib/prose_validator.py` carries an exact-string banned-adjective list; a single occurrence fails the build with the offending sentence quoted.

- **User Directive (Branch state restoration)**: *"After reading each `blitzy-` branch's Project Guide, MUST checkout the previous branch before proceeding to the next. After all branches are read, MUST return to the original HEAD. Scope: all branch traversal operations."*
  - Implementation: `load_project_guides.py` uses `git show <ref>:<path>` so HEAD never moves; the restoration requirement is satisfied by construction. The Decision Log records this as a deliberate deviation from the literal-checkout phrasing with the rationale that "checkout" is a means and "return to original HEAD" is the end — the end is achieved more reliably by never moving HEAD in the first place.

### 0.8.2 Project-Level Rules (from the implementation rules input)

- **Project Rule (Explainability)**: every non-trivial implementation decision must be documented with rationale; deliver a Markdown decision log table with what was decided, what alternatives existed, why this choice was made, and what risks it carries; for migrations or refactors, include a bidirectional traceability matrix mapping source constructs to target implementations (100% coverage, no gaps); any deviation from a literal or obvious interpretation of the requirements must have an explicit entry in the decision log; do not embed rationale in code comments — the decision log is the single source of truth for "why" decisions.
  - Implementation: `Decision_Log.md` is a primary deliverable; every stage of the pipeline emits a `decisions.json` sidecar that `build_decision_log.py` aggregates. Notable deviations logged: `git show` over `git checkout` (Section 0.8.1, last bullet); per-commit-per-branch classification rather than per-commit; the choice to omit a bidirectional traceability matrix because this is an analysis rather than a migration (the omission itself is logged as a row).

- **Project Rule (Executive Presentation)**: every deliverable must include an executive summary as a single self-contained reveal.js HTML file independent of any other documentation; audience is non-technical leadership; must cover scope, business value, architectural change, risks and mitigations, and onboarding; 12-18 slides total (target 16); four slide types (`slide-title`, `slide-divider`, content, `slide-closing`); every slide must include at least one non-text visual element; zero emoji — use Lucide SVG icons; no fenced code blocks inside slides; Blitzy visual identity tokens, typography stack, Mermaid theme variables, reveal.js / Mermaid / Lucide versions, and inline CSS custom properties as specified.
  - Implementation: `Executive_Summary.html` is a primary deliverable rendered by `build_presentation.py`. Sub-section 0.5 of this AAP catalogs the full Blitzy reveal.js theme (tokens, components, gradients, typography, CDN versions). The render path enforces the 12-18 slide count, the slide-type sequence (title → content → divider/content alternation → closing), and the "at least one non-text visual per slide" invariant.

- **Project Rule (Prose)**: validate all generated text for clarity, directness, and reader respect; flag violations of the named principles (V1-V12 for Vonnegut, A1-A10 for Asimov, B1-B5 blog rules); default to Vonnegut; switch to Asimov for technical documentation, specs, or structured explanations; emit verdict (CLEAN, NEEDS WORK, ROUGH DRAFT) plus principle-by-principle scorecard; for each violation, provide offending passage, principle name, concrete rewrite, and rationale.
  - Implementation: `lib/prose_validator.py` runs after every markdown render. The Asimov agent is selected for the profile, the decision log, and the body text of the deck (all technical documentation). Hard violations fail the build; soft violations emit a warning and the offending passage is captured for human review.

### 0.8.3 Cross-Rule Compliance Matrix

| Rule | Enforcement Site | Failure Mode | Audit Artifact |
|---|---|---|---|
| Read-only execution | `verify_clean_state.py` | Non-zero exit | `git status --porcelain` snapshot in stderr |
| Evidence threshold | `extract_patterns.py` + `build_profile.py` | Refuse to emit row | `evidence_appendix.csv` shows every claim → SHA list |
| Quantified frequency | `lib/prose_validator.py` | Build fails | violation list in `Decision_Log.md` |
| Project Guide primacy | `classify_directed_autonomous.py` | Guide read before diff inference | `classifications.json` field `evidence_source` |
| DIRECTED / AUTONOMOUS / AMBIGUOUS | `classify_directed_autonomous.py` + `build_profile.py` | Preference tables exclude non-AUTONOMOUS | `classifications.json` |
| No value judgments | `lib/prose_validator.py` | Build fails | violation list in `Decision_Log.md` |
| Branch state restoration | `load_project_guides.py` | n/a (HEAD never moves) | `Decision_Log.md` deliberate-deviation row |
| Explainability | `build_decision_log.py` | Missing decision row blocks delivery | `Decision_Log.md` |
| Executive Presentation | `build_presentation.py` | Slide count outside 12-18 or text-only slide fails the render | `Executive_Summary.html` slide count footer |
| Prose | `lib/prose_validator.py` | Hard violation fails build | scorecard appended to `Decision_Log.md` |

## 0.9 Special Instructions

### 0.9.1 Special Execution Instructions

- **Read-only mandate**: the pipeline is documentation-only with respect to the Formbricks repository. No `git add`, `git commit`, `git checkout` (mutating), `git reset`, `git rebase`, `git stash`, `git push`, or any working-tree write happens at any point. The user's `git status` invariant is asserted at pipeline exit.
- **Skip deployment**: no Formbricks build or deploy is invoked. No `pnpm install`, `pnpm build`, `pnpm test`, `turbo run`, `next build`, or `vitest` call is made against the Formbricks tree.
- **Skip Formbricks testing**: the analysis ships its own self-checks (Python `unittest` over the taxonomy regexes) but does not extend or run Formbricks tests. The `vitest.workspace.ts` and `playwright.config.ts` files are read for context only.
- **Tools mentioned and engaged**:
  - `git` 2.43.0 CLI — sole interface to the commit corpus
  - Python 3.12.3 standard library — pipeline implementation
  - reveal.js 5.1.0, Mermaid 11.4.0, Lucide 0.460.0 — CDN-loaded for the deck
- **Tools explicitly not engaged**: any Formbricks workspace tool (`pnpm`, `turbo`, `next`, `vite`, `vitest`, `playwright`, `prisma`, `eslint`, `prettier`, `husky`). The pipeline is intentionally orthogonal.
- **Quality and style requirements**: Asimov-agent Prose rules apply to all generated markdown; specifically A1 plate-glass clarity, A2 short words and simple structures, A3 logical sequence, A8 anticipate reader questions. Blog rules B1 (no em dashes) and B2 (no "It"/"This" starters) apply to the deck's short-form body text.
- **Code review and approval**: the Decision Log row "deviations from literal requirements" surfaces every interpretive choice for review; downstream consumers can challenge any row.
- **Deployment and rollout**: not applicable; the deliverables are standalone files. The orientation `README.md` documents how to re-run the pipeline when new `agent@blitzy.com` commits land.

### 0.9.2 Constraints and Boundaries

- **Technical constraint (commit identity)**: `agent@blitzy.com` is the canonical author email. Any future Blitzy alias must be added to `inventory_commits.py` to be included.
- **Technical constraint (Project Guide path)**: the rule specifies `blitzy/documentation/Project Guide.md`. The pipeline hard-codes this path; relocations on future branches require a single-point update.
- **Technical constraint (read-only git)**: the wrapper in `lib/git_helpers.py` only exposes read commands. There is no escape hatch — if a future need arises to checkout, the rule first has to be revisited.
- **Process constraint (single-instance handling)**: an observation seen only once is never promoted to a preference. It lands in Notable Findings. This rule is enforced by `extract_patterns.py` and is not overridable.
- **Process constraint (no inference without evidence)**: every claim in Sections 3-5 of the profile cites ≥2 SHAs from ≥2 branches; the citation is produced from `data/evidence_appendix.csv`, which `build_profile.py` cannot bypass.
- **Output constraint (deliverable count)**: exactly three primary deliverables — `Blitzy_Profile_Formbricks.md`, `Decision_Log.md`, `Executive_Summary.html` — plus the orientation `README.md`. The pipeline does not silently produce additional deliverables.
- **Output constraint (no value judgments)**: every generated line passes the Prose validator's banned-adjective check before it ships.
- **Output constraint (location)**: all deliverables live under `<repo_parent>/blitzy-profile-output/`. None of them is staged for commit to Formbricks.
- **Compatibility constraint (git version)**: `git branch -a --contains <SHA>` is required; `git` ≥ 2.7 satisfies this. The installed 2.43.0 is well clear of the floor.
- **Compatibility constraint (browser)**: the executive deck targets a modern browser with ES2020 support (reveal.js 5.1.0 baseline). The deck is self-contained — opening the file directly in a browser must render Mermaid and Lucide without errors.
- **Validation framework (the user's checklist)** preserved verbatim:
  - *"All `agent@blitzy.com` commits in the repo are included in the analysis (verify count against `git log --author="agent@blitzy.com" --oneline \| wc -l`)"*
  - *"All `blitzy-` prefixed branches are enumerated and their Project Guides read (verify count against `git branch -a \| grep blitzy-`)"*
  - *"Every claim in Sections 3-5 cites ≥2 commit SHAs"*
  - *"Zero unquantified frequency claims in the document"*
  - *"Every preference is classified as DIRECTED, AUTONOMOUS, or AMBIGUOUS"*
  - *"Zero evaluative adjectives in the document"*
  - *"`git status` shows no modifications after completion"*
  - *"Repository is on original branch/HEAD after completion"*
  - *"Profile contains ≥3 falsifiable AUTONOMOUS preference claims"*
  - *"Executive Summary is 3-5 sentences, behavioral description only"*
  - The pipeline's `verify_clean_state.py` and `lib/prose_validator.py` collectively enforce every item; failures block the build.

### 0.9.3 Deliberate Deviations from Literal Phrasing

- **"Checkout and read Project Guide" → "`git show <ref>:<path>` and read Project Guide"**. The user's prompt phrases the read operation as "checkout and read" but states the underlying intent as "HEAD restored after all branches are read". The pipeline achieves the intent more strictly by never moving HEAD in the first place. Logged as a Decision Log row with the rationale that this strengthens, not weakens, the read-only invariant.
- **Per-commit-per-branch classification rather than per-commit**. The user's prompt classifies "decisions" — but a single SHA can have different directive contexts across the branches that contain it. The pipeline preserves the per-branch dimension so a SHA can read DIRECTED on its origin and AMBIGUOUS on a downstream branch, and a single SHA never gets collapsed into a single label arbitrarily. Logged.
- **Bidirectional traceability matrix omitted**. The Explainability rule requires this matrix only "for migrations or refactors". The Blitzy Profile is neither. The omission is itself a row in `Decision_Log.md`.

## 0.10 References

### 0.10.1 Citation Discipline

Every claim in this Agent Action Plan about an existing artifact in the Formbricks repository carries an inline citation of the form `[<path>:<locator>]` where the locator is a line range, a section heading, a key path, or the per-branch / per-ref qualifier appropriate to the file type. Claims grounded in derived measurements (counts, branch lists, sizes) cite the command and its observed output. Claims that could not be grounded directly are tagged `[inferred — no direct source]`.

In the downstream `Blitzy_Profile_Formbricks.md` deliverable, every preference, trade-off, and behavioral-tendency claim cites ≥2 commit SHAs from ≥2 distinct branches, joined out of `data/evidence_appendix.csv`. The Evidence Appendix section of that deliverable is the canonical claim-to-SHA register.

### 0.10.2 Attachments and External References

- **User attachments**: 0. The user attached no files. The `/tmp/environments_files` directory referenced by the platform contract is absent on this host.
- **Environment variables provided by user**: 0 names listed.
- **Secrets provided by user**: 0 names listed.
- **Figma frames referenced**: 0. No Figma URL appears in the user's prompt; the Design System Compliance sub-section therefore exercises the proprietary-design-system path without a Figma cross-reference.
- **Setup instructions provided by user**: none. Environment was validated for `git` and `python3` availability directly.
- **External documentation links** consulted during AAP preparation:
  - reveal.js 5.1.0, Mermaid 11.4.0, Lucide 0.460.0 — version-pinned by the Executive Presentation rule; CDN URLs verified at delivery time.
  - Google Fonts (Inter, Space Grotesk, Fira Code) — loaded via the standard Google Fonts `<link>` per the Executive Presentation rule.

### 0.10.3 Tech Spec Cross-References

| Section | Relevance to this AAP |
|---|---|
| `1.1 EXECUTIVE SUMMARY` | Confirms the surrounding Technical Specification describes the Formbricks system, not the Blitzy Profile analysis task. The AAP is the only document section that scopes the meta-analysis. |
| All other tech-spec sections | Not directly cited. They describe Formbricks itself, which is the subject of analysis rather than the target of modification. |

### 0.10.4 Search Log (Appendix)

The following git refs, files, and folders were inspected to ground this AAP. Each entry records the inspection tool, target, and observation derived from the result.

| # | Tool | Target | Observation |
|---|---|---|---|
| 1 | bash `find` | `/.blitzyignore` | No `.blitzyignore` file present anywhere in the working tree |
| 2 | bash `which git` + `git --version` | `git` CLI | `/usr/bin/git`, version 2.43.0 |
| 3 | bash `pwd` | working directory | `/tmp/blitzy/blitzy-formbricks/main_0d6e40` |
| 4 | bash `ls /tmp/environments_files` | environments_files | Absent; no user attachments |
| 5 | bash `ls -la` | repo root | TypeScript monorepo with `apps/`, `packages/`, `charts/`, `docker/`, `docs/`, `blitzy/`, `blitzy-docs/` plus root tooling files |
| 6 | bash `cat .nvmrc` | `.nvmrc` | `22.1.0` — Node version pin (analysis pipeline does not engage Node) |
| 7 | bash `git status` | working tree | Clean; `On branch main`, `nothing to commit` |
| 8 | bash `git branch -a` | refs | 1 local branch (`main`) + 8 `remotes/origin/blitzy-*` + `demo` + `sandbox` + `main` remote |
| 9 | bash `git log --author="agent@blitzy.com" --oneline \| wc -l` | author commits on `main` | 208 commits |
| 10 | bash `git log --all --author="agent@blitzy.com" --oneline \| sort -u \| wc -l` | unique author commits across `--all` | 640 unique SHAs |
| 11 | bash `git show <ref>:blitzy/documentation/Project Guide.md` | one sample branch | Project Guide present, structured with `# Blitzy Project Guide`, `## 1. Executive Summary`, etc. |
| 12 | bash `git cat-file -e` + `-s` (per-branch loop) | Project Guide on each `blitzy-*` ref | 8 / 8 present, sizes 18,435-30,981 bytes |
| 13 | bash `cat .gitignore` | `.gitignore` | Standard Node ignores plus `branch.json`, `.vercel`, `.next-docs/`; output workspace is outside repo so ignore patterns are not relied upon |
| 14 | bash `node --version` + `python3 --version` | runtimes | Node v22.22.2 (≥ `.nvmrc` 22.1.0), Python 3.12.3 |
| 15 | bash `git rev-parse HEAD` | head | `c06879940eaaf0c98fbd373f1884b5852522ecc4` (the restoration baseline) |
| 16 | bash `git log --author="agent@blitzy.com" --pretty=format:"%s" \| head -30` | subject lines | Conventional-commit style observed: `fix(test-infra):`, `feat:`, `fix(docs):`, `fix(web):`, plus paired `Adding Blitzy Project Guide` / `Adding Blitzy Technical Specifications` auto-generated commits |
| 17 | bash `git log --author="agent@blitzy.com" "remotes/origin/<branch>" --not main` | per-branch unique commits | Sample branches showed `unique-vs-main=0`, consistent with branches that are subsets or rebased reflections of `main` |
| 18 | bash `ls apps/`, `ls packages/` | top-level subtrees | `apps/{web,storybook}`; `packages/{cache,config-eslint,config-prettier,config-typescript,database,email,i18n-utils,js-core,logger,storage,survey-ui,surveys,types,vite-plugins}` |
| 19 | bash `ls blitzy/`, `ls blitzy/documentation/`, `ls blitzy-docs/` | doc directories | `blitzy/documentation/{Project Guide.md, Technical Specifications.md}`; `blitzy-docs/{index.md, project-guide.md, technical-specifications.md}` |
| 20 | bash `git show <ref>:blitzy/documentation/Project Guide.md \| head -5` | sample branches | Guide headings vary by sprint scope (e.g., "Sprint 2: Logic & Data (Typeform Parity)", "Formbricks Documentation Suite v3.7.0", "Formbricks Typeform Parity Documentation") |
| 21 | `get_tech_spec_section` | `1.1 EXECUTIVE SUMMARY` | Confirms tech spec subject is Formbricks (the `blitzy-formbricks` parity initiative); the AAP scopes a distinct meta-analysis task |

### 0.10.5 User Inputs Preserved Verbatim

For traceability, the user's input rules, success criteria, and validation framework are preserved word-for-word in the relevant earlier sub-sections (0.1.3, 0.8.1, 0.9.2). The Decision Log will quote each item back as the source of every rule-driven choice.

