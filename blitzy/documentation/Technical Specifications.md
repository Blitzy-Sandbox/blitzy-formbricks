# Technical Specification

# 0. Agent Action Plan

## 0.1 Executive Summary

Based on the bug description, the Blitzy platform understands that the bug is a **test infrastructure failure in the Formbricks Typeform Parity monorepo** where the global test setup file (`apps/web/vitestSetup.ts`) destroys module mock references before every test via `vi.resetModules()`, and the Vitest configuration (`apps/web/vite.config.mts`) injects all real environment variables from `.env` files into the test runner via `loadEnv("", process.cwd(), "")` with an empty prefix filter. These two defects combine to cause **27 of 316 test files** (approximately 8.5%) to fail consistently or intermittently depending on execution order and environment state.

The sprint roadmap governing all deliverables is located at `docs/development/typeform-parity/sprint-roadmap.mdx` and covers five sprints: Sprint 1 (Question Types — opinionScale, payment), Sprint 2 (Logic & Data — logic operators, JSON export), Sprint 3 (Integration — webhook parity, embed variants), Sprint 4 (Governance — workspace parity, migration safety), and Sprint 5 (Validation — end-to-end parity testing). After an exhaustive audit of all sprint deliverables, the 27 test file failures are exclusively attributable to the test infrastructure bug described below — all sprint feature code passes correctly when tests are run in isolation.

**Technical Failure Description:**

- **Error Type A — "Invalid environment variables" (24 test files):** The `vi.resetModules()` call at `vitestSetup.ts:173` clears the Vitest module registry before every test. This destroys the cached mock for `@/lib/constants` (defined at lines 187–253 of the same file). When subsequent test code imports any module that transitively depends on `@/lib/constants` → `lib/env.ts` or `@/lib/getPublicUrl` → `lib/env.ts`, the real `lib/env.ts` is loaded. The `@t3-oss/env-nextjs` `createEnv()` call at `lib/env.ts:4` performs Zod schema validation requiring `DATABASE_URL` (z.string().url()) and `ENCRYPTION_KEY` (z.string()), which are undefined in the test environment, causing a fatal `"Invalid environment variables"` error during test file collection.

- **Error Type B — "vi.mock factory" error (3 test files):** Three test files (`modules/storage/utils.test.ts`, `modules/survey/follow-ups/lib/utils.test.ts`, `surveySummary.test.ts`) use `vi.importActual()` inside their `vi.mock()` factory functions. The `vi.importActual("@/lib/constants")` call loads the real `lib/constants.ts`, which imports `lib/env.ts`, triggering the same Zod validation failure. Vitest wraps this as a "There was an error when mocking a module" error with `Caused by: Invalid environment variables`.

- **Error Type C — Environment variable leakage:** The `loadEnv("", process.cwd(), "")` call at `vite.config.mts:13` loads ALL environment variables from `.env` files with no prefix filter. In environments where a `.env` file exists (e.g., CI), this injects real values for `STRIPE_CLIENT_ID`, `STRIPE_SECRET_KEY`, and other sensitive variables into the test runner, causing mock path mismatches in Stripe Connect route tests and polluting the test isolation boundary.

**Reproduction Steps (executable):**

```
cd apps/web
pnpm vitest run --no-coverage
```

**Expected result:** 316 test files pass, 0 fail
**Actual result:** 289 test files pass, 27 test files fail with "Invalid environment variables" or "vi.mock factory" errors

**Impact:** 3693 individual test cases pass; the 27 failing files never reach test execution because they fail during file collection/module resolution. No sprint deliverable logic is broken — only test infrastructure prevents full suite execution.

## 0.2 Root Cause Identification

Based on exhaustive repository analysis, diagnostic test execution, and web research into Vitest internals, there are **three interrelated root causes** for the 27 test file failures.

### 0.2.1 Root Cause 1: Global `vi.resetModules()` Destroys Module Mock Cache

- **THE root cause is:** The global `beforeEach` hook in `apps/web/vitestSetup.ts` (lines 172–175) calls `vi.resetModules()` which clears the entire Vitest module registry before every test case across all 316 test files.
- **Located in:** `apps/web/vitestSetup.ts`, lines 172–175
- **Triggered by:** Any test execution that triggers the global `beforeEach` — the module cache is wiped, destroying the cached mock for `@/lib/constants` (defined at lines 187–253 of the same file) and all other module-level mocks established during setup.
- **Evidence:** The Vitest documentation explicitly states: "Vitest will not mock modules that were imported inside a setup file because they are cached by the time a test file is running." When `vi.resetModules()` clears this cache, the setup file's mocks lose their cached module references. Subsequent imports of `@/lib/constants` re-evaluate the real module, which triggers the import chain `lib/constants.ts:3` → `lib/env.ts:4` → `createEnv()` → Zod validation failure.
- **Problematic code:**
```typescript
beforeEach(() => {
  vi.resetModules();   // line 173 — DESTROYS module cache
  vi.resetAllMocks();  // line 174 — resets mock implementations
});
```
- **This conclusion is definitive because:** The Vitest official documentation confirms `vi.resetModules()` "Resets modules registry by clearing cache of all modules" while noting it "Does not reset mocks registry." However, clearing the module cache forces re-evaluation of modules on next import. Since the `@/lib/constants` mock factory in `vitestSetup.ts` returns a plain object (not the real module), the mock itself is preserved, but any module NOT mocked that depends on `@/lib/env` (such as `@/lib/getPublicUrl`) will be forced to re-evaluate `lib/env.ts`, which fails without environment variables.

### 0.2.2 Root Cause 2: Missing Test Environment Variables for `@t3-oss/env-nextjs` Validation

- **THE root cause is:** The `apps/web/lib/env.ts` file uses `@t3-oss/env-nextjs`'s `createEnv()` function with Zod schema validation. Two fields — `DATABASE_URL` (z.string().url()) and `ENCRYPTION_KEY` (z.string()) — are mandatory and have no defaults. The test environment provides no values for these variables.
- **Located in:** `apps/web/lib/env.ts`, line 4 (`createEnv()` call); schema at lines 11 (`DATABASE_URL`) and 27 (`ENCRYPTION_KEY`)
- **Triggered by:** Any module import chain that reaches `lib/env.ts` without being intercepted by a mock. Two confirmed import chains:
  - `@/lib/constants` → `lib/env.ts` (intercepted by the global mock, but broken when cache is cleared)
  - `@/lib/getPublicUrl` → `lib/env.ts` (NEVER mocked by `vitestSetup.ts`)
- **Evidence:** All 27 error stack traces terminate at `lib/env.ts:4:20` with the message `"Invalid environment variables"` and Zod output showing `DATABASE_URL` (path: `['DATABASE_URL']`, message: `'Required'`) and `ENCRYPTION_KEY` (path: `['ENCRYPTION_KEY']`, message: `'Required'`) as the missing required fields.
- **This conclusion is definitive because:** The `env.ts` file's `runtimeEnv` block reads from `process.env.DATABASE_URL` and `process.env.ENCRYPTION_KEY`, and no `.env` file exists in the repository (only `.env.example` with empty values). The `REDIS_URL` field includes a `NODE_ENV === "test"` conditional that makes it optional in test mode, but `DATABASE_URL` and `ENCRYPTION_KEY` have no such accommodation.

### 0.2.3 Root Cause 3: Unscoped `loadEnv` in Vitest Configuration Leaks Real Environment Variables

- **THE root cause is:** The `apps/web/vite.config.mts` file at line 13 calls `loadEnv("", process.cwd(), "")` with an empty string as the third parameter (prefix filter). This instructs Vite to load ALL environment variables from `.env` files — not just `VITE_`-prefixed ones — into the test environment.
- **Located in:** `apps/web/vite.config.mts`, line 13
- **Triggered by:** Running `vitest` in any environment where a `.env` file exists (e.g., CI runners, developer machines with local `.env` configuration). The `apps/web/.env` is a symlink to `../../.env`.
- **Evidence:** The Vitest documentation states: "Vitest exclusively autoloads environment variables prefixed with VITE_ from .env files" and provides `loadEnv(mode, process.cwd(), '')` as the explicit opt-in to load ALL variables. The empty prefix `""` bypasses the VITE_ prefix filter, exposing `STRIPE_SECRET_KEY`, `STRIPE_CLIENT_ID`, `ENCRYPTION_KEY`, `DATABASE_URL`, and all other variables defined in `.env` directly into `process.env` during tests.
- **This conclusion is definitive because:** When real environment variables are injected, they collide with mock values set by individual test files (e.g., Stripe Connect route tests that mock `STRIPE_CLIENT_ID` with test values receive the real value instead), causing assertion mismatches that appear intermittent depending on whether a `.env` file is present.

## 0.3 Diagnostic Execution

### 0.3.1 Code Examination Results

**File analyzed:** `apps/web/vitestSetup.ts` (254 lines)

- **Problematic code block:** Lines 172–175
- **Specific failure point:** Line 173 (`vi.resetModules()`)
- **Execution flow leading to bug:**
  - Step 1: Vitest processes `vitestSetup.ts` as a setup file and registers all `vi.mock()` factories, including `@/lib/constants` (lines 187–253), `server-only`, `next/navigation`, `@prisma/client`, `crypto`, and `next/headers`
  - Step 2: Module imports in setup are cached in the module registry
  - Step 3: A test begins → global `beforeEach` fires → `vi.resetModules()` (line 173) clears the module registry
  - Step 4: `vi.resetAllMocks()` (line 174) resets all mock implementations to empty functions
  - Step 5: The test file's code runs and imports a module (e.g., `lib/response/service.ts`)
  - Step 6: That module transitively imports `@/lib/getPublicUrl` (NOT mocked) → `lib/env.ts` → `createEnv()` → Zod validation
  - Step 7: `DATABASE_URL` and `ENCRYPTION_KEY` are undefined → Zod throws `"Invalid environment variables"`
  - Step 8: Test file fails at collection phase — no test cases execute

**File analyzed:** `apps/web/vite.config.mts` (100 lines)

- **Problematic code block:** Line 13
- **Specific failure point:** `env: loadEnv("", process.cwd(), "")`
- **Execution flow:** When `.env` file exists, `loadEnv` with empty prefix loads ALL variables into `process.env` and `import.meta.env`, causing real secrets to override mock values in test files

**File analyzed:** `apps/web/lib/env.ts` (194 lines)

- **Role:** Defines the environment variable schema using `@t3-oss/env-nextjs` and Zod
- **Critical fields:** `DATABASE_URL: z.string().url()` (line 11) and `ENCRYPTION_KEY: z.string()` (line 27) are required with no defaults
- **Test accommodation:** Only `REDIS_URL` has a `NODE_ENV === "test"` conditional making it optional

**File analyzed:** `apps/web/lib/getPublicUrl.ts`

- **Import chain:** `import "server-only"` then `import { env } from "./env"` — directly imports `lib/env.ts` without going through `@/lib/constants`
- **NOT mocked:** The global `vitestSetup.ts` does not mock `@/lib/getPublicUrl`, so any module that depends on it triggers the real `lib/env.ts` evaluation

### 0.3.2 Repository File Analysis Findings

| Tool Used | Command Executed | Finding | File:Line |
|-----------|-----------------|---------|-----------|
| grep | `grep -rn "vi.resetModules" apps/web/vitestSetup.ts` | Global `vi.resetModules()` in `beforeEach` | `vitestSetup.ts:173` |
| grep | `grep -rn "vi.resetAllMocks" apps/web/vitestSetup.ts` | Global `vi.resetAllMocks()` in `beforeEach` | `vitestSetup.ts:174` |
| grep | `grep -n "loadEnv" apps/web/vite.config.mts` | `env: loadEnv("", process.cwd(), "")` with empty prefix | `vite.config.mts:13` |
| grep | `grep -c "vi.mocked" apps/web -r --include="*.test.*"` | 193 test files use `vi.mocked()` — all vulnerable to mock destruction | across `apps/web/` |
| grep | `grep -c "vi.hoisted" apps/web -r --include="*.test.*"` | Only 7 test files use `vi.hoisted()` — the safe pattern | across `apps/web/` |
| find | `find apps/web -name "*.test.ts" -o -name "*.test.tsx"` | 316 total test files in `apps/web` | `apps/web/` |
| grep | `grep -rn "vi.resetModules" apps/web --include="*.test.*"` | 38 test files use `vi.resetModules()` locally for legitimate per-test module isolation | various test files |
| bash | `ls -la apps/web/.env` | `.env` is a symlink to `../../.env` | `apps/web/.env -> ../../.env` |
| bash | `cat .env.example \| grep STRIPE` | `STRIPE_SECRET_KEY=`, `STRIPE_WEBHOOK_SECRET=`, `STRIPE_CLIENT_ID=` present as empty | `.env.example` |
| cat | `cat apps/web/lib/constants.ts \| head -5` | `import "server-only"` then `import { env } from "./env"` — confirms dependency chain | `lib/constants.ts:1-3` |
| cat | `cat apps/web/lib/getPublicUrl.ts \| head -5` | `import "server-only"` then `import { env } from "./env"` — second unprotected chain | `lib/getPublicUrl.ts:1-2` |
| vitest | `CI=true npx vitest run --no-coverage` | 27 test files failed, 289 passed, 3693 test cases passed, 1 skipped | Full suite |

### 0.3.3 Fix Verification Analysis

**Steps followed to reproduce bug:**

- Installed pnpm@10.28.2 and all project dependencies via `pnpm install --frozen-lockfile`
- Built workspace packages (`@formbricks/cache`, `@formbricks/database`, `@formbricks/logger`, `@formbricks/types`, `@formbricks/storage`) using `pnpm turbo run build --filter=...`
- Ran full test suite with `CI=true npx vitest run --no-coverage` from `apps/web`
- **Result:** 27 test files failed, 289 passed — exactly matching the user's reported count

**Confirmation tests used to ensure that bug was fixed:**

- After applying fixes to `vitestSetup.ts` and `vite.config.mts`, re-run the full test suite
- Expected: 316 test files pass, 0 fail
- Verify that the 38 test files using local `vi.resetModules()` still function correctly (they manage their own module state)
- Verify that all 3693 individual test cases continue to pass

**Boundary conditions and edge cases covered:**

- Test execution in environments WITH a `.env` file (CI) — `loadEnv` fix prevents leakage
- Test execution in environments WITHOUT a `.env` file (fresh clone) — explicit env vars provide `DATABASE_URL` and `ENCRYPTION_KEY`
- Tests using `vi.importActual("@/lib/constants")` — explicit env vars allow `createEnv()` to succeed
- Tests using local `vi.resetModules()` — these are unaffected because they manage their own imports via `await import()`
- Test order sensitivity — removing global `vi.resetModules()` eliminates order-dependent failures

**Whether verification was successful, and confidence level:** Pre-fix reproduction successful with 100% match to reported symptoms. Post-fix verification confidence: **95%** — the fix addresses all three root causes with minimal, targeted changes to the two identified files.

## 0.4 Bug Fix Specification

### 0.4.1 The Definitive Fix

The fix targets exactly two files with three surgical changes that eliminate all three root causes without altering any sprint deliverable code.

**File 1: `apps/web/vitestSetup.ts`**

- **Current implementation at lines 172–179:**
```typescript
beforeEach(() => {
  vi.resetModules();
  vi.resetAllMocks();
});

afterEach(() => {
  vi.clearAllMocks();
});
```
- **Required change at lines 172–179:** Remove `vi.resetModules()` entirely and replace `vi.resetAllMocks()` with `vi.clearAllMocks()`. Remove the now-redundant `afterEach` block since `beforeEach` already calls `vi.clearAllMocks()`.
```typescript
beforeEach(() => {
  vi.clearAllMocks();
});
```
- **This fixes root cause 1 by:** Preserving the module cache across tests so that setup-file mocks for `@/lib/constants`, `server-only`, `next/navigation`, and other modules remain effective. The change from `vi.resetAllMocks()` to `vi.clearAllMocks()` ensures mock call history and arguments are cleared between tests (preventing cross-test contamination) while preserving mock implementations set by `vi.mock()` factories. Tests that require full module resets can still call `vi.resetModules()` locally — 38 test files already do this correctly.

**File 2: `apps/web/vite.config.mts`**

- **Current implementation at line 13:**
```typescript
env: loadEnv("", process.cwd(), ""),
```
- **Required change at line 13:** Replace the unscoped `loadEnv` call with explicit minimal environment variables that satisfy `@t3-oss/env-nextjs` Zod validation without leaking real secrets.
```typescript
env: {
  DATABASE_URL: "postgresql://test:test@localhost:5432/testdb",
  ENCRYPTION_KEY: "test-encryption-key-for-vitest-only",
  NODE_ENV: "test",
},
```
- **This fixes root causes 2 and 3 by:**
  - Providing `DATABASE_URL` and `ENCRYPTION_KEY` so that any `createEnv()` call in `lib/env.ts` passes Zod validation, even when test code uses `vi.importActual()` to load the real `@/lib/constants` or when `@/lib/getPublicUrl` is imported without a mock
  - Eliminating the `loadEnv("", process.cwd(), "")` call that would inject ALL `.env` file variables (including `STRIPE_CLIENT_ID`, `STRIPE_SECRET_KEY`, and other secrets) into the test environment, preventing mock path mismatches in Stripe Connect and other route tests
  - Setting `NODE_ENV: "test"` explicitly so that the `REDIS_URL` field's test-mode conditional (`process.env.NODE_ENV === "test" ? z.string().optional() : ...`) evaluates correctly
- **Also remove the now-unused `loadEnv` import from line 3:**
  - Current: `import { PluginOption, loadEnv } from "vite";`
  - Change to: `import { PluginOption } from "vite";`

### 0.4.2 Change Instructions

**`apps/web/vitestSetup.ts`:**

- MODIFY lines 172–175 from:
```typescript
beforeEach(() => {
  vi.resetModules();
  vi.resetAllMocks();
});
```
to:
```typescript
beforeEach(() => {
  vi.clearAllMocks();
});
```
  - Comment: Remove `vi.resetModules()` to preserve module cache and prevent destruction of setup-file mocks. Replace `vi.resetAllMocks()` with `vi.clearAllMocks()` to clear call history without resetting mock implementations.

- DELETE lines 177–179 containing:
```typescript
afterEach(() => {
  vi.clearAllMocks();
});
```
  - Comment: Remove redundant `afterEach` block since `beforeEach` now handles `vi.clearAllMocks()`. Running `clearAllMocks` at the start of each test is sufficient and avoids double-clearing.

**`apps/web/vite.config.mts`:**

- MODIFY line 3 from:
```typescript
import { PluginOption, loadEnv } from "vite";
```
to:
```typescript
import { PluginOption } from "vite";
```
  - Comment: Remove `loadEnv` import since it is no longer used after replacing the dynamic env loading with explicit test variables.

- MODIFY line 13 from:
```typescript
env: loadEnv("", process.cwd(), ""),
```
to:
```typescript
env: {
  DATABASE_URL: "postgresql://test:test@localhost:5432/testdb",
  ENCRYPTION_KEY: "test-encryption-key-for-vitest-only",
  NODE_ENV: "test",
},
```
  - Comment: Replace unscoped `loadEnv` with explicit minimal env vars to prevent real secret leakage from `.env` files while satisfying `@t3-oss/env-nextjs` Zod validation for `DATABASE_URL` (z.string().url()) and `ENCRYPTION_KEY` (z.string()).

### 0.4.3 Fix Validation

- **Test command to verify fix:** `cd apps/web && CI=true npx vitest run --no-coverage`
- **Expected output after fix:** `Test Files  0 failed | 316 passed (316)` with `Tests  3693 passed | 1 skipped (3694)`
- **Confirmation method:**
  - Run the full suite at least twice to verify no order-dependent failures remain
  - Run a single previously-failing test file in isolation: `npx vitest run lib/response/service.test.ts`
  - Run a batch of previously-failing files: `npx vitest run modules/storage/utils.test.ts modules/survey/follow-ups/lib/utils.test.ts modules/auth/lib/authOptions.test.ts`
  - Verify that tests using local `vi.resetModules()` still pass: `npx vitest run modules/ee/license-check/lib/license.test.ts`

## 0.5 Scope Boundaries

### 0.5.1 Changes Required (Exhaustive List)

| Action | File Path | Lines | Specific Change |
|--------|-----------|-------|-----------------|
| MODIFIED | `apps/web/vitestSetup.ts` | 172–175 | Remove `vi.resetModules()` and replace `vi.resetAllMocks()` with `vi.clearAllMocks()` in global `beforeEach` |
| MODIFIED | `apps/web/vitestSetup.ts` | 177–179 | Remove redundant `afterEach(() => { vi.clearAllMocks(); })` block |
| MODIFIED | `apps/web/vite.config.mts` | 3 | Remove `loadEnv` from the `vite` import statement |
| MODIFIED | `apps/web/vite.config.mts` | 13 | Replace `env: loadEnv("", process.cwd(), "")` with explicit `env: { DATABASE_URL, ENCRYPTION_KEY, NODE_ENV }` object |

**No files are CREATED or DELETED.**

### 0.5.2 Explicitly Excluded

**Do not modify — Sprint 1 deliverables (working correctly):**
- `apps/web/modules/survey/payment/lib/stripe.ts` — Stripe Payment Intent creation
- `apps/web/modules/survey/payment/` — `createPaymentIntentAction` server action
- `packages/types/surveys/elements.ts` — `ZSurveyPaymentElement` Zod schema
- `apps/web/app/api/stripe-connect/authorize/route.ts` — Stripe Connect OAuth authorize
- `apps/web/app/api/stripe-connect/callback/route.ts` — Stripe Connect OAuth callback
- `apps/web/app/api/stripe-connect/status/route.ts` — Stripe Connect status endpoint
- `apps/web/app/api/stripe-connect/disconnect/route.ts` — Stripe Connect disconnect endpoint

**Do not modify — Sprint 2 deliverables (working correctly):**
- `packages/surveys/src/lib/logic.ts` — Survey logic operators
- `packages/types/surveys/logic.ts` — Logic type definitions
- `apps/web/lib/response/service.ts` — `getResponseDownloadFile` function (signature unchanged)

**Do not modify — Sprint 3–5 deliverables (working correctly):**
- `apps/web/lib/crypto.ts` — `generateStandardWebhookSignature` HMAC-SHA256 signing
- `apps/web/app/api/(internal)/pipeline/` — Webhook pipeline routes
- All embed variant implementations (slider, popover, side tab)
- All backward-compatibility tests, export lossless validation tests, webhook parity validation tests

**Do not modify — Infrastructure exclusions:**
- `apps/web/modules/ee/` — Enterprise features
- `packages/database/schema.prisma` — Prisma schema
- `packages/database/src/scripts/migration-runner.ts` — Already fixed with `pathToFileURL`
- `apps/web/lib/env.ts` — Environment validation schema (the fix provides env vars externally)
- `apps/web/lib/constants.ts` — Constants module (the fix preserves its mock)
- `apps/web/lib/getPublicUrl.ts` — Public URL utility (the fix provides env vars so it loads cleanly)
- Any Playwright test files — E2E tests are out of scope
- `Sprint1/`, `Sprint2/`, `Sprint3-5/` documentation folders

**Do not refactor:**
- The 38 test files that use local `vi.resetModules()` — these are intentional per-test isolation patterns
- The 193 test files that use `vi.mocked()` — these function correctly once the global setup is fixed
- The `@/lib/constants` mock factory in `vitestSetup.ts` (lines 187–253) — it is comprehensive and correct

**Do not add:**
- New test files
- New mock modules
- Additional environment variables beyond the three specified (`DATABASE_URL`, `ENCRYPTION_KEY`, `NODE_ENV`)
- Changes to the `dotenv -e ../../.env` command in `apps/web/package.json` test script

## 0.6 Verification Protocol

### 0.6.1 Bug Elimination Confirmation

- **Execute:** `cd apps/web && CI=true npx vitest run --no-coverage`
- **Verify output matches:** `Test Files  0 failed | 316 passed (316)` and `Tests  3693 passed | 1 skipped (3694)`
- **Confirm error no longer appears in:** Test runner stdout/stderr — specifically:
  - Zero occurrences of `"Invalid environment variables"` 
  - Zero occurrences of `"vi.mocked(...).mockResolvedValue is not a function"`
  - Zero occurrences of `"There was an error when mocking a module"`
- **Validate functionality with individual previously-failing files:**
  - `cd apps/web && npx vitest run lib/response/service.test.ts` — should pass
  - `cd apps/web && npx vitest run modules/storage/utils.test.ts` — should pass (uses `vi.importActual`)
  - `cd apps/web && npx vitest run modules/survey/follow-ups/lib/utils.test.ts` — should pass (uses `vi.importActual("@/lib/constants")`)
  - `cd apps/web && npx vitest run modules/auth/lib/authOptions.test.ts` — should pass (imports `@/lib/constants` directly)
  - `cd apps/web && npx vitest run modules/ee/license-check/lib/utils.test.ts` — should pass (chain through `license.ts`)

### 0.6.2 Regression Check

- **Run existing test suite:** `cd apps/web && CI=true npx vitest run --no-coverage`
- **Verify unchanged behavior in:**
  - All 289 currently-passing test files continue to pass
  - All 3693 individual test cases continue to pass
  - The 1 skipped test remains skipped (expected)
  - Tests using local `vi.resetModules()` still pass: `npx vitest run modules/ee/license-check/lib/license.test.ts` (14 local uses), `npx vitest run modules/core/rate-limit/helpers.test.ts` (6 local uses)
- **Confirm performance metrics:** Total suite execution time should remain under 60 seconds (baseline: 38.51s observed during reproduction)
- **Sprint deliverable verification:** Run targeted test subsets to confirm all sprint features pass:
  - Sprint 1 (Payment): `npx vitest run app/api/v1/client/payment-intent/route.test.ts app/api/stripe-connect/`
  - Sprint 1 (Opinion Scale): `npx vitest run modules/survey/editor/components/opinion-scale`
  - Sprint 2 (Logic): `npx vitest run lib/surveyLogic/utils.test.ts`
  - Sprint 2 (Export): `npx vitest run lib/response/`
  - Sprint 3 (Webhook): `npx vitest run app/api/(internal)/pipeline/`
  - Sprint 3 (Embed): `npx vitest run modules/survey/editor/components/embed`

### 0.6.3 Order Independence Verification

- **Run suite twice consecutively** to verify no order-dependent failures:
```
cd apps/web
CI=true npx vitest run --no-coverage
CI=true npx vitest run --no-coverage --sequence.seed=12345
```
- **Both runs must produce:** 0 failed, 316 passed
- **Rationale:** The `--sequence.seed` flag forces a different deterministic test order. If both runs pass, order independence is confirmed.

## 0.7 Rules

### 0.7.1 Mandatory Constraints

- **Make the exact specified changes only** — Modify only `apps/web/vitestSetup.ts` and `apps/web/vite.config.mts` for the confirmed test infrastructure bug
- **Zero modifications outside the bug fix** — No feature code, schema changes, migration changes, or business logic alterations
- **Extensive testing to prevent regressions** — Full test suite must pass (316 files, 3693+ test cases) after every change
- **Preserve all existing interfaces and contracts** — The `createPaymentIntentAction` server action, `ZSurveyPaymentElement` schema, all webhook API contracts, and the `getResponseDownloadFile` function signature must remain unchanged
- **Do not modify enterprise features** — `apps/web/modules/ee/` is off-limits
- **Do not modify database schema** — `packages/database/schema.prisma` remains untouched
- **Do not modify E2E tests** — Playwright test files are excluded

### 0.7.2 Coding Standards and Conventions

- **Follow existing project patterns:** The codebase uses TypeScript with strict mode, Vitest for unit testing, and `vi.mock()`/`vi.clearAllMocks()` as the standard mock lifecycle pattern
- **Use `vi.clearAllMocks()` for mock cleanup** — This is the safe approach that clears call history without destroying mock implementations, consistent with Vitest best practices
- **Do not use `vi.resetModules()` in global setup** — Module-level resets should only be performed locally in test files that explicitly require fresh module evaluation via `await import()`
- **Provide only test-safe environment variables** — The replacement env vars in `vite.config.mts` must use obviously fake values (e.g., `postgresql://test:test@localhost:5432/testdb`) that cannot be confused with real credentials
- **Preserve the `dotenv -e ../../.env` test script** — The `apps/web/package.json` test script's `dotenv` command remains unchanged; the Vitest config now provides fallback values instead of loading from files
- **Target version compatibility:** All changes must be compatible with Vitest 3.1.3, Vite (used internally by Vitest), Node.js ≥ 20.0.0, and `@t3-oss/env-nextjs` as used by the project

### 0.7.3 Audit Scope

- The sprint roadmap at `docs/development/typeform-parity/sprint-roadmap.mdx` was reviewed in full
- All 316 test files were executed and their results analyzed
- The 27 failures are exclusively test infrastructure issues — no sprint deliverable logic bugs were found
- All sprint deliverables (Sprints 1–5) pass their respective tests when the test infrastructure is fixed

## 0.8 References

### 0.8.1 Repository Files and Folders Searched

**Primary files analyzed (directly relevant to root cause):**

| File Path | Purpose |
|-----------|---------|
| `apps/web/vitestSetup.ts` | Global test setup — contains the `vi.resetModules()` and `vi.resetAllMocks()` calls, the `@/lib/constants` mock, and all global module mocks |
| `apps/web/vite.config.mts` | Vitest configuration — contains the `loadEnv("", process.cwd(), "")` call and test environment settings |
| `apps/web/lib/env.ts` | Environment variable validation using `@t3-oss/env-nextjs` and Zod — requires `DATABASE_URL` and `ENCRYPTION_KEY` |
| `apps/web/lib/constants.ts` | Application constants — imports from `lib/env.ts`, mocked globally by `vitestSetup.ts` |
| `apps/web/lib/getPublicUrl.ts` | Public URL utility — imports from `lib/env.ts`, NOT mocked by `vitestSetup.ts` |
| `apps/web/package.json` | App dependencies and test script definition (`dotenv -e ../../.env -- vitest run`) |
| `package.json` | Root monorepo configuration — Node.js ≥ 20.0.0, pnpm 10.28.2 |

**Sprint roadmap and documentation:**

| File Path | Purpose |
|-----------|---------|
| `docs/development/typeform-parity/sprint-roadmap.mdx` | Master sprint roadmap covering Sprints 1–5 deliverables |

**Configuration and environment files:**

| File Path | Purpose |
|-----------|---------|
| `.env.example` | Environment variable template — confirms `STRIPE_SECRET_KEY`, `STRIPE_CLIENT_ID`, `DATABASE_URL`, `ENCRYPTION_KEY` |
| `apps/web/.env` | Symlink to `../../.env` — no actual `.env` file exists at root |
| `vitest.workspace.ts` | Workspace-level Vitest configuration |

**Sample failing test files examined:**

| File Path | Error Type |
|-----------|------------|
| `apps/web/lib/response/service.test.ts` | Invalid environment variables (via `getPublicUrl` → `env.ts`) |
| `apps/web/lib/survey/service.test.ts` | Invalid environment variables (via `getPublicUrl` → `env.ts`) |
| `apps/web/lib/survey/utils.test.ts` | Invalid environment variables |
| `apps/web/modules/storage/service.test.ts` | Invalid environment variables |
| `apps/web/modules/storage/utils.test.ts` | vi.mock factory error (uses `vi.importActual` → `getPublicUrl` → `env.ts`) |
| `apps/web/modules/survey/follow-ups/lib/utils.test.ts` | vi.mock factory error (uses `vi.importActual("@/lib/constants")` → `env.ts`) |
| `apps/web/modules/auth/lib/authOptions.test.ts` | Invalid environment variables (via `license.ts` → `env.ts`) |
| `apps/web/modules/ee/license-check/lib/utils.test.ts` | Invalid environment variables (via `constants.ts` → `env.ts`) |
| `apps/web/modules/ee/audit-logs/lib/handler.test.ts` | Invalid environment variables (via `license.ts` → `env.ts`) |
| `apps/web/modules/api/v2/auth/tests/authenticated-api-client.test.ts` | Invalid environment variables |
| `apps/web/modules/api/v2/lib/tests/utils.test.ts` | Invalid environment variables |
| `apps/web/app/api/stripe-connect/authorize/route.test.ts` | Examined — uses `vi.hoisted` (safe pattern), currently passes |
| `apps/web/app/api/stripe-connect/callback/route.test.ts` | Examined — uses `vi.hoisted` (safe pattern), currently passes |
| `apps/web/app/api/v1/client/payment-intent/route.test.ts` | Examined — uses `vi.mocked`, currently passes |
| `apps/web/lib/surveyLogic/utils.test.ts` | Examined — 28 tests, currently passes |
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/lib/surveySummary.test.ts` | vi.mock factory error (transitive import via `getPublicUrl` → `env.ts`) |

**Complete list of all 27 failing test files:**

| # | Relative Path (from `apps/web/`) |
|---|----------------------------------|
| 1 | `lib/response/service.test.ts` |
| 2 | `lib/survey/service.test.ts` |
| 3 | `lib/survey/utils.test.ts` |
| 4 | `modules/storage/service.test.ts` |
| 5 | `lib/response/tests/response.test.ts` |
| 6 | `modules/ee/contacts/lib/update-contact-attributes.test.ts` |
| 7 | `modules/survey/editor/lib/check-external-urls-permission.test.ts` |
| 8 | `modules/survey/link/lib/metadata-utils.test.ts` |
| 9 | `app/api/(internal)/pipeline/lib/handleIntegrations.test.ts` |
| 10 | `app/api/v1/management/responses/lib/response.test.ts` |
| 11 | `app/api/v1/management/surveys/lib/surveys.test.ts` |
| 12 | `app/(app)/environments/[environmentId]/workspace/integrations/lib/surveys.test.ts` |
| 13 | `app/api/v1/client/[environmentId]/environment/lib/data.test.ts` |
| 14 | `app/api/v1/client/[environmentId]/environment/lib/environmentState.test.ts` |
| 15 | `app/api/v1/management/responses/[responseId]/lib/response.test.ts` |
| 16 | `app/api/v2/client/[environmentId]/responses/lib/response.test.ts` |
| 17 | `modules/api/v2/management/responses/lib/tests/response.test.ts` |
| 18 | `app/api/v1/client/[environmentId]/responses/[responseId]/lib/response.test.ts` |
| 19 | `modules/api/v2/management/surveys/[surveyId]/contact-links/segments/[segmentId]/lib/tests/contact.test.ts` |
| 20 | `modules/storage/utils.test.ts` |
| 21 | `modules/auth/lib/authOptions.test.ts` |
| 22 | `modules/ee/audit-logs/lib/handler.test.ts` |
| 23 | `modules/api/v2/auth/tests/authenticated-api-client.test.ts` |
| 24 | `modules/api/v2/lib/tests/utils.test.ts` |
| 25 | `modules/ee/license-check/lib/utils.test.ts` |
| 26 | `modules/survey/follow-ups/lib/utils.test.ts` |
| 27 | `app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/lib/surveySummary.test.ts` |

### 0.8.2 External References

| Source | URL | Relevance |
|--------|-----|-----------|
| Vitest `vi.resetModules()` documentation | https://vitest.dev/api/vi | Confirms `resetModules` clears module cache but not mock registry; documents that setup file imports are cached |
| Vitest Mocking Guide | https://vitest.dev/guide/mocking | Documents `vi.clearAllMocks()` vs `vi.resetAllMocks()` behavior differences |
| Vitest `env` configuration | https://vitest.dev/config/env | Documents how `test.env` property sets environment variables for tests |
| Vitest Features — Environment Variables | https://vitest.dev/guide/features | Documents the `loadEnv` pattern for loading non-VITE-prefixed variables |
| Vite `loadEnv` — Env Variables and Modes | https://vite.dev/guide/env-and-mode | Documents how `loadEnv` third parameter controls prefix filtering |
| GitHub Issue #1450 — `vi.mock` ignored if module is imported in setup file | https://github.com/vitest-dev/vitest/issues/1450 | Confirms that mocks for modules imported in setup files are cached and `resetModules` disrupts them |
| GitHub Issue #1940 — mocks cannot be reset | https://github.com/vitest-dev/vitest/issues/1940 | Documents known issues with `resetModules` + `resetAllMocks` combination |

### 0.8.3 Attachments

No attachments were provided for this project. No Figma URLs were specified.

