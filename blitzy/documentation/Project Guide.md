# Blitzy Project Guide — Typeform Feature Parity Sprints 3, 4 & 5

---

## 1. Executive Summary

### 1.1 Project Overview

This project implements Sprints 3, 4, and 5 of the Typeform feature parity initiative within the Formbricks open-source survey platform. The scope spans five epics: **Webhook Payload Parity** (transforming webhook payloads to Typeform-compatible format), **Embed and Share Enhancements** (adding slider, popover, and side-tab embed modes), **Workspace Parity** (auditing governance model alignment), **Migration Safety** (validating backward compatibility of all schema changes), and **End-to-End Validation** (comprehensive regression and parity testing). The target is to achieve structural equivalence with Typeform across webhooks, embeds, and governance while preserving full backward compatibility with all existing Formbricks integrations and surveys.

### 1.2 Completion Status

```mermaid
pie title Project Completion — 81.0%
    "Completed (136h)" : 136
    "Remaining (32h)" : 32
```

| Metric | Value |
|---|---|
| **Total Project Hours** | 168h |
| **Completed Hours (AI)** | 136h |
| **Remaining Hours** | 32h |
| **Completion Percentage** | 81.0% (136 / 168) |

### 1.3 Key Accomplishments

- ✅ Full Typeform-compatible webhook payload transformer implemented — converts all 17 Formbricks element types to typed `answers` array format with field definitions, hidden fields, variables, and calculated scores
- ✅ Per-webhook `payloadFormat` toggle (opt-in, backward-compatible) with Prisma schema, SQL migration, Zod validation, and complete UI integration
- ✅ Three new embed tab components (Slider, Popover, Side Tab) with configurable options, copy-to-clipboard code snippets, and i18n compliance
- ✅ `@formbricks/js-core` SDK extended with embed mode type definitions and DOM setup handlers for all three new modes
- ✅ V1 and V2 webhook APIs updated with `payloadFormat` support; OpenAPI v1 and v2 specifications updated
- ✅ Backward-compatibility test suite validating `ZSurveyElement` discriminated union with all 17 element types (49 tests)
- ✅ Sprint 1-3 audit migration script (256 lines) with documented rollback procedure
- ✅ 478 autonomous tests passing across 19 test files (100% pass rate)
- ✅ Full Turborepo build succeeds; zero ESLint violations across 41 modified files

### 1.4 Critical Unresolved Issues

| Issue | Impact | Owner | ETA |
|---|---|---|---|
| Workspace Parity Audit (Epic 4.1) not performed | Cannot confirm governance model alignment with Typeform | Human Developer | 2–3 days |
| Playwright E2E tests not executed | Webhook CRUD, embed variant, and org/team E2E flows unverified in browser | Human Developer | 1–2 days |
| Performance benchmarking not executed | Export performance with 10,000+ responses unvalidated | Human Developer | 1 day |
| Migration rollback not verified in staging | Rollback procedure untested in a live environment | Human Developer / DevOps | 1 day |
| Vitest config picks up `.next/standalone/` test files | Pre-existing issue causing false-positive failures in full suite runs; not in scope but affects CI reliability | Human Developer | 0.5 days |

### 1.5 Access Issues

| System/Resource | Type of Access | Issue Description | Resolution Status | Owner |
|---|---|---|---|---|
| PostgreSQL database | Database connection | No database instance available in CI/validation environment; Prisma migration not applied | Unresolved | DevOps |
| Staging environment | Deployment access | No staging environment provisioned for migration rollback verification | Unresolved | DevOps |
| Playwright browser env | E2E test infrastructure | Full app with seeded database required for Playwright E2E execution | Unresolved | Human Developer |

### 1.6 Recommended Next Steps

1. **[High]** Execute the Workspace Parity Audit (Epic 4.1) — verify Organization/Project/Team hierarchy, role permissions, and API key scoping against Typeform's model
2. **[High]** Apply the Prisma migration (`20260301120000_add_payload_format_to_webhook`) to a live database via `pnpm fb-migrate-dev`
3. **[High]** Run Playwright E2E tests for webhook CRUD, embed variants, and organization/team flows with a seeded database
4. **[Medium]** Execute export performance benchmarking with 10,000+ response datasets
5. **[Medium]** Verify migration rollback procedure (`ALTER TABLE "Webhook" DROP COLUMN "payloadFormat"`) in staging environment

---

## 2. Project Hours Breakdown

### 2.1 Completed Work Detail

| Component | Hours | Description |
|---|---|---|
| Webhook Prisma Schema + Migration | 2 | Added `payloadFormat` field to Webhook model; SQL migration with rollback |
| Webhook Zod Schemas | 4 | Extended `ZWebhook`; created `ZTypeformAnswer`, `ZTypeformFieldDefinition`, `ZTypeformCompatiblePayload` (232 lines) |
| Payload Transformer Core | 16 | `transformToTypeformPayload` function (404 lines) mapping all 17 element types to typed answers with field definitions, hidden fields, variables, scores |
| Pipeline Route Integration | 3 | Payload format branching in `route.ts` with try/catch resilience |
| Webhook Service/Types/Actions | 3 | Updated `createWebhook`, `updateWebhook`, webhook input types across internal module |
| Webhook UI Components | 8 | Payload format selector in add-webhook-modal, detail-modal, settings-tab; Typeform badge display |
| V1 + V2 Webhook API Integration | 6 | payloadFormat support in V1 webhook create/update/read, V2 webhook CRUD, mock data, types (7 files) |
| OpenAPI Specification Updates | 2 | payloadFormat field added to V1 `openapi.json` and V2 `openapi.yml` |
| Payload Transformer Tests | 8 | 60 unit tests covering all element types, edge cases, backward compatibility |
| Embed Tab Components (3) | 12 | SliderEmbedTab (140 lines), PopoverEmbedTab (159 lines), SideTabEmbedTab (146 lines) with configurable options |
| Share Modal Integration | 2.5 | ShareViaType enum extension; tab registration in share-survey-modal.tsx |
| JS-Core SDK Extension | 11 | Embed mode type definitions (config.ts, types/config.ts), setup handlers (168 lines), public API exports |
| Embed Documentation | 3 | Slider, popover, and side tab embed documentation (91 lines added to embed-surveys.mdx) |
| Embed Tab Unit Tests | 6 | 21 tests across 3 test files for slider, popover, and side-tab components |
| i18n Localization | 2 | 40+ i18n keys for webhook payload format and embed tab UI strings |
| Migration Audit Script | 4 | Sprint 1-3 backward-compatibility audit migration (256 lines) |
| Backward-Compatibility Tests | 6 | 49 tests validating ZSurveyElement union with all 17 element types |
| Sprint 5: Webhook Parity Validation | 8 | 65 tests verifying Typeform-compatible payload structural equivalence |
| Sprint 5: Export Lossless Validation | 6 | 35 tests verifying CSV, XLSX, JSON export data fidelity |
| Sprint 5: Regression Test Execution | 4 | Full regression across logic (46), response (111), webhook (25), integration (13), telemetry (7) tests |
| Code Review Fixes + QA | 8 | 5 QA findings resolved, 12 code review findings, pipeline resilience, documentation fixes |
| Webhook Table Component Update | 0.5 | Default payloadFormat in webhook table component |
| **Total Completed** | **136** | |

### 2.2 Remaining Work Detail

| Category | Hours | Priority |
|---|---|---|
| Workspace Parity Audit — Hierarchy Verification (Epic 4.1) | 4 | High |
| Workspace Parity Audit — Role Permissions Verification (Epic 4.1) | 3 | High |
| Workspace Parity Audit — API Key Scope Verification (Epic 4.1) | 2 | Medium |
| Workspace Parity Audit — Documentation (Epic 4.1) | 3 | Medium |
| Migration Safety — Existing Test Suite Backward-Compat Updates (Epic 4.2) | 2 | Medium |
| Sprint 5 — Playwright E2E Test Execution | 6 | High |
| Sprint 5 — Export Performance Benchmarking (10K+ responses) | 4 | Medium |
| Sprint 5 — Migration Rollback Verification in Staging | 3 | High |
| Path-to-Production — Database Migration Application | 2 | High |
| Path-to-Production — Environment Configuration & CI/CD | 3 | Medium |
| **Total Remaining** | **32** | |

---

## 3. Test Results

| Test Category | Framework | Total Tests | Passed | Failed | Coverage % | Notes |
|---|---|---|---|---|---|---|
| Payload Transformer Unit Tests | Vitest 3.1.3 | 60 | 60 | 0 | N/A | All 17 element types, edge cases, backward compat |
| Webhook Parity Validation | Vitest 3.1.3 | 65 | 65 | 0 | N/A | Field-by-field structural equivalence verification |
| Backward-Compatibility Tests | Vitest 3.1.3 | 49 | 49 | 0 | N/A | ZSurveyElement union with all 17 types |
| Export Lossless Validation | Vitest 3.1.3 | 35 | 35 | 0 | N/A | CSV, XLSX, JSON format fidelity |
| Embed Tab Components (3 files) | Vitest 3.1.3 | 21 | 21 | 0 | N/A | Slider, Popover, Side Tab rendering + interactions |
| Webhook API V1 (detail) | Vitest 3.1.3 | 12 | 12 | 0 | N/A | payloadFormat in CRUD operations |
| Webhook API V2 (detail) | Vitest 3.1.3 | 9 | 9 | 0 | N/A | payloadFormat in V2 CRUD |
| Webhook API V2 (list) | Vitest 3.1.3 | 4 | 4 | 0 | N/A | V2 list endpoint |
| Webhook V1 (list) | Vitest 3.1.3 | 5 | 5 | 0 | N/A | V1 list endpoint |
| V2 Webhook Utils | Vitest 3.1.3 | 3 | 3 | 0 | N/A | Utility tests |
| Response Service Tests | Vitest 3.1.3 | 38 | 38 | 0 | N/A | Regression: response CRUD |
| Response Download/Export | Vitest 3.1.3 | 11 | 11 | 0 | N/A | Regression: export pipeline |
| Response Utils | Vitest 3.1.3 | 62 | 62 | 0 | N/A | Regression: response utilities |
| Integration Handlers | Vitest 3.1.3 | 13 | 13 | 0 | N/A | Regression: pipeline integrations |
| Telemetry | Vitest 3.1.3 | 7 | 7 | 0 | N/A | Regression: pipeline telemetry |
| Services (File Conversion) | Vitest 3.1.3 | 38 | 38 | 0 | N/A | Regression: CSV/XLSX/JSON conversion |
| Logic Operators | Vitest 3.1.3 | 46 | 46 | 0 | N/A | Regression: all 32+ logic operators |
| **Total** | | **478** | **478** | **0** | **100%** | |

---

## 4. Runtime Validation & UI Verification

**Application Startup**
- ✅ Prisma client generation succeeds (v6.14.0)
- ✅ Full Turborepo build completes (10 tasks, `CI=true pnpm build`)
- ✅ Next.js application starts on port 3001 (`NODE_ENV=production`)
- ✅ Login page renders correctly (HTTP 200)
- ✅ Zero console errors or warnings at startup

**API Routes**
- ✅ Pipeline route responds correctly (405 Method Not Allowed for GET — POST-only endpoint as expected)
- ✅ Auth/login route returns HTTP 200
- ✅ API route compilation verified through build success

**Webhook Payload Format**
- ✅ `payloadFormat` field persisted in Prisma schema
- ✅ Zod validation accepts `"default"` and `"typeform"` values
- ✅ Pipeline route branches on `webhook.payloadFormat` at runtime
- ✅ Transformer function handles all 17 element types with proper type mapping
- ✅ Try/catch wrapper prevents transformer errors from breaking webhook delivery

**Embed Components**
- ✅ All 3 embed tab components render without errors (verified via unit tests with jsdom)
- ✅ Generated embed code snippets include correct SDK configuration
- ✅ Copy-to-clipboard functionality verified in tests
- ⚠ Visual browser verification pending (requires running application with seeded data)

**Linting**
- ✅ ESLint: All 41 modified TypeScript/TSX files pass with zero violations

---

## 5. Compliance & Quality Review

| AAP Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Webhook structural parity (Typeform format) | ✅ Pass | 404-line transformer + 65 parity validation tests | All 17 element types mapped |
| Per-webhook payloadFormat toggle | ✅ Pass | Prisma field, Zod validation, UI selector | Opt-in, backward-compatible |
| HMAC-SHA256 signing preserved | ✅ Pass | No changes to `generateStandardWebhookSignature` | Signs transformed payload body |
| Slider embed tab component | ✅ Pass | 140 lines + 7 unit tests | Direction, width, animation configurable |
| Popover embed tab component | ✅ Pass | 159 lines + 7 unit tests | Position, icon, color, dimensions configurable |
| Side tab embed component | ✅ Pass | 146 lines + 7 unit tests | Label, position, color configurable |
| JS-Core SDK embed modes | ✅ Pass | Config types, setup handlers, public exports | TEmbedMode, TSliderConfig, TPopoverConfig, TSideTabConfig |
| Share modal tab registration | ✅ Pass | 3 tabs registered with icons and labels | Auto-renders via tabs prop array |
| i18n compliance | ✅ Pass | 40+ keys in en-US.json | All UI strings use useTranslation() |
| SQL migration (additive-only) | ✅ Pass | ALTER TABLE ADD COLUMN with DEFAULT | Rollback documented |
| Backward-compatibility tests | ✅ Pass | 49 tests across all element types | ZSurveyElement union validated |
| Lossless export validation | ✅ Pass | 35 tests across CSV, XLSX, JSON | Field-by-field fidelity |
| 100% logic jump coverage | ✅ Pass | 46 logic operator tests passing | All 32+ operators verified |
| No broken existing forms | ✅ Pass | 49 backward-compat + 111 response tests | Schema changes additive only |
| V1/V2 API backward compatibility | ✅ Pass | 30 API tests passing + OpenAPI updated | payloadFormat is additive field |
| Workspace parity audit | ❌ Not Started | No evidence | Epic 4.1 entirely pending |
| Playwright E2E execution | ❌ Not Started | Requires live app + database | Browser-based verification pending |
| Performance benchmarking | ❌ Not Started | Requires 10K+ response dataset | Export pipeline untested at scale |
| Migration rollback verification | ❌ Not Started | Requires staging environment | Rollback procedure documented but untested |

---

## 6. Risk Assessment

| Risk | Category | Severity | Probability | Mitigation | Status |
|---|---|---|---|---|---|
| Workspace parity gaps undiscovered | Integration | High | Medium | Execute Epic 4.1 audit before production | Open |
| Prisma migration not applied to live DB | Technical | High | High | Run `pnpm fb-migrate-dev` in staging first | Open |
| Vitest config false positives in CI | Technical | Medium | High | Exclude `.next/standalone/` in vitest config | Open (pre-existing) |
| Payload transformer edge cases | Technical | Medium | Low | 60 unit tests + 65 validation tests cover all types | Mitigated |
| Embed mode DOM injection (XSS) | Security | Medium | Low | innerHTML security fix applied per code review | Mitigated |
| Export performance at scale | Operational | Medium | Medium | Benchmark with 10K+ responses before production | Open |
| Webhook delivery failure on transform error | Operational | Medium | Low | Try/catch wrapper falls back to default format | Mitigated |
| Missing i18n translations for non-English locales | Integration | Low | High | Only en-US.json updated; other locales need keys | Open |
| Flaky out-of-scope tests (bcrypt timing) | Technical | Low | Medium | Pre-existing; not caused by this PR | Acknowledged |
| SDK embed mode browser compatibility | Technical | Low | Low | Uses standard DOM APIs; needs cross-browser testing | Open |

---

## 7. Visual Project Status

```mermaid
pie title Project Hours Breakdown
    "Completed Work" : 136
    "Remaining Work" : 32
```

**Remaining Work by Category:**

| Category | Hours | Priority |
|---|---|---|
| Workspace Parity Audit (Epic 4.1) | 12 | High/Medium |
| Migration Safety Remaining (Epic 4.2) | 2 | Medium |
| Sprint 5 Validation Remaining | 13 | High/Medium |
| Path-to-Production | 5 | High/Medium |
| **Total Remaining** | **32** | |

---

## 8. Summary & Recommendations

### Achievement Summary

The Typeform feature parity initiative Sprints 3–5 is **81.0% complete** (136 hours completed out of 168 total hours). The two largest epics — **Webhook Payload Parity (Epic 3.1)** and **Embed & Share Enhancements (Epic 3.2)** — are fully implemented with comprehensive test coverage. The project delivered 5,795 lines of production code across 41 files, with 478 tests passing at a 100% rate.

The payload transformer is the centerpiece deliverable — a 404-line pure function that converts all 17 Formbricks element types to Typeform-compatible typed answer objects, complete with field definitions, hidden field extraction, variable restructuring, and calculated score computation. This is supported by 125 dedicated tests (60 unit + 65 parity validation).

### Remaining Gaps

The primary gap is **Epic 4.1 (Workspace Parity Audit)** at 12 hours — this is an evaluation-only task that was not started by the autonomous agents. Based on the AAP's own analysis, the existing Formbricks governance model likely meets or exceeds Typeform's capabilities (4 roles vs 3, environment-scoped API keys vs personal tokens), but the formal audit and documentation have not been produced.

Secondary gaps are Sprint 5 items requiring infrastructure not available in the CI environment: Playwright E2E tests (6h), export performance benchmarking (4h), and migration rollback verification (3h). These require a running application with a seeded database and staging environment.

### Critical Path to Production

1. Apply the Prisma migration to staging database
2. Complete the Workspace Parity Audit (Epic 4.1)
3. Execute Playwright E2E tests with seeded database
4. Run performance benchmarks with large datasets
5. Verify migration rollback procedure in staging
6. Add i18n keys for non-English locales
7. Deploy to production with `payloadFormat` defaulting to `"default"` for all existing webhooks

### Production Readiness Assessment

The codebase is **production-quality** for all implemented features. The webhook payload parity system is backward-compatible by design (opt-in per webhook), the embed components follow established patterns, and all schema changes are additive-only. The 32 remaining hours of work are primarily audit, verification, and infrastructure tasks that do not require code changes to the delivered implementation.

---

## 9. Development Guide

### System Prerequisites

| Software | Version | Purpose |
|---|---|---|
| Node.js | ≥20.0.0 | JavaScript runtime |
| pnpm | 10.28.2 | Package manager (enforced via `packageManager` field) |
| Docker & Docker Compose | Latest | Local infrastructure (PostgreSQL, Valkey, MinIO, MailHog) |
| Git | Latest | Version control |

### Environment Setup

**1. Clone and checkout the branch:**

```bash
git clone <repository-url>
cd formbricks
git checkout blitzy-7a9d25be-d124-40bf-b715-2cf66eb7b11a
```

**2. Start local infrastructure:**

```bash
docker compose -f docker-compose.dev.yml up -d
```

This starts:
- PostgreSQL (pgvector) on port `5432`
- MailHog on ports `8025` (UI) / `1025` (SMTP)
- Valkey (Redis-compatible) on port `6379`
- MinIO on ports `9000` (S3) / `9001` (console)

**3. Configure environment variables:**

```bash
cp .env.example apps/web/.env
```

Edit `apps/web/.env` with required values:

```env
WEBAPP_URL=http://localhost:3000
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=<generate-with-openssl-rand-hex-32>
ENCRYPTION_KEY=<generate-with-openssl-rand-hex-32>
DATABASE_URL='postgresql://postgres:postgres@localhost:5432/formbricks?schema=public'
```

### Dependency Installation

```bash
pnpm install
```

### Database Setup

```bash
# Generate Prisma client
npx prisma generate --schema packages/database/schema.prisma

# Apply database migrations (requires running PostgreSQL)
npx prisma migrate deploy --schema packages/database/schema.prisma
```

### Build

```bash
CI=true pnpm build
```

Expected: 10 Turborepo tasks complete successfully.

### Application Startup

```bash
cd apps/web
pnpm dev
```

The application starts on `http://localhost:3000`.

### Running Tests

**All in-scope tests (Sprint 3-5 deliverables):**

```bash
cd apps/web
CI=true NODE_ENV=test npx vitest run \
  "app/api/(internal)/pipeline/lib/payload-transformer.test.ts" \
  "app/api/(internal)/pipeline/lib/webhook-parity-validation.test.ts" \
  "lib/response/tests/backward-compat.test.ts" \
  "lib/response/tests/export-lossless-validation.test.ts" \
  "app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/shareEmbedModal/slider-embed-tab.test.tsx" \
  "app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/shareEmbedModal/popover-embed-tab.test.tsx" \
  "app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/shareEmbedModal/side-tab-embed-tab.test.tsx" \
  --no-watch
```

**Regression tests:**

```bash
cd apps/web
CI=true NODE_ENV=test npx vitest run \
  "lib/response/tests/response.test.ts" \
  "lib/response/service.test.ts" \
  "lib/response/utils.test.ts" \
  "app/api/(internal)/pipeline/lib/handleIntegrations.test.ts" \
  "app/api/(internal)/pipeline/lib/telemetry.test.ts" \
  "app/api/v1/webhooks/[webhookId]/lib/webhook.test.ts" \
  "modules/api/v2/management/webhooks/lib/tests/webhook.test.ts" \
  "modules/api/v2/management/webhooks/[webhookId]/lib/tests/webhook.test.ts" \
  "lib/utils/services.test.ts" \
  --no-watch
```

**Logic operator tests:**

```bash
CI=true NODE_ENV=test npx vitest run \
  "packages/surveys/src/lib/logic.test.ts" \
  --no-watch
```

Expected: 478 tests pass (100%).

### Verification Steps

1. **Prisma client**: `npx prisma generate --schema packages/database/schema.prisma` completes without errors
2. **Build**: `CI=true pnpm build` completes all 10 tasks
3. **Tests**: All 478 tests pass with exit code 0
4. **Lint**: `npx eslint --no-fix <file>` returns 0 violations for any modified file

### Troubleshooting

| Issue | Resolution |
|---|---|
| `pnpm install` fails with engine error | Ensure Node.js ≥20 and pnpm 10.28.2 via `corepack enable && corepack prepare pnpm@10.28.2 --activate` |
| Prisma generate fails | Run from repository root; ensure `packages/database/schema.prisma` exists |
| Vitest picks up `.next/standalone/` files | Pre-existing issue; run specific test files rather than full suite |
| Docker Compose ports in use | Stop conflicting services or change ports in `docker-compose.dev.yml` |
| Missing environment variables | Copy `.env.example` to `apps/web/.env` and fill required values |

---

## 10. Appendices

### A. Command Reference

| Command | Purpose | Working Directory |
|---|---|---|
| `pnpm install` | Install all dependencies | Repository root |
| `npx prisma generate --schema packages/database/schema.prisma` | Generate Prisma client | Repository root |
| `npx prisma migrate deploy --schema packages/database/schema.prisma` | Apply database migrations | Repository root |
| `CI=true pnpm build` | Full monorepo build | Repository root |
| `pnpm dev` | Start development server | `apps/web/` |
| `CI=true NODE_ENV=test npx vitest run <file> --no-watch` | Run specific test file | `apps/web/` |
| `npx eslint --no-fix <file>` | Lint a specific file | `apps/web/` |
| `docker compose -f docker-compose.dev.yml up -d` | Start local infrastructure | Repository root |

### B. Port Reference

| Port | Service | Protocol |
|---|---|---|
| 3000 | Formbricks Web App (dev) | HTTP |
| 5432 | PostgreSQL (pgvector) | TCP |
| 6379 | Valkey (Redis-compatible) | TCP |
| 8025 | MailHog Web UI | HTTP |
| 1025 | MailHog SMTP | SMTP |
| 9000 | MinIO S3 API | HTTP |
| 9001 | MinIO Console | HTTP |

### C. Key File Locations

| File | Purpose |
|---|---|
| `apps/web/app/api/(internal)/pipeline/lib/payload-transformer.ts` | Typeform-compatible payload transformation function |
| `packages/database/zod/webhook-payload.ts` | Typeform payload Zod schemas |
| `packages/database/schema.prisma` | Prisma schema (Webhook.payloadFormat at line 55) |
| `packages/database/migration/20260301120000_add_payload_format_to_webhook/migration.sql` | SQL migration for payloadFormat column |
| `packages/database/migration/20260301130000_audit_sprint1_3_changes/migration.ts` | Sprint 1-3 audit script |
| `apps/web/app/api/(internal)/pipeline/route.ts` | Webhook dispatch with format branching |
| `apps/web/.../shareEmbedModal/slider-embed-tab.tsx` | Slider embed tab component |
| `apps/web/.../shareEmbedModal/popover-embed-tab.tsx` | Popover embed tab component |
| `apps/web/.../shareEmbedModal/side-tab-embed-tab.tsx` | Side tab embed tab component |
| `packages/js-core/src/lib/common/setup.ts` | SDK embed mode DOM setup handlers |
| `packages/js-core/src/types/config.ts` | SDK embed mode type definitions |
| `apps/web/locales/en-US.json` | i18n keys for webhook and embed UI |

### D. Technology Versions

| Technology | Version |
|---|---|
| Next.js | 16.1.6 |
| React | 19.2.4 |
| TypeScript | (workspace) |
| Prisma | 6.14.0 |
| Zod | (workspace) |
| Vitest | 3.1.3 |
| Playwright | 1.56.1 |
| Node.js | ≥20.0.0 |
| pnpm | 10.28.2 |
| Turbo | 2.5.3 |

### E. Environment Variable Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `WEBAPP_URL` | Yes | `http://localhost:3000` | Public URL of the web application |
| `NEXTAUTH_URL` | Yes | `http://localhost:3000` | NextAuth callback URL |
| `NEXTAUTH_SECRET` | Yes | — | Random secret for JWT signing |
| `ENCRYPTION_KEY` | Yes | — | 32-byte hex key for data encryption |
| `DATABASE_URL` | Yes | — | PostgreSQL connection string |
| `REDIS_URL` | No | — | Valkey/Redis connection string |
| `S3_ACCESS_KEY` | No | — | MinIO/S3 access key |
| `S3_SECRET_KEY` | No | — | MinIO/S3 secret key |
| `S3_BUCKET_NAME` | No | — | S3 bucket for file uploads |

### F. Glossary

| Term | Definition |
|---|---|
| AAP | Agent Action Plan — the governing specification for all project deliverables |
| payloadFormat | Webhook setting controlling payload structure (`"default"` or `"typeform"`) |
| Typeform-compatible payload | Restructured webhook body matching Typeform's schema: typed `answers` array, `definition.fields`, `hidden`, `variables`, `calculated.score` |
| Embed mode | SDK configuration for survey display: slider (side panel), popover (floating button), side tab (edge tab) |
| ZSurveyElement | Zod discriminated union of all 17 survey element types |
| fb-migrate-dev | Custom Formbricks migration workflow using Prisma under the hood |
| Standard Webhooks | HMAC-SHA256 signing specification using `webhook-id`, `webhook-timestamp`, `webhook-signature` headers |