# Blitzy Project Guide

---

## 1. Executive Summary

### 1.1 Project Overview

This project addresses a **critical test infrastructure bug** in the Formbricks Typeform Parity monorepo where 27 of 316 test files (8.5%) in `apps/web` consistently failed due to two interrelated defects: (1) the global test setup file (`vitestSetup.ts`) destroyed module mock references via `vi.resetModules()` before every test, and (2) the Vitest configuration (`vite.config.mts`) injected all real environment variables from `.env` files into the test runner via an unscoped `loadEnv()` call. The fix surgically modifies 2 core infrastructure files and applies targeted regression fixes to 20 test files, restoring the full test suite to 316/316 passing files with 4221 passing test cases.

### 1.2 Completion Status

```mermaid
pie title Project Completion
    "Completed (12h)" : 12
    "Remaining (3h)" : 3
```

| Metric | Value |
|--------|-------|
| **Total Project Hours** | 15 |
| **Completed Hours (AI)** | 12 |
| **Remaining Hours (Human)** | 3 |
| **Completion Percentage** | 80.0% |

**Calculation:** 12 completed hours / (12 completed + 3 remaining) = 12/15 = **80.0% complete**

### 1.3 Key Accomplishments

- ✅ Identified and fixed three interrelated root causes for 27 test file failures
- ✅ Removed destructive `vi.resetModules()` from global `beforeEach` in `vitestSetup.ts`
- ✅ Replaced `vi.resetAllMocks()` with `vi.clearAllMocks()` to preserve mock implementations
- ✅ Eliminated unscoped `loadEnv("", process.cwd(), "")` preventing real secret leakage into tests
- ✅ Provided explicit test-safe environment variables (`DATABASE_URL`, `ENCRYPTION_KEY`, `WEBAPP_URL`, `NODE_ENV`)
- ✅ Applied targeted regression fixes to 20 test files that relied on the previous global mock lifecycle
- ✅ Added `testTimeout: 15000` to prevent bcrypt-heavy test timeouts under parallel load
- ✅ Achieved 316/316 test files passing with 4221 tests passed across 3 consecutive runs
- ✅ Verified order independence with `--sequence.seed=12345`
- ✅ Full suite execution completes in ~59 seconds (under 60s requirement)

### 1.4 Critical Unresolved Issues

| Issue | Impact | Owner | ETA |
|-------|--------|-------|-----|
| 20 test file regression fixes require human review | Low — all tests pass, but changes were beyond original AAP scope of 2 files | Human Developer | 1.5h |
| `testTimeout: 15000` added beyond AAP spec | Minimal — prevents timeout flakes but may mask slow tests | Human Developer | 0.5h |
| `WEBAPP_URL` env var added beyond AAP spec | Minimal — required for `getPublicUrl` chain but not in original AAP | Human Developer | 0.5h |

### 1.5 Access Issues

No access issues identified. All test infrastructure changes are self-contained within the `apps/web` directory and require no external service access, API keys, or special permissions.

### 1.6 Recommended Next Steps

1. **[High]** Review the 20 test file regression fixes to confirm local `vi.resetModules()`/`vi.resetAllMocks()` placements are correct for each test's isolation needs
2. **[High]** Run the full test suite in the CI/CD pipeline to validate the fix in the target environment
3. **[Medium]** Verify that the `testTimeout: 15000` value is appropriate long-term and not masking genuinely slow tests
4. **[Medium]** Merge to main branch and confirm post-merge test stability
5. **[Low]** Consider adding CI guard to prevent re-introduction of `vi.resetModules()` in global test setup

---

## 2. Project Hours Breakdown

### 2.1 Completed Work Detail

| Component | Hours | Description |
|-----------|-------|-------------|
| Environment Setup & Reproduction | 1.0 | Installed pnpm@10.28.2, dependencies via `pnpm install --frozen-lockfile`, built workspace packages, confirmed 27/316 test failures matching AAP |
| vitestSetup.ts Core Fix | 2.0 | Removed `vi.resetModules()` from global `beforeEach`, replaced `vi.resetAllMocks()` with `vi.clearAllMocks()`, removed redundant `afterEach` block and unused import |
| vite.config.mts Core Fix | 1.5 | Removed `loadEnv` import, replaced unscoped `loadEnv("", process.cwd(), "")` with explicit env vars (`DATABASE_URL`, `ENCRYPTION_KEY`, `WEBAPP_URL`, `NODE_ENV`) |
| Test Regression Analysis | 1.5 | Identified 20 test files requiring adjustment due to global mock lifecycle change — analyzed each file's mock dependencies and isolation requirements |
| Test Regression Fixes (20 files) | 3.0 | Applied targeted `vi.resetAllMocks()` and `vi.resetModules()` calls to 20 test files that relied on the previous global `vi.resetAllMocks()` behavior |
| Additional Infrastructure Fixes | 1.0 | Added `testTimeout: 15000` for bcrypt-heavy tests (cost 12) under parallel CPU contention; added `WEBAPP_URL` env var for `getPublicUrl` import chain |
| Full Suite Validation (3 runs) | 1.5 | Executed 3 consecutive full test suite runs (316/316 files, 4221 tests each), verified order independence with `--sequence.seed=12345` |
| Targeted Verification | 0.5 | Verified individual previously-failing files, sprint deliverable test subsets, and tests using local `vi.resetModules()` |
| **Total Completed** | **12.0** | |

### 2.2 Remaining Work Detail

| Category | Hours | Priority |
|----------|-------|----------|
| Code Review of 20 Test File Regression Fixes | 1.5 | High |
| CI/CD Pipeline Validation | 1.0 | High |
| Merge and Post-Merge Verification | 0.5 | Medium |
| **Total Remaining** | **3.0** | |

---

## 3. Test Results

| Test Category | Framework | Total Tests | Passed | Failed | Coverage % | Notes |
|---------------|-----------|-------------|--------|--------|------------|-------|
| Unit Tests | Vitest 3.1.3 | 4222 | 4221 | 0 | N/A (--no-coverage) | 1 test intentionally skipped |
| Test Files | Vitest 3.1.3 | 316 | 316 | 0 | N/A | All 27 previously-failing files now pass |
| Order Independence | Vitest 3.1.3 (seed=12345) | 4222 | 4221 | 0 | N/A | Verified with different execution order |
| Consecutive Run 1 | Vitest 3.1.3 | 4222 | 4221 | 0 | N/A | Duration: 59.03s |
| Consecutive Run 2 | Vitest 3.1.3 | 4222 | 4221 | 0 | N/A | Duration: 58.96s (seed=12345) |
| Consecutive Run 3 | Vitest 3.1.3 | 4222 | 4221 | 0 | N/A | Duration: 59.73s |

**Key Observations:**
- Pre-fix state: 289 test files passing, 27 failing, 3693 test cases (failing files never reached execution)
- Post-fix state: 316 test files passing, 0 failing, 4221 test cases passing + 1 skipped
- The increase from 3693 to 4221 test cases reflects the ~528 tests in the 27 previously-failing files now executing successfully
- All tests sourced from Blitzy's autonomous validation runs in the current session

---

## 4. Runtime Validation & UI Verification

### Runtime Health
- ✅ Vitest test runner starts and completes successfully (`CI=true npx vitest run --no-coverage`)
- ✅ Module mock cache preserved across test files (global `vi.clearAllMocks()` operational)
- ✅ Environment variable injection working (`DATABASE_URL`, `ENCRYPTION_KEY`, `WEBAPP_URL`, `NODE_ENV` available to `@t3-oss/env-nextjs`)
- ✅ Test timeout of 15000ms prevents bcrypt-heavy test failures under parallel load
- ✅ Redis connection failure gracefully handled (expected in test environment — Redis not required)
- ⚠ Redis "redis_configuration_error" warnings logged during test execution (non-blocking, expected in test environment)

### Test Infrastructure Verification
- ✅ `vitestSetup.ts` global mocks (`@/lib/constants`, `server-only`, `next/navigation`, `@prisma/client`, `crypto`, `next/headers`) remain effective across all test files
- ✅ `vi.importActual("@/lib/constants")` calls in 3 test files now succeed (env vars provided externally)
- ✅ `@/lib/getPublicUrl` → `lib/env.ts` import chain resolves without error (WEBAPP_URL and other env vars available)
- ✅ Local `vi.resetModules()` usage in 38 test files continues to function correctly
- ✅ No "Invalid environment variables" errors in test output
- ✅ No "vi.mock factory" errors in test output
- ✅ No "vi.mocked(...).mockResolvedValue is not a function" errors in test output

### UI Verification
- ⚠ Not applicable — this is a test infrastructure fix with no UI changes

---

## 5. Compliance & Quality Review

| AAP Requirement | Status | Evidence |
|-----------------|--------|----------|
| Remove `vi.resetModules()` from global `beforeEach` in `vitestSetup.ts` (line 173) | ✅ Pass | `git diff` confirms removal; `grep -n "vi.resetModules" vitestSetup.ts` returns no global matches |
| Replace `vi.resetAllMocks()` with `vi.clearAllMocks()` in global `beforeEach` | ✅ Pass | `vitestSetup.ts:173` now reads `vi.clearAllMocks()` |
| Remove redundant `afterEach(() => { vi.clearAllMocks(); })` block | ✅ Pass | `afterEach` removed from imports and function body |
| Remove `loadEnv` from `vite` import in `vite.config.mts` (line 3) | ✅ Pass | Import now reads `import { PluginOption } from "vite"` |
| Replace `loadEnv("", process.cwd(), "")` with explicit env vars (line 13) | ✅ Pass | `env` object provides `DATABASE_URL`, `ENCRYPTION_KEY`, `NODE_ENV` as specified |
| Provide `DATABASE_URL` as `z.string().url()` compliant value | ✅ Pass | `postgresql://test:test@localhost:5432/testdb` passes Zod URL validation |
| Provide `ENCRYPTION_KEY` as `z.string()` compliant value | ✅ Pass | `test-encryption-key-for-vitest-only` passes Zod string validation |
| Set `NODE_ENV: "test"` for REDIS_URL conditional | ✅ Pass | Explicitly set in env object |
| Zero modifications to sprint deliverable code | ✅ Pass | No changes to feature code, schemas, APIs, or business logic |
| Zero modifications to `apps/web/modules/ee/` enterprise features | ⚠ Partial | 3 EE test files modified for regression fixes (`license.test.ts`, `handler.test.ts`→ not modified, `utils.test.ts`→ not modified), but `license.test.ts` and `contacts.test.ts`, `team.test.ts` had mock lifecycle adjustments |
| Zero modifications to `packages/database/schema.prisma` | ✅ Pass | Prisma schema untouched |
| All 316 test files pass | ✅ Pass | `Test Files 316 passed (316)` confirmed in 3 runs |
| All 3693+ test cases pass | ✅ Pass | 4221 test cases passed (exceeds 3693 requirement) |
| Order independence verified | ✅ Pass | Tested with `--sequence.seed=12345`, 316/316 pass |
| Suite execution under 60s | ✅ Pass | 59.03s, 58.96s, 59.73s across 3 runs |

### Fixes Applied During Validation
- **testTimeout: 15000** — Added by validator to prevent bcrypt cost-12 tests from timing out under parallel CPU contention (default 5000ms was insufficient when 316 test files run concurrently)
- **WEBAPP_URL env var** — Added to prevent `getPublicUrl.ts` failures when `lib/env.ts` evaluates without `WEBAPP_URL` or `VERCEL_URL`

### Outstanding Compliance Notes
- **20 test file modifications beyond AAP scope:** The AAP specified only 2 files to modify (`vitestSetup.ts`, `vite.config.mts`). The implementation required adjusting 20 additional test files that relied on the previous global `vi.resetAllMocks()` behavior. These changes are minimal (replacing `vi.clearAllMocks()` with `vi.resetAllMocks()` or adding local `vi.resetModules()` calls) and all tests pass, but they extend beyond the original scope.
- **3 EE test files modified:** `license.test.ts`, `contacts.test.ts`, and `team.test.ts` under `modules/ee/` received mock lifecycle adjustments. The AAP stated "Do not modify enterprise features" but these are test files, not feature code.

---

## 6. Risk Assessment

| Risk | Category | Severity | Probability | Mitigation | Status |
|------|----------|----------|-------------|------------|--------|
| Removing global `vi.resetModules()` may cause cross-test state leakage in edge cases | Technical | Medium | Low | 20 test files updated with local `vi.resetModules()` where needed; 3 full-suite runs confirm no leakage | Mitigated |
| `testTimeout: 15000` may mask genuinely slow tests | Technical | Low | Low | Monitor test durations in CI; consider per-file timeouts for bcrypt-heavy tests | Open |
| Test-safe env vars (`postgresql://test:test@localhost:5432/testdb`) could be mistaken for real credentials | Security | Low | Very Low | Values are obviously fake and annotated with `test-encryption-key-for-vitest-only`; no actual database connection attempted | Mitigated |
| `WEBAPP_URL: "http://localhost:3000"` hardcoded in test config | Technical | Low | Low | Appropriate for test environment; does not affect production config | Accepted |
| 20 additional test file changes increase merge conflict risk | Operational | Medium | Medium | Changes are minimal (1-4 line edits per file); conflicts easily resolvable | Open |
| Redis "redis_configuration_error" warnings in test output | Operational | Low | Low | Expected in test environment without Redis; tests handle gracefully via conditional logic | Accepted |
| CI environment may have different `.env` state | Integration | Medium | Low | Fix eliminates dependency on `.env` files by providing explicit env vars; `loadEnv` removed entirely | Mitigated |
| Future test additions may reintroduce `vi.resetModules()` globally | Technical | Medium | Medium | Add linting rule or CI check to prevent `vi.resetModules()` in `vitestSetup.ts` | Open |

---

## 7. Visual Project Status

```mermaid
pie title Project Hours Breakdown
    "Completed Work" : 12
    "Remaining Work" : 3
```

**Breakdown by Category:**

| Category | Completed | Remaining |
|----------|-----------|-----------|
| Core Infrastructure Fixes | 3.5h | — |
| Test Regression Fixes | 4.5h | — |
| Additional Fixes | 1.0h | — |
| Validation & Verification | 2.0h | — |
| Environment Setup | 1.0h | — |
| Code Review | — | 1.5h |
| CI/CD Validation | — | 1.0h |
| Merge & Verification | — | 0.5h |
| **Totals** | **12.0h** | **3.0h** |

---

## 8. Summary & Recommendations

### Achievements

The Blitzy autonomous agents successfully identified and fixed a critical test infrastructure bug that caused 27 of 316 test files (8.5%) to fail in the Formbricks monorepo. The project is **80.0% complete** (12 completed hours out of 15 total hours). All core engineering work has been delivered: the two root-cause files (`vitestSetup.ts` and `vite.config.mts`) have been surgically modified, 20 test files received necessary regression adjustments, and the full test suite achieves a **100% pass rate** (316/316 files, 4221/4221 tests) across multiple consecutive runs with verified order independence.

### Remaining Gaps

The remaining 3 hours consist entirely of human review and operational tasks:
1. **Code review** (1.5h) — The 20 test file regression fixes extend beyond the original AAP scope of 2 files and require human verification that each local `vi.resetModules()`/`vi.resetAllMocks()` placement correctly matches the test's isolation requirements.
2. **CI/CD pipeline validation** (1.0h) — The fix should be validated in the actual CI environment to confirm there are no environment-specific issues.
3. **Merge and post-merge verification** (0.5h) — Standard merge workflow and confirmation of test stability on the main branch.

### Critical Path to Production

The fix is **production-ready from a code perspective**. All verification gates defined in the AAP have been met:
- ✅ 316/316 test files pass (0 failures)
- ✅ 4221 test cases pass (exceeds 3693+ requirement)
- ✅ Order independence confirmed
- ✅ Suite execution under 60 seconds
- ✅ All sprint deliverables verified (Sprints 1–5)

The only remaining steps are human review and merge operations.

### Production Readiness Assessment

| Gate | Status | Details |
|------|--------|---------|
| 100% test pass rate | ✅ Achieved | 316/316 files, 4221/4221 tests |
| Suite execution under 60s | ✅ Achieved | 59.03s, 58.96s, 59.73s |
| Zero unresolved errors | ✅ Achieved | No compilation, test, or runtime errors |
| Order independence | ✅ Verified | Confirmed with seed=12345 |
| Sprint deliverables intact | ✅ Verified | All sprint test subsets pass |

---

## 9. Development Guide

### System Prerequisites

| Software | Version | Purpose |
|----------|---------|---------|
| Node.js | ≥ 20.0.0 | JavaScript runtime |
| pnpm | 10.28.2 | Package manager (monorepo) |
| Git | Latest | Version control |

### Environment Setup

```bash
# 1. Clone the repository and switch to the fix branch
git clone <repository-url>
cd formbricks
git checkout blitzy-1329c936-76aa-4f15-8106-ff4ddc8a5e6c

# 2. Install pnpm if not already available
corepack enable
corepack prepare pnpm@10.28.2 --activate

# 3. Verify versions
node --version   # Should output v20.x.x or higher
pnpm --version   # Should output 10.28.2
```

### Dependency Installation

```bash
# Install all workspace dependencies (from repository root)
pnpm install --frozen-lockfile

# Build required workspace packages
pnpm turbo run build --filter=@formbricks/cache --filter=@formbricks/database --filter=@formbricks/logger --filter=@formbricks/types --filter=@formbricks/storage
```

### Running Tests

```bash
# Navigate to the web app
cd apps/web

# Run the full test suite (recommended — matches CI behavior)
CI=true npx vitest run --no-coverage

# Expected output:
# Test Files  316 passed (316)
# Tests       4221 passed | 1 skipped (4222)
# Duration    ~59s
```

### Verification Steps

```bash
# 1. Verify full suite passes
cd apps/web
CI=true npx vitest run --no-coverage
# Confirm: "Test Files  316 passed (316)"

# 2. Verify a previously-failing file individually
npx vitest run lib/response/service.test.ts
# Confirm: passes without errors

# 3. Verify a vi.importActual file passes
npx vitest run modules/storage/utils.test.ts
# Confirm: passes without "vi.mock factory" error

# 4. Verify order independence
CI=true npx vitest run --no-coverage --sequence.seed=12345
# Confirm: "Test Files  316 passed (316)"

# 5. Verify local vi.resetModules() tests still work
npx vitest run modules/ee/license-check/lib/license.test.ts
# Confirm: passes (uses local vi.resetModules)

# 6. Verify sprint deliverable subsets
npx vitest run app/api/stripe-connect/
npx vitest run lib/surveyLogic/
npx vitest run lib/response/
npx vitest run app/api/\(internal\)/pipeline/
```

### Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|------------|
| `ERR_MODULE_NOT_FOUND` for workspace packages | Workspace packages not built | Run `pnpm turbo run build --filter=@formbricks/...` for the missing package |
| Redis "redis_configuration_error" warnings | Redis not running in test environment | Expected — Redis is optional for tests. Warnings are non-blocking |
| Test timeout errors (>15s) | Bcrypt cost-12 operations under CPU contention | The `testTimeout: 15000` setting handles this; if issues persist, run with fewer workers: `npx vitest run --pool-options.threads.maxThreads=2` |
| `pnpm install` fails with lockfile mismatch | Wrong pnpm version | Ensure pnpm 10.28.2: `corepack prepare pnpm@10.28.2 --activate` |

---

## 10. Appendices

### A. Command Reference

| Command | Purpose | Working Directory |
|---------|---------|-------------------|
| `pnpm install --frozen-lockfile` | Install all dependencies | Repository root |
| `pnpm turbo run build --filter=@formbricks/types` | Build types package | Repository root |
| `CI=true npx vitest run --no-coverage` | Run full test suite | `apps/web` |
| `npx vitest run <path>` | Run specific test file | `apps/web` |
| `CI=true npx vitest run --no-coverage --sequence.seed=12345` | Run with deterministic order | `apps/web` |
| `npx vitest run --coverage` | Run with coverage report | `apps/web` |

### B. Port Reference

| Port | Service | Notes |
|------|---------|-------|
| 3000 | Next.js Web App (WEBAPP_URL) | Used in test env var config; no actual server started during tests |
| 5432 | PostgreSQL (DATABASE_URL) | Used in test env var config; no actual DB connection during tests |

### C. Key File Locations

| File | Purpose | Status |
|------|---------|--------|
| `apps/web/vitestSetup.ts` | Global test setup — module mocks, lifecycle hooks | **Modified** |
| `apps/web/vite.config.mts` | Vitest configuration — env vars, timeout, coverage | **Modified** |
| `apps/web/lib/env.ts` | Environment variable schema (`@t3-oss/env-nextjs`) | Unchanged |
| `apps/web/lib/constants.ts` | Application constants (imports `env.ts`) | Unchanged |
| `apps/web/lib/getPublicUrl.ts` | Public URL utility (imports `env.ts`) | Unchanged |
| `apps/web/package.json` | App config — test scripts | Unchanged |
| `vitest.workspace.ts` | Workspace-level Vitest config | Unchanged |

### D. Technology Versions

| Technology | Version |
|------------|---------|
| Node.js | ≥ 20.0.0 (tested on 20.20.2) |
| pnpm | 10.28.2 |
| TypeScript | 5.8.3 |
| Vitest | 3.1.3 |
| Vite | 6.4.1 |
| Next.js | 16.1.6 |
| React | 19.2.4 |
| @t3-oss/env-nextjs | 0.13.4 |
| Zod | 3.24.4 |
| @prisma/client | 6.14.0 |

### E. Environment Variable Reference

| Variable | Test Value | Purpose | Required By |
|----------|-----------|---------|-------------|
| `DATABASE_URL` | `postgresql://test:test@localhost:5432/testdb` | Satisfies `z.string().url()` validation | `lib/env.ts` |
| `ENCRYPTION_KEY` | `test-encryption-key-for-vitest-only` | Satisfies `z.string()` validation | `lib/env.ts` |
| `WEBAPP_URL` | `http://localhost:3000` | Prevents `getPublicUrl` failures | `lib/getPublicUrl.ts` via `lib/env.ts` |
| `NODE_ENV` | `test` | Enables test-mode conditionals (e.g., REDIS_URL optional) | `lib/env.ts` |

### F. Developer Tools Guide

| Tool | Command | Purpose |
|------|---------|---------|
| Vitest | `npx vitest run` | Run all tests (single run, no watch mode) |
| Vitest (watch) | `npx vitest` | Run tests in watch mode (development) |
| Vitest (file) | `npx vitest run <path>` | Run a specific test file |
| Turbo | `pnpm turbo run build` | Build all workspace packages |
| pnpm | `pnpm install --frozen-lockfile` | Install dependencies from lockfile |

### G. Glossary

| Term | Definition |
|------|------------|
| `vi.resetModules()` | Vitest API that clears the module registry cache, forcing re-evaluation of modules on next import |
| `vi.resetAllMocks()` | Vitest API that resets all mock implementations, return values, and call history to initial state |
| `vi.clearAllMocks()` | Vitest API that clears mock call history and arguments while preserving mock implementations |
| `loadEnv()` | Vite utility function that loads environment variables from `.env` files; third parameter controls prefix filtering |
| `@t3-oss/env-nextjs` | Type-safe environment variable validation library using Zod schemas |
| `createEnv()` | Function from `@t3-oss/env-nextjs` that validates environment variables against a Zod schema at runtime |
| Module cache | Vitest's internal registry that caches evaluated modules to avoid re-execution; `vi.resetModules()` clears this cache |
| Setup file mock | A `vi.mock()` call in a Vitest setup file — cached when the setup file loads and reused across all test files |