# Blitzy Project Guide — Typeform Feature Parity: Sprints 3–5

---

## 1. Executive Summary

### 1.1 Project Overview

This project implements Sprints 3, 4, and 5 of the Typeform feature parity initiative within the Formbricks open-source survey platform. The scope spans five epics: webhook payload parity (transforming Formbricks payloads to Typeform-compatible format), embed and share enhancements (slider, popover, and side tab embed modes), workspace governance parity (audit of organizational hierarchy and roles), migration safety procedures (backward-compatibility validation for all Sprint 1–3 schema changes), and end-to-end validation across all capability areas. The target users are Formbricks self-hosted and cloud platform users migrating from or competing with Typeform. The technical scope covers the Next.js 16 monorepo across `apps/web`, `packages/database`, `packages/js-core`, and `packages/types`, totaling 78 files changed with 10,675 net lines of code added.

### 1.2 Completion Status

```mermaid
pie title Project Completion
    "Completed (120h)" : 120
    "Remaining (18h)" : 18
```

| Metric | Value |
|---|---|
| **Total Project Hours** | 138 |
| **Completed Hours (AI)** | 120 |
| **Remaining Hours** | 18 |
| **Completion Percentage** | **87.0%** |

**Calculation**: 120 completed hours / (120 + 18) total hours = 120 / 138 = **87.0% complete**

### 1.3 Key Accomplishments

- ✅ Webhook payload parity — per-webhook `payloadFormat` toggle with full Typeform-compatible transformation covering all 17 survey element types
- ✅ Prisma schema migration with documented rollback procedure for `Webhook.payloadFormat` column
- ✅ Three new embed variants (Slider, Popover, Side Tab) implemented as share modal tabs with configurable options
- ✅ `@formbricks/js-core` SDK extended with `TEmbedMode` types and DOM initialization logic for all three embed modes
- ✅ V1 and V2 webhook APIs updated with `payloadFormat` support and OpenAPI documentation
- ✅ Backward-compatibility audit migration script validating all Sprint 1–3 schema changes across 17 element types
- ✅ Comprehensive validation test suites: webhook parity (957 lines), export lossless (700 lines), backward-compat (676 lines)
- ✅ Full test suite passing: 981 web app tests, all package tests green, zero TypeScript compilation errors
- ✅ Next.js 16 production build succeeds (58/58 static pages, all 9 library packages compile)
- ✅ Workspace governance audit confirming 4-role model exceeds Typeform's 3-role model

### 1.4 Critical Unresolved Issues

| Issue | Impact | Owner | ETA |
|---|---|---|---|
| Workspace parity audit not formally documented | Medium — no standalone artifact for stakeholder review | Human Developer | 2h |
| Playwright E2E tests not executed against running application | Medium — embed variants and webhook flows untested end-to-end | Human Developer | 3h |
| Migration rollback not verified in staging environment | High — rollback procedure exists but is untested in realistic conditions | Human Developer | 2h |
| Performance benchmarking with 10k+ datasets not executed | Low — test file exists but large-scale benchmark not run | Human Developer | 2h |

### 1.5 Access Issues

| System/Resource | Type of Access | Issue Description | Resolution Status | Owner |
|---|---|---|---|---|
| Staging Database | Database credentials | No staging environment available for migration rollback verification | Unresolved | DevOps |
| Stripe API | API credentials | `STRIPE_CLIENT_ID` env variable added to `.env.example` but not configured | Unresolved | Human Developer |
| Playwright Browser Environment | CI/CD infrastructure | E2E tests require running application instance with database | Unresolved | DevOps |

### 1.6 Recommended Next Steps

1. **[High]** Deploy Prisma migration (`20260301120000_add_payload_format_to_webhook`) to staging and verify rollback procedure
2. **[High]** Configure environment variables and run full Playwright E2E test suite against running application
3. **[High]** Validate webhook integration with real HTTP endpoints using both `default` and `typeform` payload formats
4. **[Medium]** Create formal workspace parity audit documentation summarizing governance model comparison findings
5. **[Medium]** Set up CI/CD pipeline stage for Playwright E2E tests and embed variant cross-browser verification

---

## 2. Project Hours Breakdown

### 2.1 Completed Work Detail

| Component | Hours | Description |
|---|---|---|
| Webhook Schema & Migration | 8 | Prisma `payloadFormat` field, `ZWebhook` extension, `webhook-payload.ts` Zod schemas (232 lines), SQL migration with rollback |
| Webhook Payload Transformer | 14 | `transformToTypeformPayload` function (404 lines) mapping all 17 element types to Typeform typed answer format |
| Webhook Pipeline Integration | 3 | Payload format branching in `route.ts`, try/catch error handling with graceful fallback |
| Webhook Service & API Updates | 5 | CRUD service `payloadFormat` persistence, V1 and V2 API type extensions, webhook table default |
| Webhook UI Components | 7 | Format selector radio buttons in add modal, format badge in detail modal, format toggle in settings tab |
| Webhook Documentation & i18n | 3 | OpenAPI v1/v2 schema updates (nullable payloadFormat), en-US.json i18n keys for webhook labels |
| Webhook Unit Tests | 4 | `payload-transformer.test.ts` (917 lines), V1/V2 webhook test updates (91 lines added) |
| Embed Tab Components | 12 | `SliderEmbedTab` (140 lines), `PopoverEmbedTab` (159 lines), `SideTabEmbedTab` (146 lines) with config and code generation |
| Share Modal Integration | 3 | `ShareViaType` enum extension (3 values), tab registration in `share-survey-modal.tsx` with icons/labels |
| JS-Core SDK Extension | 10 | `TEmbedMode`/`TSliderConfig`/`TPopoverConfig`/`TSideTabConfig` types, DOM setup logic (168 lines), exports |
| Embed Documentation & i18n | 3 | `embed-surveys.mdx` new sections (91 lines), en-US.json embed tab keys |
| Embed Tab Tests | 5 | 5 test files (slider 252, popover 205, side-tab 183, variants 196, modes 187 lines) |
| Workspace Parity Audit | 6 | Schema audit of Organization/Membership/Project/Team models, 4-role vs 3-role mapping, API key scope verification |
| Migration Audit & Safety | 10 | Audit migration script (256 lines), rollback tests (336 lines), cross-platform migration runner fix |
| Backward Compatibility Tests | 6 | `backward-compat.test.ts` (676 lines) validating ZSurveyElement union against existing survey fixtures |
| Sprint 5 Validation Tests | 13 | Webhook parity validation (957 lines), export lossless (700 lines), performance (181 lines), types export (615 lines) |
| Sprint 5 E2E & Regression | 7 | Playwright `embed-variants.spec.ts` (277 lines), full test suite execution (981 tests pass, 10 turbo tasks green) |
| Rollback Procedures | 1 | SQL rollback documentation in migration comments, DataMigration model status tracking |
| **Total** | **120** | |

### 2.2 Remaining Work Detail

| Category | Hours | Priority |
|---|---|---|
| Workspace Parity Audit Documentation | 2 | Medium |
| Staging Migration Rollback Verification | 2 | High |
| Playwright E2E Full Execution | 3 | High |
| Performance Benchmarking (10k+ responses) | 2 | Medium |
| Environment Configuration Validation | 1 | High |
| Prisma Migration Deployment Procedure | 1 | High |
| CI/CD Pipeline for E2E Tests | 2 | Medium |
| Real Webhook Endpoint Integration Testing | 3 | Medium |
| Cross-Browser Embed Mode Testing | 2 | Low |
| **Total** | **18** | |

---

## 3. Test Results

| Test Category | Framework | Total Tests | Passed | Failed | Coverage % | Notes |
|---|---|---|---|---|---|---|
| Web App Unit Tests | Vitest 3.1.3 | 981 | 981 | 0 | — | 37 test files, 1 pre-existing skip |
| Surveys Package | Vitest | 609 | 609 | 0 | — | Logic operator evaluation tests |
| JS-Core Package | Vitest | 253 | 253 | 0 | — | Includes new embed-modes.test.ts, setup.test.ts |
| i18n-utils Package | Vitest | 56 | 56 | 0 | — | Translation scanning tests |
| Database Migration | Vitest | 13 | 13 | 0 | — | Migration rollback tests |
| Payload Transformer | Vitest | ~60 | ~60 | 0 | — | 917 lines covering all 17 element types (included in web total) |
| Backward Compatibility | Vitest | ~40 | ~40 | 0 | — | ZSurveyElement union validation (included in web total) |
| Webhook Parity Validation | Vitest | ~35 | ~35 | 0 | — | Structural equivalence checks (included in web total) |
| Export Lossless Validation | Vitest | ~25 | ~25 | 0 | — | CSV/XLSX/JSON field-by-field comparison (included in web total) |
| Embed Tab Components | Vitest | ~45 | ~45 | 0 | — | 5 test files for slider/popover/side-tab (included in web total) |
| TypeScript Compilation | tsc --noEmit | — | Pass | 0 | 100% | Zero errors across all packages |
| ESLint | ESLint | — | Pass | 0 | 100% | Zero violations on all modified files |
| Next.js Build | Next.js 16 | 58 pages | 58 | 0 | 100% | Production build succeeds (2m39s) |

**Note**: All tests listed originate from Blitzy's autonomous validation execution. Individual test counts within web app total are approximate as Vitest reports at the file level; the web app total of 981 is exact.

---

## 4. Runtime Validation & UI Verification

### Runtime Health
- ✅ `pnpm install --frozen-lockfile` — Dependency resolution succeeds (6.5s)
- ✅ `pnpm prisma generate` — Prisma client generation succeeds (v6.14.0)
- ✅ `pnpm build` — Full turbo build succeeds (10/10 tasks, all packages + web app)
- ✅ TypeScript compilation — Zero errors across all 9 library packages and web application
- ✅ Git working tree — Clean (no uncommitted changes)

### UI Component Verification
- ✅ Share modal registers 3 new embed tabs (Slider, Popover, Side Tab) via `useMemo` array
- ✅ Webhook add modal includes payload format radio selector (Default / Typeform-compatible)
- ✅ Webhook detail modal displays Typeform-compatible format badge
- ✅ Webhook settings tab includes payload format toggle with radio buttons
- ✅ All UI strings internationalized via `useTranslation()` with en-US.json keys

### API Integration Verification
- ✅ Pipeline route correctly branches on `webhook.payloadFormat === "typeform"`
- ✅ V1 webhook API (`/api/v1/webhooks`) accepts and persists `payloadFormat`
- ✅ V2 webhook API (`/api/v2/management/webhooks`) accepts and persists `payloadFormat`
- ✅ OpenAPI v1 and v2 specs include `payloadFormat` field definition with nullable type
- ⚠️ Live webhook delivery not tested (requires running application and external endpoint)

### SDK Verification
- ✅ JS-Core SDK exports `TEmbedMode`, `TSliderConfig`, `TPopoverConfig`, `TSideTabConfig`
- ✅ SDK `setup()` function creates appropriate DOM containers for each embed mode
- ✅ SDK compiles cleanly (253/253 tests pass)
- ⚠️ Browser-based embed rendering not tested (requires live browser environment)

---

## 5. Compliance & Quality Review

| AAP Deliverable | Status | Evidence | Notes |
|---|---|---|---|
| **Epic 3.1: Webhook Payload Parity** | ✅ Complete | Schema + migration + transformer + UI + API + tests | All requirements met |
| Prisma `payloadFormat` field | ✅ Pass | `schema.prisma` line 55 | Additive column with default |
| SQL migration with rollback | ✅ Pass | `20260301120000_*/migration.sql` | 4-line migration with rollback comment |
| ZWebhook Zod extension | ✅ Pass | `zod/webhooks.ts` line 49 | `z.enum(["default","typeform"]).default("default").nullable()` |
| Typeform payload Zod schemas | ✅ Pass | `zod/webhook-payload.ts` (232 lines) | ZTypeformAnswer, ZTypeformFieldDefinition, ZTypeformCompatiblePayload |
| Payload transformer | ✅ Pass | `payload-transformer.ts` (404 lines) | Handles all 17 element types |
| Pipeline format branching | ✅ Pass | `route.ts` lines 123–125 | try/catch with fallback to default format |
| Webhook UI format controls | ✅ Pass | add-modal, detail-modal, settings-tab | Radio selector, badge, toggle |
| V1/V2 API support | ✅ Pass | Verified in both webhook.ts and types files | payloadFormat in CRUD operations |
| OpenAPI documentation | ✅ Pass | `openapi.json`, `openapi.yml` | Nullable type, enum values documented |
| Unit tests | ✅ Pass | `payload-transformer.test.ts` (917 lines) | All pass |
| **Epic 3.2: Embed & Share Enhancements** | ✅ Complete | 3 tab components + SDK + share modal + docs + tests | All requirements met |
| ShareViaType enum extension | ✅ Pass | `share.ts` lines 11–13 | SLIDER, POPOVER, SIDE_TAB |
| Slider embed tab | ✅ Pass | `slider-embed-tab.tsx` (140 lines) | Direction, width, animation config |
| Popover embed tab | ✅ Pass | `popover-embed-tab.tsx` (159 lines) | Position, icon, color, dimensions |
| Side tab embed tab | ✅ Pass | `side-tab-embed-tab.tsx` (146 lines) | Label, position, color config |
| Share modal registration | ✅ Pass | `share-survey-modal.tsx` imports + useMemo | 3 new entries with icons |
| JS-Core SDK types | ✅ Pass | `config.ts` (26 new lines) | TEmbedMode, TSliderConfig, TPopoverConfig, TSideTabConfig |
| JS-Core SDK setup | ✅ Pass | `setup.ts` (168 new lines) | DOM container creation for all modes |
| SDK public exports | ✅ Pass | `index.ts` lines 11–15, 123 | All types exported |
| Embed documentation | ✅ Pass | `embed-surveys.mdx` (91 new lines) | Slider, Popover, Side Tab sections |
| Embed tests | ✅ Pass | 5 test files (1,023 lines) | All pass |
| **Epic 4.1: Workspace Parity** | ⚠️ Partial | Audit performed, no standalone documentation | Code changes not required per evaluation |
| Schema audit | ✅ Pass | Organization/Project/Team models reviewed | 4-role > 3-role coverage confirmed |
| Role permissions audit | ✅ Pass | `utils.ts`, `roles.ts` analyzed | Formbricks exceeds Typeform's model |
| API key scope verification | ✅ Pass | Per-environment scoping verified | Meets/exceeds Typeform PAT model |
| Formal documentation | ❌ Not Done | No standalone audit document created | 2h remaining |
| Folder grouping | ✅ N/A | Determined not necessary for parity | No structural gap identified |
| **Epic 4.2: Migration Safety** | ✅ Complete | Audit script + rollback tests + backward-compat tests | All requirements met |
| Audit migration script | ✅ Pass | `20260301130000_*/migration.ts` (256 lines) | Validates 17 element types |
| Rollback tests | ✅ Pass | `migration-rollback.test.ts` (336 lines) | All pass |
| Backward-compat tests | ✅ Pass | `backward-compat.test.ts` (676 lines) | ZSurveyElement union verified |
| Migration runner fix | ✅ Pass | Cross-platform path handling | ESM import compatibility |
| **Sprint 5: Validation** | ⚠️ Mostly Complete | Test suites created and passing; staging/E2E gaps remain | 7h remaining |
| Webhook parity validation | ✅ Pass | `webhook-parity-validation.test.ts` (957 lines) | Structural equivalence verified |
| Export lossless validation | ✅ Pass | `export-lossless-validation.test.ts` (700 lines) | CSV/XLSX/JSON field-by-field |
| Performance validation | ⚠️ Partial | Test file exists (181 lines) | 10k+ benchmark not executed |
| Full regression suite | ✅ Pass | 981 web tests + all packages | Zero failures |
| Playwright E2E | ⚠️ Partial | Test files created (embed-variants.spec.ts) | Not executed against running app |
| Staging rollback | ❌ Not Done | No staging environment available | Requires infrastructure |

### Parity Constraint Compliance
| Constraint | Status |
|---|---|
| Webhook structural parity (Typeform format) | ✅ Verified via unit tests |
| 100% logic jump coverage (32 operators) | ✅ 609/609 logic tests pass |
| No broken existing forms | ✅ Backward-compat tests confirm |
| Lossless export (CSV/XLSX/JSON) | ✅ Export validation tests pass |
| HMAC-SHA256 signature integrity | ✅ No changes to signing mechanism |
| Additive-only migrations | ✅ Only new columns with defaults |

---

## 6. Risk Assessment

| Risk | Category | Severity | Probability | Mitigation | Status |
|---|---|---|---|---|---|
| Migration rollback untested in staging | Technical | High | Medium | Rollback procedure documented in SQL; test suite validates logic | Open — requires staging environment |
| Webhook payload transformer edge cases | Technical | Medium | Low | 917 lines of unit tests covering all 17 element types; try/catch fallback to default format | Mitigated |
| Embed mode DOM conflicts with host page | Technical | Medium | Medium | Unique container IDs (`formbricks-slider-container`, etc.); scoped CSS | Open — requires cross-browser testing |
| Playwright E2E tests not run against live application | Technical | Medium | High | Test files created and syntactically valid; requires running app instance | Open |
| `STRIPE_CLIENT_ID` environment variable not configured | Operational | Low | High | Added to `.env.example`; documented in environment setup | Open — requires Stripe dashboard setup |
| Workspace parity audit undocumented | Operational | Low | High | Audit was performed but no formal artifact; create summary document | Open |
| Performance benchmarking with large datasets not run | Technical | Low | Medium | Export streaming pipeline exists; test file created but not executed at scale | Open |
| Third-party webhook consumers receiving unexpected format | Integration | High | Low | Per-webhook opt-in toggle (default format unchanged); `payloadFormat: "default"` for all existing webhooks | Mitigated |
| SDK embed mode types not yet consumed by Formbricks surveys renderer | Integration | Low | Low | Types exported from js-core; surveys package unchanged (out of scope) | Accepted |
| Zod schema expansion breaking legacy API consumers | Security | Medium | Low | `payloadFormat` is nullable with default; existing webhooks unaffected | Mitigated |

---

## 7. Visual Project Status

```mermaid
pie title Project Hours Breakdown
    "Completed Work" : 120
    "Remaining Work" : 18
```

### Remaining Hours by Category

| Category | Hours | Priority |
|---|---|---|
| Workspace Parity Audit Documentation | 2 | Medium |
| Staging Migration Rollback Verification | 2 | High |
| Playwright E2E Full Execution | 3 | High |
| Performance Benchmarking (10k+ responses) | 2 | Medium |
| Environment Configuration Validation | 1 | High |
| Prisma Migration Deployment Procedure | 1 | High |
| CI/CD Pipeline for E2E Tests | 2 | Medium |
| Real Webhook Endpoint Integration Testing | 3 | Medium |
| Cross-Browser Embed Mode Testing | 2 | Low |
| **Total Remaining** | **18** | |

---

## 8. Summary & Recommendations

### Achievement Summary

The project has achieved **87.0% completion** (120 of 138 total hours), delivering all core implementation work for Sprints 3–5 of the Typeform feature parity initiative. All five epics have been addressed: webhook payload parity is fully implemented with a production-ready 404-line payload transformer supporting all 17 element types; three new embed variants (Slider, Popover, Side Tab) are built, registered, and tested with full SDK support; workspace governance parity has been audited with no code changes required; migration safety procedures are established with comprehensive backward-compatibility testing; and Sprint 5 validation test suites are created and passing.

### Key Metrics
- **53 commits** on the feature branch
- **78 files** modified or created (33 new, 45 modified)
- **10,675 net lines** of production code added
- **981/981** web app tests passing (100% pass rate)
- **All 10** turbo build tasks successful
- **Zero** TypeScript compilation errors
- **Zero** ESLint violations

### Remaining Gaps

The 18 remaining hours focus on three areas: (1) staging environment verification — running the migration rollback procedure and Playwright E2E tests against a live application instance; (2) integration testing — validating webhook delivery with real HTTP endpoints and embed mode rendering across browsers; and (3) documentation — formalizing the workspace parity audit findings. No core implementation work remains.

### Production Readiness Assessment

The codebase is **near production-ready**. All code compiles, builds, and tests pass. The primary gap is operational verification in a production-like staging environment. The webhook payload transformer includes resilient error handling (try/catch fallback to default format), the migration is additive-only with a documented rollback, and all existing functionality remains backward-compatible.

### Recommendations

1. **Prioritize staging deployment** — Apply the Prisma migration and verify rollback before production release
2. **Run full E2E suite** — Execute Playwright tests against a running application to validate embed variants and webhook flows end-to-end
3. **Test webhook delivery** — Configure a test webhook endpoint with `payloadFormat: "typeform"` and verify the Typeform-compatible payload structure with a real consumer
4. **Document workspace audit** — Create a standalone summary of the governance model comparison for stakeholder review
5. **Add CI/CD stage** — Integrate Playwright E2E tests into the CI/CD pipeline for ongoing regression coverage

---

## 9. Development Guide

### System Prerequisites

| Software | Version | Purpose |
|---|---|---|
| Node.js | ≥ 20.x (tested: 20.20.2) | JavaScript runtime |
| pnpm | 10.28.2 | Package manager (enforced via `packageManager` field) |
| PostgreSQL | 14+ | Primary database |
| Docker (optional) | Latest | Database container management |
| Git | Latest | Version control |

### Environment Setup

1. **Clone the repository and switch to the feature branch:**

```bash
git clone <repository-url>
cd formbricks
git checkout blitzy-7a9d25be-d124-40bf-b715-2cf66eb7b11a
```

2. **Configure environment variables:**

```bash
cp .env.example .env
```

Edit `.env` and configure the following required variables:

```bash
# Database
DATABASE_URL='postgresql://postgres:postgres@localhost:5432/formbricks?schema=public'

# Application URLs
WEBAPP_URL=http://localhost:3000
NEXTAUTH_URL=http://localhost:3000

# Authentication
NEXTAUTH_SECRET=<generate-with-openssl-rand-hex-32>
ENCRYPTION_KEY=<generate-with-openssl-rand-hex-32>

# Stripe (for payment features — optional for non-payment testing)
STRIPE_SECRET_KEY=<your-stripe-secret-key>
STRIPE_WEBHOOK_SECRET=<your-stripe-webhook-secret>
STRIPE_CLIENT_ID=<your-stripe-connect-client-id>
```

3. **Start the database:**

```bash
# Using Docker
pnpm db:start

# Or use an existing PostgreSQL instance (ensure DATABASE_URL is set)
```

### Dependency Installation

```bash
# Install all workspace dependencies (frozen lockfile for reproducibility)
pnpm install --frozen-lockfile

# Generate Prisma client
pnpm prisma generate --schema=packages/database/schema.prisma

# Apply database migrations
pnpm db:migrate:deploy

# Seed the database (optional, for development data)
pnpm db:seed
```

### Application Startup

```bash
# Build all packages and the web application
pnpm build

# Start the development server
pnpm dev
```

The application will be available at `http://localhost:3000`.

### Running Tests

```bash
# Run all tests (monorepo-wide)
pnpm test

# Run web app tests only
cd apps/web && pnpm test

# Run specific package tests
cd packages/js-core && pnpm test
cd packages/surveys && pnpm test
cd packages/database && pnpm test

# Run with watch mode disabled (CI)
CI=true pnpm test -- --watchAll=false

# Run Playwright E2E tests (requires running application)
cd apps/web && npx playwright test
```

### Verification Steps

1. **Verify build succeeds:**
```bash
pnpm build
# Expected: 10/10 tasks successful, zero errors
```

2. **Verify Prisma client is generated:**
```bash
pnpm prisma generate --schema=packages/database/schema.prisma
# Expected: "Generated Prisma Client"
```

3. **Verify TypeScript compilation:**
```bash
npx tsc --noEmit --pretty -p packages/js-core/tsconfig.json
# Expected: No output (zero errors)
```

4. **Verify tests pass:**
```bash
CI=true pnpm test -- --watchAll=false --ci
# Expected: All test suites pass
```

### Webhook Payload Format Testing

To test the Typeform-compatible webhook payload:

1. Navigate to **Integrations > Webhooks** in the Formbricks dashboard
2. Click **Add Webhook**
3. Enter a webhook URL (e.g., https://webhook.site or a local endpoint)
4. Select **Typeform-compatible** under Payload Format
5. Select triggers and surveys
6. Save and submit a survey response to trigger the webhook
7. Verify the payload contains `answers` array, `definition.fields`, and `calculated.score`

### Embed Mode Testing

To test the new embed variants:

1. Navigate to any survey's **Summary** page
2. Click **Share Survey**
3. Select **Slider**, **Popover**, or **Side Tab** from the sidebar
4. Configure options (direction, position, color, etc.)
5. Copy the generated JavaScript snippet
6. Paste into an HTML page and open in a browser

### Troubleshooting

| Issue | Resolution |
|---|---|
| `prisma generate` fails | Ensure `packages/database/schema.prisma` exists and `DATABASE_URL` is set |
| Build fails with TypeScript errors | Run `pnpm install --frozen-lockfile` then `pnpm prisma generate` first |
| Tests fail with database errors | Ensure PostgreSQL is running and `DATABASE_URL` is correctly configured |
| Migration fails | Check `packages/database/migration/` for pending migrations; run `pnpm db:migrate:deploy` |
| Webhook payload not transforming | Verify `payloadFormat` is set to `"typeform"` on the webhook record |
| Embed variants not appearing in share modal | Verify `share.ts` has `SLIDER`, `POPOVER`, `SIDE_TAB` enum values |

---

## 10. Appendices

### A. Command Reference

| Command | Purpose | Working Directory |
|---|---|---|
| `pnpm install --frozen-lockfile` | Install dependencies | Repository root |
| `pnpm prisma generate --schema=packages/database/schema.prisma` | Generate Prisma client | Repository root |
| `pnpm build` | Build all packages and web app | Repository root |
| `pnpm dev` | Start development server | Repository root |
| `pnpm test` | Run all tests | Repository root |
| `pnpm db:start` | Start PostgreSQL via Docker | Repository root |
| `pnpm db:migrate:deploy` | Apply database migrations | Repository root |
| `pnpm db:migrate:dev` | Create new migration (development) | Repository root |
| `pnpm db:seed` | Seed database with sample data | Repository root |
| `npx tsc --noEmit` | Type-check without emitting | Any package directory |
| `npx playwright test` | Run E2E tests | `apps/web` |

### B. Port Reference

| Service | Port | Description |
|---|---|---|
| Web Application | 3000 | Next.js 16 development server |
| PostgreSQL | 5432 | Primary database |
| SMTP (dev) | 1025 | Development email server |
| OpenTelemetry | 4318 | OTLP endpoint (optional) |

### C. Key File Locations

| File | Purpose |
|---|---|
| `packages/database/schema.prisma` | Prisma database schema (Webhook model with `payloadFormat`) |
| `packages/database/zod/webhooks.ts` | ZWebhook Zod schema |
| `packages/database/zod/webhook-payload.ts` | Typeform-compatible payload Zod schemas |
| `packages/database/migration/20260301120000_add_payload_format_to_webhook/` | SQL migration for payloadFormat |
| `packages/database/migration/20260301130000_audit_sprint1_3_changes/` | Sprint 1–3 backward-compat audit |
| `apps/web/app/api/(internal)/pipeline/lib/payload-transformer.ts` | Payload transformation logic |
| `apps/web/app/api/(internal)/pipeline/route.ts` | Pipeline route (webhook dispatch) |
| `apps/web/modules/integrations/webhooks/` | Webhook CRUD module (service, actions, UI) |
| `apps/web/app/(app)/.../summary/components/shareEmbedModal/` | All embed tab components |
| `apps/web/app/(app)/.../summary/types/share.ts` | ShareViaType enum |
| `packages/js-core/src/types/config.ts` | SDK embed mode type definitions |
| `packages/js-core/src/lib/common/setup.ts` | SDK embed mode initialization |
| `packages/js-core/src/index.ts` | SDK public API exports |
| `docs/xm-and-surveys/surveys/link-surveys/embed-surveys.mdx` | Embed documentation |
| `docs/api-v2-reference/openapi.yml` | API v2 OpenAPI specification |
| `docs/api-reference/openapi.json` | API v1 OpenAPI specification |
| `.env.example` | Environment variable template |

### D. Technology Versions

| Technology | Version |
|---|---|
| Node.js | ≥ 20.x (tested: 20.20.2) |
| pnpm | 10.28.2 |
| Next.js | 16.1.6 |
| React | 19.2.4 |
| Prisma | 6.14.0 |
| @prisma/client | 6.14.0 |
| TypeScript | (workspace) |
| Vitest | 3.1.3 |
| Playwright | 1.56.1 |
| Zod | (workspace) |
| Turborepo | 2.5.3 |

### E. Environment Variable Reference

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `WEBAPP_URL` | Yes | Public URL of the web application |
| `NEXTAUTH_URL` | Yes | NextAuth.js callback URL (same as WEBAPP_URL) |
| `NEXTAUTH_SECRET` | Yes | Random secret for NextAuth.js session encryption |
| `ENCRYPTION_KEY` | Yes | Random key for data encryption |
| `STRIPE_SECRET_KEY` | For payments | Stripe API secret key |
| `STRIPE_WEBHOOK_SECRET` | For payments | Stripe webhook signing secret |
| `STRIPE_CLIENT_ID` | For Stripe Connect | Stripe Connect OAuth client ID |
| `SMTP_HOST` | For emails | SMTP server hostname |
| `SMTP_PORT` | For emails | SMTP server port (default: 1025) |

### F. Developer Tools Guide

| Tool | Usage |
|---|---|
| Prisma Studio | `npx prisma studio` — Visual database browser |
| Turbo Cache | `turbo run build --no-cache` — Force rebuild without cache |
| ESLint | `npx eslint <file> --no-fix` — Check for lint issues |
| Prettier | `pnpm format` — Auto-format all files |
| Docker Compose | `docker compose up -d` — Start all services in background |

### G. Glossary

| Term | Definition |
|---|---|
| **payloadFormat** | Per-webhook setting controlling payload structure: `"default"` (Formbricks format) or `"typeform"` (Typeform-compatible format) |
| **ShareViaType** | TypeScript enum defining all share/embed tab types in the survey sharing modal |
| **TEmbedMode** | TypeScript type union (`"slider" \| "popover" \| "sideTab"`) for JS-Core SDK embed modes |
| **ZSurveyElement** | Zod discriminated union schema encompassing all 17 survey element types |
| **TSurveyElementTypeEnum** | TypeScript enum listing all survey element type identifiers |
| **Pipeline Route** | Internal Next.js API route (`/api/(internal)/pipeline`) handling webhook dispatch and integration processing |
| **fb-migrate-dev** | Custom migration command (`pnpm db:migrate:dev`) that generates SQL, copies to Prisma's migration directory, and applies all pending migrations |
| **DataMigration** | Prisma model tracking data migration execution status (`pending`, `applied`, `failed`) |
| **Standard Webhooks** | Specification for webhook signing using HMAC-SHA256 with `webhook-id`, `webhook-timestamp`, `webhook-signature` headers |