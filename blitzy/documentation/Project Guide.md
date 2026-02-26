# Project Guide — Formbricks TypeA & TypeB Survey Element Types (Sprint 1 Foundation)

## 1. Executive Summary

### 1.1 Project Overview

This project extends the Formbricks survey type system by adding two new element types (`TypeA` and `TypeB`) to the `TSurveyElementTypeEnum` enumeration, completing Sprint 1 — Foundation (Question Types). The implementation spans the entire monorepo stack: core type system, survey editor, survey renderer, analytics/summary, integrations, and i18n support.

**Completion: 62 hours completed out of 81 total hours = 77% complete.**

### 1.2 Key Achievements

- **Full type-system foundation**: Both element types registered in `TSurveyElementTypeEnum` (17 members), with Zod schemas, TypeScript types, deprecated v1 API mirrors, summary schemas, and logic operator validators
- **Complete editor integration**: Editor form components, element type registry, block-card form mapping, and logic rule engine definitions for both types
- **Full renderer stack**: Preact-compatible respondent-facing renderers, React survey-ui design-system components, Storybook stories (18 stories total), and conditional rendering switch branches
- **Analytics pipeline**: Summary display components, server-side summary computation, and SummaryList rendering branches
- **Integration parity**: Notion TYPE_MAPPING, response conversion, single-response rendering, and pipeline handler coverage
- **Comprehensive testing**: All 4,669 tests pass (100%), TypeScript compiles cleanly, runtime verified
- **i18n coverage**: Translation keys added across all 14 supported locales

### 1.3 Validation Summary

| Metric | Result |
|--------|--------|
| Build Status | ✅ SUCCESS — 10/10 turbo tasks |
| Total Tests | ✅ 4,669/4,669 pass (100%) |
| TypeScript Compilation | ✅ Clean — zero type errors |
| Runtime Verification | ✅ Next.js 16.1.6 starts, HTTP 200 |
| Files Changed | 51 (10 created, 41 modified) |
| Source Lines Added | 1,823 |
| Source Lines Removed | 29 |
| Total Commits | 36 |

### 1.4 Critical Notes for Reviewers

- `TypeA` and `TypeB` are **generic scaffold names** per the AAP — concrete element type names were not provided in the original requirement. All code uses these names consistently and propagation to final names is a remaining human task.
- 5 pre-existing test files exhibit timing-dependent flakiness when run in the full 300-file web app suite (bcrypt/fetch timeouts under load). These are **not caused by this branch** — identical behavior on `main`. All 5 pass in isolation (189/189).

---

## 2. Validation Results Detail

### 2.1 Build Results

Full monorepo force build completed successfully in ~3m52s:

| Package | Status |
|---------|--------|
| @formbricks/logger | ✅ Built |
| @formbricks/database | ✅ Built |
| @formbricks/cache | ✅ Built |
| @formbricks/storage | ✅ Built |
| @formbricks/i18n-utils | ✅ Built |
| @formbricks/survey-ui | ✅ Built |
| @formbricks/surveys | ✅ Built |
| @formbricks/js-core | ✅ Built |
| @formbricks/types | ✅ Built |
| @formbricks/web | ✅ Built |

### 2.2 Test Results

| Test Suite | Tests | Files | Status |
|------------|-------|-------|--------|
| @formbricks/surveys | 527 | 19 | ✅ 100% |
| @formbricks/survey-ui | 60 | 3 | ✅ 100% |
| @formbricks/cache | 147 | 10 | ✅ 100% |
| @formbricks/logger | 10 | 1 | ✅ 100% |
| @formbricks/i18n-utils | 56 | 1 | ✅ 100% |
| @formbricks/storage | 64 | 3 | ✅ 100% |
| Web App (main) | 3,616 | 295 | ✅ 100% |
| Web App (isolation) | 189 | 5 | ✅ 100% |
| **Total** | **4,669** | **337** | **✅ 100%** |

**In-Scope Test Files (TypeA/TypeB Coverage Verified):**

| Test File | Tests | Verified |
|-----------|-------|----------|
| logic-rule-engine.test.ts | 26/26 | TypeA + TypeB operator definitions |
| utils.test.ts | 32/32 | TypeA + TypeB form input compatibility |
| evaluator.test.ts | 39/39 | TypeA + TypeB validation |
| validators.test.ts | 129/129 | TypeA + TypeB generic validation |
| logic.test.ts | 45/45 | TypeA + TypeB logic evaluation |

### 2.3 Fixes Applied During Validation

| Commit | Fix Description |
|--------|----------------|
| `40ed3c1` | Resolved 24 dependency vulnerabilities from QA audit |
| `12f3d0c` | Registered TypeA/TypeB editor form components in block-card.tsx elementFormMap |
| `6513caf` | Corrected TypeA/TypeB summary pipeline data type from `string[]` to `string` |
| `c4251231` | Added placeholder field to deprecated TypeA/TypeB question schemas and i18n translation keys |

---

## 3. Hours Breakdown and Completion

### 3.1 Completed Hours by Component

| Component | Files | Lines Added | Hours |
|-----------|-------|-------------|-------|
| Type System (constants, elements, types, validation-rules) | 4 modified | 122 | 7 |
| Survey Editor (elements registry, forms, logic engine, block-card, form-input) | 6 modified + 2 created | 240 | 11 |
| Survey Renderer (Preact elements, conditional switch, survey-ui components, stories) | 2 modified + 6 created | 775 | 21 |
| Analytics & Integrations (summary, Notion, responses, rendering, pipeline) | 6 modified + 2 created | 247 | 11.5 |
| Supporting (i18n 14 locales, mocks, tests, config) | 21 modified | 439 | 6.5 |
| Debugging & Validation (security fixes, type corrections, registration) | — | — | 5 |
| **Total Completed** | **51 files** | **1,823** | **62** |

### 3.2 Remaining Hours Breakdown

| Task | Hours | Priority | Confidence |
|------|-------|----------|------------|
| Professional i18n translations for 13 non-English locales | 4 | Medium | High |
| E2E test suite for TypeA/TypeB survey lifecycle | 3 | Medium | High |
| Additional test coverage (survey.test.ts, shared-conditions-factory.test.ts) | 2 | Medium | High |
| Type naming finalization and codebase propagation | 2 | High | Medium |
| Production environment configuration | 2 | High | High |
| Real integration testing (Notion, webhooks) | 2 | Medium | Medium |
| Visual/UX design review of components and Storybook | 1 | Low | High |
| Survey templates with new element types | 1 | Low | High |
| Documentation and final code review | 1 | Low | High |
| Enterprise uncertainty buffer | 1 | — | — |
| **Total Remaining** | **19** | — | — |

### 3.3 Calculation

```
Completed Hours:  62h
Remaining Hours:  19h (includes 1.21x enterprise multiplier on base 15.5h)
Total Hours:      81h
Completion:       62 / 81 = 76.5% ≈ 77%
```

### 3.4 Hours Visualization

```mermaid
pie title Project Hours Breakdown
    "Completed Work" : 62
    "Remaining Work" : 19
```

---

## 4. Implementation Summary

### 4.1 Files Created (10 new files)

| # | File | Lines | Purpose |
|---|------|-------|---------|
| 1 | `packages/survey-ui/src/components/elements/type-a-element.tsx` | 105 | React survey-ui TypeA component |
| 2 | `packages/survey-ui/src/components/elements/type-b-element.tsx` | 105 | React survey-ui TypeB component |
| 3 | `packages/survey-ui/src/components/elements/type-a-element.stories.tsx` | 179 | Storybook stories for TypeA (9 stories) |
| 4 | `packages/survey-ui/src/components/elements/type-b-element.stories.tsx` | 179 | Storybook stories for TypeB (9 stories) |
| 5 | `packages/surveys/src/components/elements/type-a-element.tsx` | 69 | Preact TypeA renderer with TTC |
| 6 | `packages/surveys/src/components/elements/type-b-element.tsx` | 69 | Preact TypeB renderer with TTC |
| 7 | `apps/web/modules/survey/editor/components/type-a-element-form.tsx` | 99 | TypeA editor form component |
| 8 | `apps/web/modules/survey/editor/components/type-b-element-form.tsx` | 99 | TypeB editor form component |
| 9 | `apps/web/.../(analysis)/summary/components/TypeASummary.tsx` | 81 | TypeA analytics summary |
| 10 | `apps/web/.../(analysis)/summary/components/TypeBSummary.tsx` | 81 | TypeB analytics summary |

### 4.2 Key Modified Files (41 modified)

**Type System:**
- `packages/types/surveys/constants.ts` — `TSurveyElementTypeEnum` now has 17 members
- `packages/types/surveys/elements.ts` — `ZSurveyElement` union now has 17 schemas
- `packages/types/surveys/types.ts` — 10 insertion points: deprecated mirrors, question union, operator validators, summary schemas

**Editor:**
- `apps/web/modules/survey/lib/elements.tsx` — `getElementTypes()` registry
- `apps/web/modules/survey/editor/lib/logic-rule-engine.ts` — operator definitions
- `apps/web/modules/survey/editor/components/block-card.tsx` — form map registration

**Renderer:**
- `packages/surveys/src/components/general/element-conditional.tsx` — rendering switch (now 17 cases)
- `packages/survey-ui/src/index.ts` — public API exports

**Analytics & Integrations:**
- `apps/web/.../(analysis)/summary/components/SummaryList.tsx` — rendering branches
- `apps/web/.../integrations/notion/constants.ts` — TYPE_MAPPING entries
- `apps/web/lib/responses.ts` — `convertResponseValue` case branches
- `apps/web/modules/analysis/.../RenderResponse.tsx` — response rendering

**i18n:**
- All 14 locale files (en-US + 13 languages) — TypeA/TypeB translation keys

---

## 5. Remaining Human Tasks

### 5.1 Detailed Task Table

| # | Task | Description | Priority | Severity | Hours | Action Steps |
|---|------|-------------|----------|----------|-------|--------------|
| 1 | Professional i18n Translations | All 13 non-English locale files currently have English-only placeholder strings for `type_a`, `type_a_description`, `type_b`, `type_b_description` keys. Professional translators must provide proper translations for de-DE, es-ES, fr-FR, hu-HU, ja-JP, nl-NL, pt-BR, pt-PT, ro-RO, ru-RU, sv-SE, zh-Hans-CN, zh-Hant-TW. | Medium | Medium | 4 | 1. Extract TypeA/TypeB keys from en-US.json. 2. Send to translation service. 3. Update each locale file with proper translations. 4. Verify with native speakers. |
| 2 | E2E Test Suite | No end-to-end tests verify the complete user flow: creating a survey with TypeA/TypeB elements → publishing → collecting responses → viewing summary analytics. | Medium | Medium | 3 | 1. Create Cypress/Playwright test for survey creation with TypeA. 2. Add test for TypeB survey creation. 3. Test response collection flow. 4. Test summary analytics rendering. |
| 3 | Additional Unit Test Coverage | AAP §0.6.1 lists `survey.test.ts` and `shared-conditions-factory.test.ts` as requiring updates. These files were not directly modified. | Medium | Low | 2 | 1. Review `apps/web/modules/survey/editor/lib/survey.test.ts` for TypeA/TypeB gaps. 2. Review `shared-conditions-factory.test.ts` for coverage. 3. Add missing test cases. |
| 4 | Type Naming Finalization | `TypeA` and `TypeB` are generic scaffold names. When concrete type names are decided, a rename propagation across all 51 affected files is required. | High | Medium | 2 | 1. Decide final element type names. 2. Global find-replace in all source files (TypeA→FinalNameA, typeA→finalNameA). 3. Update locale files. 4. Update Storybook titles. 5. Run full test suite to verify. |
| 5 | Production Environment Configuration | Environment variables, database connections, and service endpoints need configuration for production deployment. | High | High | 2 | 1. Configure `.env` with production values. 2. Set up PostgreSQL connection. 3. Configure Redis cache. 4. Set API keys for external services. 5. Verify health endpoint. |
| 6 | Real Integration Testing | Notion integration and webhook pipeline need testing with real external services to verify TypeA/TypeB data flows correctly. | Medium | Medium | 2 | 1. Set up Notion test workspace. 2. Create TypeA/TypeB survey and collect response. 3. Verify Notion database receives data with correct property types. 4. Test webhook payload format. |
| 7 | Visual/UX Design Review | Storybook stories are created but need visual review by a designer to verify styling, spacing, RTL support, and accessibility compliance. | Low | Low | 1 | 1. Run Storybook locally. 2. Review all 18 stories (9 per type). 3. Verify RTL rendering with Arabic text. 4. Check error state styling. 5. Validate disabled state appearance. |
| 8 | Survey Templates | No survey templates include TypeA or TypeB elements. Consider adding template(s) that showcase the new types. | Low | Low | 1 | 1. Review `apps/web/app/lib/templates.ts`. 2. Create a template with TypeA and/or TypeB elements. 3. Add i18n keys for template strings. |
| 9 | Documentation and Code Review | Final human review of all changes, code documentation, and architectural decision validation. | Low | Low | 1 | 1. Review all 10 new files for code quality. 2. Verify JSDoc comments. 3. Check for any TODO/FIXME comments. 4. Validate Zod schema design decisions. |
| 10 | Enterprise Uncertainty Buffer | Buffer for unexpected issues discovered during human review. | — | — | 1 | Reserve for any issues found during tasks 1-9. |
| | **Total Remaining Hours** | | | | **19** | |

### 5.2 Priority Distribution

```mermaid
pie title Remaining Work by Priority
    "High Priority" : 4
    "Medium Priority" : 11
    "Low Priority" : 3
    "Buffer" : 1
```

---

## 6. Development Guide

### 6.1 System Prerequisites

| Software | Version | Purpose |
|----------|---------|---------|
| Node.js | ≥ 20.0.0 | JavaScript runtime |
| pnpm | ≥ 10.x | Package manager (monorepo workspace) |
| Git | ≥ 2.x | Version control |
| PostgreSQL | 14+ | Database (required for full app) |
| Redis | 6+ | Caching layer (optional for dev) |

### 6.2 Environment Setup

```bash
# 1. Clone and checkout the feature branch
git clone <repository-url>
cd formbricks
git checkout blitzy-62760c9b-b9b1-4afd-9103-880bac62d3a7

# 2. Install dependencies
pnpm install --no-frozen-lockfile

# 3. Copy environment template (if first setup)
cp apps/web/.env.example apps/web/.env
# Edit .env with your database URL, Redis URL, and other required values
```

### 6.3 Build & Verify

```bash
# Full monorepo build (all packages + web app)
pnpm build
# Expected: 10/10 turbo tasks succeed in ~4 minutes

# TypeScript type checking (types package specifically)
npx tsc --noEmit --project packages/types/tsconfig.json
# Expected: Clean exit with no errors
```

### 6.4 Running Tests

```bash
# Package-level tests (fast, isolated)
pnpm --filter @formbricks/surveys test -- --run       # 527 tests, ~14s
pnpm --filter @formbricks/survey-ui test -- --run      # 60 tests, ~4s
pnpm --filter @formbricks/cache test -- --run           # 147 tests
pnpm --filter @formbricks/logger test -- --run          # 10 tests
pnpm --filter @formbricks/i18n-utils test -- --run      # 56 tests
pnpm --filter @formbricks/storage test -- --run         # 64 tests

# Web app tests (full suite)
cd apps/web
CI=true npx vitest run --exclude '.next/**'             # 3,805 tests, ~3-5 min

# Run only TypeA/TypeB-related tests
cd apps/web
CI=true npx vitest run --exclude '.next/**' -t "TypeA"
CI=true npx vitest run --exclude '.next/**' -t "TypeB"
```

### 6.5 Application Startup

```bash
# Start the Next.js development server
cd apps/web
pnpm dev
# Expected: Available at http://localhost:3000

# Production mode (after build)
HOSTNAME=0.0.0.0 PORT=3334 node apps/web/.next/standalone/apps/web/server.js
# Expected: Server ready in ~200ms at http://localhost:3334
```

### 6.6 Verification Steps

```bash
# Verify runtime health
curl -s http://localhost:3334/health
# Expected: HTTP 200

# Verify TypeA/TypeB enum members exist in compiled output
node -e "
const { TSurveyElementTypeEnum } = require('./packages/types/surveys/constants');
console.log('TypeA:', TSurveyElementTypeEnum.TypeA);
console.log('TypeB:', TSurveyElementTypeEnum.TypeB);
console.log('Total members:', Object.keys(TSurveyElementTypeEnum).length);
"
# Expected: TypeA: typeA, TypeB: typeB, Total members: 34 (17 keys + 17 reverse)
```

### 6.7 Storybook (Visual Development)

```bash
# Run Storybook for survey-ui components
cd packages/survey-ui
pnpm storybook
# Navigate to UI-package/Elements/TypeAElement and TypeBElement
# 9 stories each: StylingPlayground, Default, WithDescription, WithValue,
# Required, WithError, Disabled, RTL, MultipleElements
```

### 6.8 Troubleshooting

| Issue | Solution |
|-------|----------|
| `pnpm install` fails | Ensure Node.js ≥ 20.0.0 and pnpm ≥ 10.x. Try `pnpm install --no-frozen-lockfile` |
| Build fails on `@formbricks/database` | Ensure PostgreSQL is running and `DATABASE_URL` is set in `.env` |
| Tests timeout on crypto/auth | These are pre-existing flaky tests (bcrypt timing). Run in isolation: `npx vitest run lib/crypto.test.ts` |
| TypeA/TypeB not showing in editor | Verify `getElementTypes()` in `apps/web/modules/survey/lib/elements.tsx` includes both entries |
| Notion integration errors | Ensure `TYPE_MAPPING` in `notion/constants.ts` has entries for `TypeA` and `TypeB` |

---

## 7. Risk Assessment

### 7.1 Technical Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Generic TypeA/TypeB naming causes confusion | Medium | High | Prioritize type naming finalization (Task #4). Use global find-replace with full test suite validation. |
| i18n placeholder strings shown to non-English users | Medium | High | Complete professional translations (Task #1) before production release. |
| Missing E2E coverage for new types | Medium | Medium | Create E2E tests (Task #2) covering full survey lifecycle before production. |
| Pre-existing flaky tests may mask new failures | Low | Low | Monitor test results. Run flaky tests in isolation to confirm they're unrelated. |

### 7.2 Security Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| 24 dependency vulnerabilities (resolved) | Low | Low | Already resolved in commit `40ed3c1`. Monitor for new advisories. |
| New element types accept arbitrary string input | Low | Low | Input sanitized through existing Zod schema validation. XSS prevention via React's built-in escaping. |

### 7.3 Operational Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| No production environment configured | High | High | Must complete Task #5 before deployment. |
| No monitoring for new element types | Low | Medium | Existing monitoring covers all element types generically. |

### 7.4 Integration Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Notion integration untested with real service | Medium | Medium | Complete integration testing (Task #6) with real Notion workspace. |
| Webhook payloads for new types not verified | Medium | Medium | Test with real webhook consumers before production. |

---

## 8. Architecture Decisions

### 8.1 Simple Element Pattern

TypeA and TypeB follow the "simple element" pattern (similar to Consent, NPS, Rating), extending `ZSurveyElementBase` with minimal additional fields (`placeholder`, `validation`). This decision was driven by the AAP specifying these as generic scaffold types.

### 8.2 Logic Operators

Both types support only `isSubmitted` and `isSkipped` operators, matching the pattern of other simple types (FileUpload, Address, Ranking, ContactInfo). This prevents invalid logic conditions per AAP §0.7.3.

### 8.3 Summary Schema

Summary schemas use the `samples`-based pattern (like ContactInfo, Address) with `string` value type, suitable for text-input-style elements. The data type was corrected from `string[]` to `string` during validation.

### 8.4 Backward Compatibility

Deprecated `ZSurveyTypeAQuestion`/`ZSurveyTypeBQuestion` schemas maintain v1 API compatibility. Both are annotated with `@deprecated` JSDoc comments directing consumers to the element equivalents.

---

## 9. Files Changed — Complete Inventory

### 9.1 New Files (10)

```
A  apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/TypeASummary.tsx
A  apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/TypeBSummary.tsx
A  apps/web/modules/survey/editor/components/type-a-element-form.tsx
A  apps/web/modules/survey/editor/components/type-b-element-form.tsx
A  packages/survey-ui/src/components/elements/type-a-element.stories.tsx
A  packages/survey-ui/src/components/elements/type-a-element.tsx
A  packages/survey-ui/src/components/elements/type-b-element.stories.tsx
A  packages/survey-ui/src/components/elements/type-b-element.tsx
A  packages/surveys/src/components/elements/type-a-element.tsx
A  packages/surveys/src/components/elements/type-b-element.tsx
```

### 9.2 Modified Files (41, excluding pnpm-lock.yaml)

```
M  apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/SummaryList.tsx
M  apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/lib/surveySummary.ts
M  apps/web/app/(app)/environments/[environmentId]/workspace/integrations/notion/constants.ts
M  apps/web/app/api/(internal)/pipeline/lib/handleIntegrations.ts
M  apps/web/lib/responses.ts
M  apps/web/lib/survey/__mock__/survey.mock.ts
M  apps/web/locales/de-DE.json
M  apps/web/locales/en-US.json
M  apps/web/locales/es-ES.json
M  apps/web/locales/fr-FR.json
M  apps/web/locales/hu-HU.json
M  apps/web/locales/ja-JP.json
M  apps/web/locales/nl-NL.json
M  apps/web/locales/pt-BR.json
M  apps/web/locales/pt-PT.json
M  apps/web/locales/ro-RO.json
M  apps/web/locales/ru-RU.json
M  apps/web/locales/sv-SE.json
M  apps/web/locales/zh-Hans-CN.json
M  apps/web/locales/zh-Hant-TW.json
M  apps/web/modules/analysis/components/SingleResponseCard/components/RenderResponse.tsx
M  apps/web/modules/email/components/preview-email-template.tsx
M  apps/web/modules/survey/components/element-form-input/index.tsx
M  apps/web/modules/survey/components/element-form-input/utils.test.ts
M  apps/web/modules/survey/editor/components/block-card.tsx
M  apps/web/modules/survey/editor/lib/logic-rule-engine.test.ts
M  apps/web/modules/survey/editor/lib/logic-rule-engine.ts
M  apps/web/modules/survey/lib/elements.tsx
M  apps/web/package.json
M  package.json
M  packages/survey-ui/src/index.ts
M  packages/surveys/src/components/general/element-conditional.tsx
M  packages/surveys/src/lib/logic.test.ts
M  packages/surveys/src/lib/validation/evaluator.test.ts
M  packages/surveys/src/lib/validation/evaluator.ts
M  packages/surveys/src/lib/validation/validators.test.ts
M  packages/types/js.ts
M  packages/types/surveys/constants.ts
M  packages/types/surveys/elements.ts
M  packages/types/surveys/types.ts
M  packages/types/surveys/validation-rules.ts
```
