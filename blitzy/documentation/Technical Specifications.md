# Technical Specification

# 0. Agent Action Plan

## 0.1 Intent Clarification

### 0.1.1 Core Feature Objective

Based on the prompt, the Blitzy platform understands that the new feature requirement is to **complete Sprint 2: Logic & Data** of the Typeform Parity initiative within the Formbricks open-source survey platform. Sprint 2 is defined in the project's sprint roadmap as covering two parallel epics:

- **Epic 2.1 — Logic Operator Parity**: Verify and confirm that every Typeform logic jump condition type has a functionally equivalent operator in the Formbricks conditional logic engine. Extend the logic condition system to fully support `opinionScale` and `payment` element types (introduced in Sprint 1) as left operands. Add comprehensive test coverage for all operators against the new element types.
- **Epic 2.2 — JSON Response Export**: Add JSON as a third export format alongside CSV and XLSX in the response download pipeline. This includes extending the format type in the service layer, creating a JSON conversion function, updating the download UI with a JSON option, exposing the JSON format through the server action layer, and implementing lossless data fidelity validation.

The platform detects the following implicit requirements:

- Sprint 1 (Foundation — new `opinionScale` and `payment` element types) is a prerequisite and must already be complete. Analysis of the codebase confirms that Sprint 1 is fully implemented: both types are present in `TSurveyElementTypeEnum`, Zod schemas are defined, editor and renderer components exist, and validation rules are registered.
- The JSON export must use the existing intermediate `getResponsesJson` flat tabular data structure to maintain consistency with CSV and XLSX output.
- The lossless export constraint requires that every response field present in the database appears in the JSON export without truncation, rounding, or encoding loss.
- The 100% logic jump coverage constraint requires systematic verification that all 20 Typeform operators map to the 32 existing Formbricks operators.
- Existing Formbricks forms must not be broken by any changes.

### 0.1.2 Special Instructions and Constraints

- **AAP Constraint — 100% Logic Jump Coverage**: Logic jump feature equivalence must be 100%. Every Typeform logic condition type must have a confirmed Formbricks equivalent. The exhaustive operator-to-operator mapping in `docs/development/typeform-parity/logic-parity.mdx` serves as the authoritative verification.
- **AAP Constraint — Lossless Export**: Response export must be lossless. The JSON export must preserve every response field without truncation, rounding, or encoding loss. Seven data fidelity metrics and verification procedures are defined in `docs/development/typeform-parity/export-parity.mdx`.
- **AAP Constraint — No Broken Existing Forms**: All changes must be additive. Existing surveys must continue to parse, render, and export correctly.
- **Architectural Requirement**: Follow the existing monorepo patterns — pnpm workspace, Turborepo build graph, Zod schema definitions in `packages/types/`, runtime logic in `packages/surveys/`, server actions in `apps/web/`, UI components using the existing component library.
- **Source of Truth**: Implementation must follow four authoritative documents exactly:
  - `docs/development/typeform-parity/logic-parity.mdx` — Epic 2.1 primary doc
  - `docs/development/typeform-parity/export-parity.mdx` — Epic 2.2 primary doc
  - `docs/development/typeform-parity/sprint-roadmap.mdx` (lines 164–247) — Sprint 2 steps
  - `docs/development/typeform-parity/question-type-parity.mdx` — Referenced by Epic 2.1 for OpinionScale and Payment context

### 0.1.3 Technical Interpretation

These feature requirements translate to the following technical implementation strategy:

- To **verify logic operator parity**, we will audit the 32 operators in `ZSurveyLogicConditionsOperator` (in `packages/types/surveys/logic.ts`) against the 20 Typeform operator mappings documented in logic-parity.mdx, confirming zero gaps and 100% coverage.
- To **extend logic support for new element types**, we will verify and enhance the `getLeftOperandValue` function in both `packages/surveys/src/lib/logic.ts` and `apps/web/lib/surveyLogic/utils.ts` to handle `opinionScale` as numeric left operands (already partially implemented) and `payment` as submission-state left operands.
- To **verify cyclic detection compatibility**, we will confirm that `findBlocksWithCyclicLogic` in `packages/types/surveys/blocks-validation.ts` correctly traverses blocks containing the new element types (the DFS algorithm is element-type-agnostic by design).
- To **add comprehensive logic test coverage**, we will extend test cases in `packages/surveys/src/lib/logic.test.ts` and `apps/web/lib/surveyLogic/utils.test.ts` covering all applicable operators for `opinionScale` (numeric operators: `equals`, `doesNotEqual`, `isGreaterThan`, `isLessThan`, `isGreaterThanOrEqual`, `isLessThanOrEqual`, `isSubmitted`, `isSkipped`) and `payment` (submission-state operators: `isSubmitted`, `isSkipped`).
- To **implement JSON response export**, we will extend the `format` parameter in `getResponseDownloadFile` (in `apps/web/lib/response/service.ts`) from `"csv" | "xlsx"` to `"csv" | "xlsx" | "json"`, add a `convertToJson` function in `apps/web/lib/utils/file-conversion.ts`, and add a JSON conditional branch in the export pipeline.
- To **expose JSON export in the UI**, we will add JSON download options in the `CustomFilter.tsx` component, update the `ResponseTable.tsx` component, update the `selected-row-settings.tsx` data-table component, update the server action schema in `actions.ts`, and update the `downloadResponsesFile` utility in `utils.ts`.
- To **add JSON export i18n labels**, we will add new translation keys (e.g., `all_responses_json`, `filtered_responses_json`, `selected_responses_json`) across all 14 locale files in `apps/web/locales/`.
- To **validate lossless export**, we will extend the export test suite in `apps/web/lib/response/tests/response.test.ts` with JSON-specific test cases verifying field-by-field equivalence.

## 0.2 Repository Scope Discovery

### 0.2.1 Comprehensive File Analysis

The Formbricks repository is a TypeScript-first pnpm monorepo with two primary source surfaces: `apps/web/` (the Next.js 16 production application) and `packages/` (shared libraries and tooling). Sprint 2 touches files across both surfaces. The following exhaustive file inventory covers every file requiring creation or modification.

**Epic 2.1 — Logic Operator Parity (Existing Files to Verify/Modify):**

| File Path | Type | Purpose |
|---|---|---|
| `packages/types/surveys/logic.ts` | Verify | Confirm 32 operators in `ZSurveyLogicConditionsOperator` cover all 20 Typeform operators |
| `packages/types/surveys/blocks.ts` | Verify | Confirm 3 action types (`jumpToBlock`, `calculate`, `requireAnswer`) cover Typeform actions |
| `packages/types/surveys/blocks-validation.ts` | Verify | Confirm cyclic detection algorithm handles blocks with new element types |
| `packages/types/surveys/constants.ts` | Verify | Confirm `OpinionScale` and `Payment` entries exist in `TSurveyElementTypeEnum` |
| `packages/types/surveys/elements.ts` | Verify | Confirm `ZSurveyOpinionScaleElement` and `ZSurveyPaymentElement` schemas are in `ZSurveyElement` union |
| `packages/surveys/src/lib/logic.ts` | Modify | Ensure `getLeftOperandValue` handles all applicable operators for `opinionScale` and `payment` types |
| `apps/web/lib/surveyLogic/utils.ts` | Modify | Ensure `getLeftOperandValue` and `evaluateSingleCondition` handle `opinionScale` numeric coercion and `payment` submission-state evaluation |
| `packages/surveys/src/lib/logic.test.ts` | Modify | Add/extend test cases for `opinionScale` and `payment` element type logic evaluation |
| `apps/web/lib/surveyLogic/utils.test.ts` | Modify | Add/extend test cases for `opinionScale` and `payment` element type logic in the web editor context |

**Epic 2.2 — JSON Response Export (Existing Files to Modify):**

| File Path | Type | Purpose |
|---|---|---|
| `apps/web/lib/response/service.ts` | Modify | Extend `getResponseDownloadFile` format parameter to include `"json"`; add JSON output branch |
| `apps/web/lib/utils/file-conversion.ts` | Modify | Add `convertToJson` function producing pretty-printed JSON from flat response data |
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/actions.ts` | Modify | Extend `ZGetResponsesDownloadUrlAction` format schema to accept `"json"` |
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/utils.ts` | Modify | Extend `downloadResponsesFile` to handle `"json"` format (MIME type, file creation) |
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/components/CustomFilter.tsx` | Modify | Add JSON download menu items for all-responses and filtered-responses |
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/responses/components/ResponseTable.tsx` | Modify | Add JSON format to `downloadSelectedRows` handler |
| `apps/web/modules/ui/components/data-table/components/selected-row-settings.tsx` | Modify | Add JSON download option to selected row download menu |
| `apps/web/modules/ui/components/data-table/components/data-table-toolbar.tsx` | Verify | Confirm download action passthrough supports new format parameter |
| `apps/web/lib/response/utils.ts` | Verify | Confirm `getResponsesJson` and `getResponsesFileName` work correctly for JSON format |
| `apps/web/lib/response/tests/response.test.ts` | Modify | Add test case for JSON format download |

**i18n Translation Files (All 14 Locales):**

| File Path | Type | Purpose |
|---|---|---|
| `apps/web/locales/en-US.json` | Modify | Add JSON download label translations |
| `apps/web/locales/de-DE.json` | Modify | Add JSON download label translations |
| `apps/web/locales/es-ES.json` | Modify | Add JSON download label translations |
| `apps/web/locales/fr-FR.json` | Modify | Add JSON download label translations |
| `apps/web/locales/hu-HU.json` | Modify | Add JSON download label translations |
| `apps/web/locales/ja-JP.json` | Modify | Add JSON download label translations |
| `apps/web/locales/nl-NL.json` | Modify | Add JSON download label translations |
| `apps/web/locales/pt-BR.json` | Modify | Add JSON download label translations |
| `apps/web/locales/pt-PT.json` | Modify | Add JSON download label translations |
| `apps/web/locales/ro-RO.json` | Modify | Add JSON download label translations |
| `apps/web/locales/ru-RU.json` | Modify | Add JSON download label translations |
| `apps/web/locales/sv-SE.json` | Modify | Add JSON download label translations |
| `apps/web/locales/zh-Hans-CN.json` | Modify | Add JSON download label translations |
| `apps/web/locales/zh-Hant-TW.json` | Modify | Add JSON download label translations |

### 0.2.2 Integration Point Discovery

**API Endpoints Connecting to the Feature:**

- Server action `getResponsesDownloadUrlAction` in `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/actions.ts` — the authenticated entry point for all export requests, currently restricted to `"csv" | "xlsx"` format
- The response service function `getResponseDownloadFile` in `apps/web/lib/response/service.ts` (lines 342–443) — the core export pipeline called by the server action

**Database Models/Migrations Affected:**

- No database schema changes required. The format parameter is a code-level construct, not a database column. Survey data is stored as JSON in PostgreSQL — logic and export changes are purely additive at the TypeScript level.

**Service Classes Requiring Updates:**

- `apps/web/lib/response/service.ts` — `getResponseDownloadFile` function
- `apps/web/lib/utils/file-conversion.ts` — format conversion utilities

**UI Components to Modify:**

- `CustomFilter.tsx` — summary page download dropdown
- `ResponseTable.tsx` — response table selected-row download handler
- `selected-row-settings.tsx` — data-table selected-row download UI
- `data-table-toolbar.tsx` — data-table toolbar (verify passthrough)

### 0.2.3 New File Requirements

**New Source Files to Create:**

No entirely new source files are required. Both epics involve modifications to existing files rather than creating new modules. The JSON export feature extends the existing pipeline in-place, and logic operator parity is a verification and enhancement exercise on existing code.

**New Test Coverage to Add (within existing test files):**

- `packages/surveys/src/lib/logic.test.ts` — Additional test cases for all operators with `opinionScale` and `payment` left operands
- `apps/web/lib/surveyLogic/utils.test.ts` — Additional test cases for `opinionScale` and `payment` logic evaluation in the web editor context
- `apps/web/lib/response/tests/response.test.ts` — New test case for JSON format export validation

### 0.2.4 Web Search Research Conducted

No external web searches are required for this sprint. The implementation is fully defined by the four source-of-truth documents within the repository, and all libraries (`@json2csv/node`, `xlsx`, `zod`) are already installed with known versions. The Formbricks codebase provides complete patterns for extending the export pipeline and logic evaluation engine.

## 0.3 Dependency Inventory

### 0.3.1 Private and Public Packages

The following packages are directly relevant to the Sprint 2 implementation:

| Registry | Package | Version | Purpose |
|---|---|---|---|
| workspace | `@formbricks/types` | 0.0.0 (workspace) | Survey type definitions including `ZSurveyLogicConditionsOperator`, `ZSurveyBlockLogic`, `ZSurveyElement` union, and `TSurveyElementTypeEnum` |
| workspace | `@formbricks/surveys` | 1.0.0 (workspace) | Survey runtime including logic evaluation engine (`logic.ts`) and survey renderer components |
| workspace | `@formbricks/database` | workspace | Prisma schema, database client, and migration infrastructure |
| workspace | `@formbricks/logger` | workspace | Logging utility used in file conversion error handling |
| npm | `zod` | 3.24.4 | Schema validation used for all type definitions and server action input validation |
| npm | `zod-openapi` | 4.2.4 | OpenAPI extension for Zod schemas |
| npm | `@json2csv/node` | 7.0.6 | CSV format conversion using `AsyncParser` in the export pipeline |
| npm (vendored) | `xlsx` | 0.20.3 | XLSX format conversion using SheetJS, vendored as `file:vendor/xlsx-0.20.3.tgz` |
| npm | `@prisma/client` | 6.14.0 | Type-safe database client for response retrieval |
| npm | `next` | 16.1.6 | Application framework (App Router with server actions) |
| npm | `react` | 19.2.3 | UI rendering framework |
| npm | `stripe` | 16.12.0 | Stripe SDK for payment element type (Epic 2.1 context — payment logic operators) |

### 0.3.2 Dependency Updates

**No new dependencies are required.** Sprint 2 exclusively uses existing packages already installed in the monorepo. The JSON export uses native `JSON.stringify()` — no additional serialization library is needed.

**Import Updates:**

The following files require import additions or modifications:

- `apps/web/lib/utils/file-conversion.ts` — No new imports needed; the new `convertToJson` function uses only built-in `JSON.stringify`
- `apps/web/lib/response/service.ts` — Import the new `convertToJson` function from `file-conversion.ts`
- `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/utils.ts` — Update the type annotation for `fileType` parameter to include `"json"`
- `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/components/CustomFilter.tsx` — Update the `handleDownloadResponses` type annotation to include `"json"`
- `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/responses/components/ResponseTable.tsx` — Update the `downloadSelectedRows` type annotation to include `"json"`

**External Reference Updates:**

- `apps/web/locales/*.json` (14 files) — Add three new translation keys per locale:
  - `environments.surveys.summary.all_responses_json`
  - `environments.surveys.summary.filtered_responses_json`
  - `environments.surveys.summary.selected_responses_json`

## 0.4 Integration Analysis

### 0.4.1 Existing Code Touchpoints

**Epic 2.1 — Logic Operator Parity Touchpoints:**

- **`packages/surveys/src/lib/logic.ts` (line 107–118)**: The `getLeftOperandValue` function already contains explicit numeric handling for `OpinionScale`, `NPS`, and `Rating` element types. Verification is needed to confirm this covers all applicable operators. The `Payment` type is not currently listed in this numeric handling block because payment responses are string-based submission states (e.g., `"paid"`, `"skipped"`), which route through the default `data[leftOperand.value]` path.
- **`apps/web/lib/surveyLogic/utils.ts` (lines 407–413, 536–540)**: The web editor's duplicate logic evaluation already handles `Payment` for `isSubmitted` (checking `leftValue !== "skipped"`) and `opinionScale` for numeric coercion. Both need verification for completeness across all applicable operators.
- **`packages/types/surveys/blocks-validation.ts` (lines 3–81)**: The `findBlocksWithCyclicLogic` DFS algorithm operates on block-level navigation (`jumpToBlock` targets and `logicFallback` references). It is element-type-agnostic — it only traverses block IDs, not element types within blocks. No modification is required, but verification that it processes blocks containing the new element types without error is necessary.

**Epic 2.2 — JSON Response Export Touchpoints:**

- **`apps/web/lib/response/service.ts` (line 344)**: Direct modification required. The format parameter type `"csv" | "xlsx"` must be extended to `"csv" | "xlsx" | "json"`. The conditional branch at lines 425–430 must be expanded with a JSON path.
- **`apps/web/lib/response/service.ts` (line 347)**: The `validateInputs` call uses `ZString` for the format parameter. This must be verified to accept `"json"` (it validates against `z.string()`, which is permissive, so no change is needed at the Zod string level — but the server action schema in `actions.ts` is the actual gate).
- **`apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/actions.ts` (line 26)**: The server action schema `z.union([z.literal("csv"), z.literal("xlsx")])` must be extended with `z.literal("json")`.
- **`apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/utils.ts` (lines 1–44)**: The `downloadResponsesFile` function handles `"xlsx"` (binary base64 decode) and `"csv"` (text blob) formats. A `"json"` branch must be added with MIME type `"application/json;charset=utf-8"`.
- **`apps/web/lib/response/utils.ts` (line 640–645)**: The `getResponsesFileName` function already accepts a dynamic extension string parameter. Passing `"json"` will automatically produce file names like `export-{name}-{date}.json`. No modification needed.

### 0.4.2 Dependency Injections

No new service registrations or dependency injections are required. Both epics extend existing functions and components within the established dependency graph:

- The `getResponseDownloadFile` function is already wired into the `getResponsesDownloadUrlAction` server action
- The logic evaluation functions are already imported and used by the survey runtime and editor
- The file conversion utilities are already imported by the response service

### 0.4.3 Database/Schema Updates

No database migrations or schema changes are required for Sprint 2:

- **Logic Parity (Epic 2.1)**: Logic operators, conditions, and actions are defined in TypeScript Zod schemas stored in `packages/types/`. They are persisted as JSON within the survey document in PostgreSQL. No SQL migrations are needed.
- **JSON Export (Epic 2.2)**: The export format is a code-level parameter passed to a function. It does not correspond to any database column or Prisma model field. The response data being exported is read-only.

### 0.4.4 Cross-Epic Integration

The two epics in Sprint 2 are independent and can proceed in parallel without cross-dependencies:

- Epic 2.1 (Logic Parity) modifies `packages/types/surveys/`, `packages/surveys/src/lib/`, and `apps/web/lib/surveyLogic/`
- Epic 2.2 (JSON Export) modifies `apps/web/lib/response/`, `apps/web/lib/utils/`, `apps/web/app/(app)/.../surveys/[surveyId]/`, and locale files

The only shared touchpoint is `packages/types/` (both epics reference types from this package), but they operate on different schemas — Epic 2.1 on `logic.ts`/`blocks.ts` and Epic 2.2 on `responses.ts`. No merge conflicts are anticipated.

## 0.5 Technical Implementation

### 0.5.1 File-by-File Execution Plan

**Group 1 — Epic 2.1: Logic Operator Parity Verification and Enhancement**

- **VERIFY: `packages/types/surveys/logic.ts`** — Confirm all 32 operators in `ZSurveyLogicConditionsOperator` are present. Validate the 20-operator Typeform mapping documented in `logic-parity.mdx` against the actual enum values. Confirm the 12 unary operators in `operatorsWithoutRightOperand` are correctly listed.
- **VERIFY: `packages/types/surveys/blocks.ts`** — Confirm the 3 action types (`jumpToBlock`, `calculate`, `requireAnswer`) are implemented with correct Zod schemas. Validate that multi-action logic rows process correctly.
- **VERIFY: `packages/types/surveys/blocks-validation.ts`** — Confirm the DFS-based `findBlocksWithCyclicLogic` function handles blocks containing `opinionScale` and `payment` elements without error. The algorithm traverses block-level navigation (jump targets and fallbacks), not element-level types.
- **MODIFY: `packages/surveys/src/lib/logic.ts`** — Verify and enhance the `getLeftOperandValue` function. The OpinionScale numeric handling already exists at lines 108–118. Confirm that `Payment` elements correctly route through the default `data[leftOperand.value]` path for submission-state operators (`isSubmitted`, `isSkipped`). Add explicit handling if the default path does not correctly coerce payment response values.
- **MODIFY: `apps/web/lib/surveyLogic/utils.ts`** — Verify and enhance the web editor's logic evaluation. OpinionScale numeric coercion exists at lines 536–540. Payment `isSubmitted` handling exists at lines 407–413. Confirm completeness of both paths for all applicable operators.
- **MODIFY: `packages/surveys/src/lib/logic.test.ts`** — Add comprehensive test cases covering:
  - `opinionScale` with operators: `equals`, `doesNotEqual`, `isGreaterThan`, `isLessThan`, `isGreaterThanOrEqual`, `isLessThanOrEqual`, `isSubmitted`, `isSkipped`
  - `payment` with operators: `isSubmitted`, `isSkipped`
  - Nested condition groups combining new element types with existing types
  - Edge cases: boundary values for scale ranges (1, 5, 7, 10), empty/skipped responses
- **MODIFY: `apps/web/lib/surveyLogic/utils.test.ts`** — Add test cases mirroring the runtime tests for the web editor's logic evaluation, covering `opinionScale` numeric operators and `payment` submission-state operators.

**Group 2 — Epic 2.2: JSON Response Export Core Implementation**

- **MODIFY: `apps/web/lib/utils/file-conversion.ts`** — Add `convertToJson` function:
  ```typescript
  export const convertToJson = (
    fields: string[],
    jsonData: Record<string, string | number>[]
  ): string => {
    return JSON.stringify(jsonData, null, 2);
  };
  ```
- **MODIFY: `apps/web/lib/response/service.ts`** — Extend `getResponseDownloadFile`:
  - Change format parameter type from `"csv" | "xlsx"` to `"csv" | "xlsx" | "json"`
  - Add JSON conditional branch after the existing `getResponsesJson` call (which already produces intermediate JSON data):
    ```typescript
    if (format === "json") {
      fileContents = convertToJson(headers, jsonData);
    }
    ```
- **MODIFY: `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/actions.ts`** — Extend the server action format schema:
  ```typescript
  format: z.union([z.literal("csv"), z.literal("xlsx"), z.literal("json")])
  ```

**Group 3 — Epic 2.2: JSON Response Export UI and Client Updates**

- **MODIFY: `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/utils.ts`** — Extend `downloadResponsesFile` to handle `"json"` format:
  - Update the `fileType` parameter type to `"csv" | "xlsx" | "json"`
  - Add a JSON branch creating a `File` with MIME type `"application/json;charset=utf-8"`
- **MODIFY: `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/components/CustomFilter.tsx`** — Add JSON download menu items:
  - Update `handleDownloadResponses` type signature to accept `"json"`
  - Add "All responses (JSON)" dropdown item calling `handleDownloadResponses(FilterDownload.ALL, "json")`
  - Add "Filtered responses (JSON)" dropdown item calling `handleDownloadResponses(FilterDownload.FILTER, "json")`
- **MODIFY: `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/responses/components/ResponseTable.tsx`** — Update the `downloadSelectedRows` function type to accept `"csv" | "xlsx" | "json"` and add JSON handling
- **MODIFY: `apps/web/modules/ui/components/data-table/components/selected-row-settings.tsx`** — Add "Selected responses (JSON)" dropdown item calling `handleDownloadSelectedRows("json")`

**Group 4 — Epic 2.2: i18n and Tests**

- **MODIFY: `apps/web/locales/*.json` (14 locale files)** — Add translation keys for JSON download labels. For `en-US.json`:
  - `"all_responses_json": "All responses (JSON)"`
  - `"filtered_responses_json": "Filtered responses (JSON)"`
  - `"selected_responses_json": "Selected responses (JSON)"`
  - Apply equivalent translations for all 13 other locales
- **MODIFY: `apps/web/lib/response/tests/response.test.ts`** — Add test case for JSON format:
  - Test that `getResponseDownloadFile` accepts `"json"` format
  - Verify returned `fileContents` is valid JSON parseable by `JSON.parse()`
  - Verify returned `fileName` ends with `.json`
  - Verify field-by-field equivalence between source response data and parsed JSON export

### 0.5.2 Implementation Approach per File

The implementation proceeds in dependency order:

- **Establish type-level changes first** by extending the format union in the server action schema (`actions.ts`) and the service function signature (`service.ts`). This ensures TypeScript type checking guides downstream changes.
- **Add the conversion function** (`convertToJson` in `file-conversion.ts`) and wire it into the export pipeline (`service.ts`) — the core backend feature.
- **Update client-side utilities** (`utils.ts` for file download handling) to accept the new format.
- **Extend UI components** (`CustomFilter.tsx`, `ResponseTable.tsx`, `selected-row-settings.tsx`) to expose the JSON option to users.
- **Add i18n labels** across all 14 locales to support the new UI elements.
- **Implement comprehensive tests** for both epics to validate correctness and satisfy lossless export constraints.

### 0.5.3 User Interface Design

The JSON export feature surfaces in the existing download dropdown menus within the survey analysis views. The changes are additive — new menu items for JSON are appended after the existing CSV and XLSX options:

- **Summary page** (`CustomFilter.tsx`): The download dropdown currently shows 4 items (All CSV, All XLSX, Filtered CSV, Filtered XLSX). Two new items are added: "All responses (JSON)" and "Filtered responses (JSON)", following the same visual pattern as existing items.
- **Response table** (`ResponseTable.tsx` + `selected-row-settings.tsx`): The selected-row download dropdown currently shows 2 items (Selected CSV, Selected XLSX). One new item is added: "Selected responses (JSON)".
- No new screens, modals, or navigation changes are required. The JSON option integrates seamlessly into the existing export UI pattern.

## 0.6 Scope Boundaries

### 0.6.1 Exhaustively In Scope

**Epic 2.1 — Logic Operator Parity:**

- Logic type definitions: `packages/types/surveys/logic.ts`
- Block logic definitions: `packages/types/surveys/blocks.ts`
- Block validation (cyclic detection): `packages/types/surveys/blocks-validation.ts`
- Element type enum: `packages/types/surveys/constants.ts`
- Element schemas: `packages/types/surveys/elements.ts`
- Runtime logic evaluation: `packages/surveys/src/lib/logic.ts`
- Editor logic evaluation: `apps/web/lib/surveyLogic/utils.ts`
- Runtime logic tests: `packages/surveys/src/lib/logic.test.ts`
- Editor logic tests: `apps/web/lib/surveyLogic/utils.test.ts`

**Epic 2.2 — JSON Response Export:**

- Response export service: `apps/web/lib/response/service.ts`
- Response data utilities: `apps/web/lib/response/utils.ts`
- File conversion utilities: `apps/web/lib/utils/file-conversion.ts`
- Server action: `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/actions.ts`
- Client-side download: `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/utils.ts`
- Download UI (summary): `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/components/CustomFilter.tsx`
- Download UI (responses): `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/responses/components/ResponseTable.tsx`
- Download UI (data-table): `apps/web/modules/ui/components/data-table/components/selected-row-settings.tsx`
- Download UI (toolbar): `apps/web/modules/ui/components/data-table/components/data-table-toolbar.tsx`
- Response export tests: `apps/web/lib/response/tests/response.test.ts`
- All locale files: `apps/web/locales/*.json` (14 files)

**Documentation (Verification Only):**

- `docs/development/typeform-parity/logic-parity.mdx` — Source of truth for operator mapping
- `docs/development/typeform-parity/export-parity.mdx` — Source of truth for export parity and lossless validation
- `docs/development/typeform-parity/sprint-roadmap.mdx` — Sprint 2 step definitions (lines 164–247)
- `docs/development/typeform-parity/question-type-parity.mdx` — Context for new element types from Sprint 1

### 0.6.2 Explicitly Out of Scope

- **Sprint 1 element type implementation** — `opinionScale` and `payment` types are already implemented. No changes to element schemas, editor components (`opinion-scale-element-form.tsx`, `payment-element-form.tsx`), or renderer components (`opinion-scale-element.tsx`, `payment-element.tsx`).
- **Sprint 3 features** — Webhook payload parity, embed/share enhancements. These depend on Sprint 2 but are not part of this scope.
- **Sprint 4 features** — Workspace governance alignment and migration safety procedures.
- **Structured JSON API endpoint** — The export-parity.mdx document recommends flat JSON first (using existing `getResponsesJson`) with a future structured JSON API for advanced integrations. Only flat JSON export is in scope.
- **OpenAPI specification updates** — While the sprint-roadmap.mdx mentions documenting the JSON export in API v1 and v2 specs, the primary deliverable is the functional implementation. API spec documentation for the endpoint-level export can be addressed separately.
- **Performance optimizations** — The export pipeline already uses cursor-based batching (3,000 per batch). No performance tuning beyond the JSON conversion branch is in scope.
- **Refactoring of existing code** — No changes to existing CSV or XLSX export paths, existing logic operators, or unrelated modules.
- **Database migrations** — No SQL migrations are required for Sprint 2. All changes are at the TypeScript/application level.

## 0.7 Rules for Feature Addition

### 0.7.1 Parity Constraints

- **100% Logic Jump Coverage**: Every Typeform logic condition type must have a confirmed Formbricks equivalent. The 20-operator mapping in `logic-parity.mdx` must be verified against the 32-operator `ZSurveyLogicConditionsOperator` enum. No gaps are permitted.
- **Lossless Export**: JSON export must preserve every response field without truncation, rounding, or encoding loss. The 7 fidelity metrics defined in `export-parity.mdx` (field completeness, value accuracy, metadata preservation, hidden field completeness, file reference integrity, Unicode support, round-trip verification) must be satisfiable by the implementation.
- **No Broken Existing Forms**: All changes must be additive. Existing surveys with the 17 element types in the `ZSurveyElement` union must continue to parse, render, and export correctly. No existing operator behavior may be altered.

### 0.7.2 Architectural Conventions

- **Monorepo Package Boundaries**: Type definitions belong in `packages/types/`, runtime logic in `packages/surveys/`, server actions and services in `apps/web/`. Cross-package imports must follow the established workspace resolution pattern.
- **Zod Schema Patterns**: All new or modified schemas must follow the existing Zod validation patterns. Format unions use `z.union([z.literal("csv"), z.literal("xlsx"), z.literal("json")])` — not `z.enum()` — matching the existing `ZGetResponsesDownloadUrlAction` pattern.
- **Server Action Security**: The `authenticatedActionClient` with `checkAuthorizationUpdated` middleware must be preserved for all export actions. The JSON format must be gated behind the same authorization checks (organization owner/manager or project team read permission) as CSV and XLSX.
- **i18n Pattern**: Translation keys must follow the existing namespace pattern `environments.surveys.summary.*` and be added to all 14 locale files. The `en-US.json` file serves as the canonical source; other locales may use English as placeholder text pending translation.

### 0.7.3 Testing Requirements

- **Logic Test Coverage**: Tests must cover all applicable operators for `opinionScale` (numeric: `equals`, `doesNotEqual`, `isGreaterThan`, `isLessThan`, `isGreaterThanOrEqual`, `isLessThanOrEqual`; state: `isSubmitted`, `isSkipped`) and `payment` (state: `isSubmitted`, `isSkipped`) in both the runtime engine (`packages/surveys/src/lib/logic.test.ts`) and the web editor engine (`apps/web/lib/surveyLogic/utils.test.ts`).
- **Export Test Coverage**: The JSON export test must verify: (a) the function accepts `"json"` format, (b) the returned content is valid parseable JSON, (c) the file name ends with `.json`, and (d) field-by-field equivalence between source data and exported data.
- **Backward Compatibility**: Existing test suites must continue to pass without modification. Running the full test suite (`pnpm test`) must result in zero regressions.

### 0.7.4 Code Quality Standards

- **TypeScript Strict Mode**: All modified files must satisfy the existing TypeScript strict mode configuration. No `any` types or type assertions should be introduced.
- **Error Handling**: The JSON conversion function must handle edge cases (empty response arrays, null values) gracefully, following the error handling patterns in the existing `convertToCsv` and `convertToXlsxBuffer` functions.
- **Consistent Formatting**: All code must be formatted with Prettier using the shared config from `packages/config-prettier` and pass ESLint checks from `.eslintrc.cjs`.

## 0.8 References

### 0.8.1 Source of Truth Documents

| Document | Path | Purpose |
|---|---|---|
| Logic Parity | `docs/development/typeform-parity/logic-parity.mdx` | Epic 2.1 primary doc — exhaustive operator-to-operator mapping between Typeform and Formbricks |
| Export Parity | `docs/development/typeform-parity/export-parity.mdx` | Epic 2.2 primary doc — response export format comparison with JSON gap analysis and lossless validation procedures |
| Sprint Roadmap | `docs/development/typeform-parity/sprint-roadmap.mdx` | Sprint 2 step definitions (lines 164–247), dependency graph, and validation milestones |
| Question Type Parity | `docs/development/typeform-parity/question-type-parity.mdx` | Context for Epic 2.1 — OpinionScale and Payment type specifications added in Sprint 1 |

### 0.8.2 Repository Files Searched and Analyzed

**Type System Files:**

| File Path | Lines Analyzed | Key Findings |
|---|---|---|
| `packages/types/surveys/logic.ts` | 1–247 | 32 operators confirmed in `ZSurveyLogicConditionsOperator`; 12 unary operators listed |
| `packages/types/surveys/blocks.ts` | 1–147 | 3 action types confirmed; `ZSurveyBlock` with logic and fallback fields |
| `packages/types/surveys/blocks-validation.ts` | 1–87 | DFS cyclic detection is element-type-agnostic; works at block ID level |
| `packages/types/surveys/constants.ts` | 1–21 | 17 element types including `Payment` and `OpinionScale` confirmed |
| `packages/types/surveys/elements.ts` | 350–400 | `ZSurveyOpinionScaleElement` and `ZSurveyPaymentElement` schemas confirmed in `ZSurveyElement` union |
| `packages/types/surveys/validation-rules.ts` | 299–300 | `payment: ["minValue", "maxValue"]` and `opinionScale: []` confirmed |

**Logic Runtime Files:**

| File Path | Lines Analyzed | Key Findings |
|---|---|---|
| `packages/surveys/src/lib/logic.ts` | 1–300 | `getLeftOperandValue` handles `OpinionScale` at lines 108–118 with numeric coercion |
| `apps/web/lib/surveyLogic/utils.ts` | 400–540 | Payment `isSubmitted` handling at lines 407–413; OpinionScale numeric coercion at lines 536–540 |
| `packages/surveys/src/lib/logic.test.ts` | 1168–1350 | Existing OpinionScale tests (numeric operators) and Payment tests (`isSubmitted`, `isSkipped`) |
| `apps/web/lib/surveyLogic/utils.test.ts` | 1379–1530 | Existing OpinionScale and Payment tests in web editor context |

**Export Pipeline Files:**

| File Path | Lines Analyzed | Key Findings |
|---|---|---|
| `apps/web/lib/response/service.ts` | 340–443 | `getResponseDownloadFile` with `format: "csv" \| "xlsx"` — JSON gap confirmed |
| `apps/web/lib/utils/file-conversion.ts` | 1–31 | `convertToCsv` and `convertToXlsxBuffer` — pattern for new `convertToJson` function |
| `apps/web/lib/response/utils.ts` | 630–795 | `getResponsesJson` produces flat `Record<string, string \| number>[]` — reusable for JSON export |
| `apps/web/app/(app)/.../actions.ts` | 1–175 | Server action schema restricts format to `"csv" \| "xlsx"` at line 26 |
| `apps/web/app/(app)/.../utils.ts` | 1–44 | `downloadResponsesFile` handles CSV/XLSX — needs JSON branch |
| `apps/web/app/(app)/.../CustomFilter.tsx` | 240–448 | Download dropdown with 4 items (CSV/XLSX × All/Filtered) — needs JSON items |
| `apps/web/app/(app)/.../ResponseTable.tsx` | 207–243 | Selected-row download handler — needs JSON format support |
| `apps/web/modules/ui/.../selected-row-settings.tsx` | 96–182 | Selected row download UI — needs JSON menu item |
| `apps/web/lib/response/tests/response.test.ts` | 208–233 | Existing CSV/XLSX download tests — needs JSON test |

**Configuration and Infrastructure Files:**

| File Path | Lines Analyzed | Key Findings |
|---|---|---|
| `package.json` (root) | 1–107 | Node.js ≥ 20.0.0, pnpm 10.28.2, React 19.2.3, Next.js 16.1.6 |
| `apps/web/package.json` | (dependencies) | `@json2csv/node` 7.0.6, `xlsx` 0.20.3 (vendored), `stripe` 16.12.0 |
| `packages/types/package.json` | 1–20 | `zod` 3.24.4, `@prisma/client` 6.14.0 |
| `apps/web/locales/en-US.json` | (translation keys) | Existing keys: `all_responses_csv`, `all_responses_excel`, `filtered_responses_csv`, `filtered_responses_excel`, `selected_responses_csv`, `selected_responses_excel` |

### 0.8.3 Attachments

No attachments (Figma URLs, design files, or external documents) were provided for this task. All implementation guidance comes from the four source-of-truth documents within the repository.

### 0.8.4 Folders Explored

| Folder Path | Depth | Purpose |
|---|---|---|
| `` (root) | 0 | Monorepo root — identified workspace structure, build tools, and configuration |
| `docs/` | 1 | Documentation workspace — located source-of-truth MDX files |
| `docs/development/typeform-parity/` | 3 | Typeform parity initiative docs — all 4 source documents |
| `packages/types/surveys/` | 3 | Survey type definitions — logic, blocks, elements, constants |
| `packages/surveys/src/lib/` | 4 | Survey runtime — logic evaluation engine and tests |
| `apps/web/lib/response/` | 3 | Response export service and utilities |
| `apps/web/lib/utils/` | 3 | File conversion utilities (CSV, XLSX) |
| `apps/web/lib/surveyLogic/` | 3 | Web editor logic evaluation and tests |
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/` | 6 | Survey analysis pages — actions, utils, components |
| `apps/web/modules/ui/components/data-table/components/` | 5 | Data table UI components with download functionality |
| `apps/web/locales/` | 2 | i18n translation files (14 locales) |
| `apps/web/modules/survey/editor/components/` | 4 | Survey editor components — verified OpinionScale and Payment forms exist |
| `packages/surveys/src/components/elements/` | 4 | Survey renderer components — verified OpinionScale and Payment renderers exist |

