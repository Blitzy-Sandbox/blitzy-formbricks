# Technical Specification

# 0. Agent Action Plan

## 0.1 Intent Clarification

### 0.1.1 Core Feature Objective

Based on the prompt, the Blitzy platform understands that the new feature requirement is to **extend the Formbricks survey type system by adding two new element types** to the `TSurveyElementTypeEnum` enumeration, completing Sprint 1 — Foundation (Question Types). Specifically:

- **Add two new members to `TSurveyElementTypeEnum`** in `packages/types/surveys/constants.ts`, growing the current 15-member enum (`FileUpload`, `OpenText`, `MultipleChoiceSingle`, `MultipleChoiceMulti`, `NPS`, `CTA`, `Rating`, `Consent`, `PictureSelection`, `Cal`, `Date`, `Matrix`, `Address`, `Ranking`, `ContactInfo`) to 17 members.
- **Establish complete type-system foundations** for each new type: Zod schemas, TypeScript inferred types, validation rules, logic operator mappings, summary schemas, and backward-compatible deprecated question type mirrors.
- **Ensure downstream compatibility** so that logic operators, webhook payloads, export formats, integration mappings, survey renderer conditional branches, and survey editor UI all recognize and correctly handle the new types.

Implicit requirements detected:
- The two new element types have **not been explicitly named** in the user's prompt. The implementation plan must be structured as a **generic two-type addition scaffold** that accommodates any two new question types (referred to as `TypeA` and `TypeB` throughout this plan until concrete names are provided).
- Each new type requires a **mirror deprecated `ZSurveyXxxQuestion`** schema in `packages/types/surveys/types.ts` for v1 API backward compatibility, matching the existing pattern used by all 15 current types.
- The `isInvalidOperatorsForQuestionType` and `isInvalidOperatorsForElementType` switch statements in `packages/types/surveys/types.ts` must include explicit `case` branches for each new type — the existing `default` branch returns `true` (invalid), causing silent failures.

### 0.1.2 Special Instructions and Constraints

- **Foundational Sprint:** This is Sprint 1, meaning all downstream features (logic operators, webhook payloads, export formats) depend on these type definitions being complete and correct. No half-measures are acceptable.
- **Maintain backward compatibility:** Every existing `TSurveyQuestionTypeEnum` deprecated mirror must remain intact. New types must also receive equivalent deprecated mirrors.
- **Follow repository conventions:** The codebase uses a consistent pattern for each element type — enum member → Zod element schema → union inclusion → deprecated question mirror → logic operator mapping → summary schema → editor form component → renderer component → integration mapping. All layers must be addressed.
- **No temporal planning:** This plan describes **what** and **how**, never **when**.

### 0.1.3 Technical Interpretation

These feature requirements translate to the following technical implementation strategy:

- To **register new element types**, we will add two new enum members to `TSurveyElementTypeEnum` in `packages/types/surveys/constants.ts` and create corresponding Zod schemas in `packages/types/surveys/elements.ts` following the `ZSurveyElementBase.extend(...)` pattern used by all existing types.
- To **maintain type-union completeness**, we will add the new Zod schemas to the `ZSurveyElement` discriminated union in `packages/types/surveys/elements.ts` and to the deprecated `ZSurveyQuestion` union in `packages/types/surveys/types.ts`.
- To **support conditional logic**, we will add `case` branches to `isInvalidOperatorsForQuestionType` and `isInvalidOperatorsForElementType` in `packages/types/surveys/types.ts`, define applicable logic operators per type, and register entries in the logic-rule-engine at `apps/web/modules/survey/editor/lib/logic-rule-engine.ts`.
- To **enable survey creation**, we will create editor form components at `apps/web/modules/survey/editor/components/`, add element presets to `apps/web/modules/survey/lib/elements.tsx`, and register renderer components in both `packages/surveys/src/components/` and `packages/survey-ui/src/elements/`.
- To **ensure analytics completeness**, we will create summary schemas (`ZSurveyElementSummaryTypeA/TypeB`) in `packages/types/surveys/types.ts`, add them to the `ZSurveyElementSummary` union, and add conditional branches to the SummaryList rendering component.
- To **maintain integration parity**, we will add Notion type mappings in the integration constants file and ensure webhook/pipeline handling covers the new types.


## 0.2 Repository Scope Discovery

### 0.2.1 Comprehensive File Analysis

The addition of two new element types propagates through the entire Formbricks monorepo. The following exhaustive file inventory was derived by tracing every reference to `TSurveyElementTypeEnum`, `TSurveyQuestionTypeEnum`, `ZSurveyElement`, and related identifiers across the codebase.

**Type System Layer — `packages/types/surveys/`**

| File | Purpose | Change Type |
|------|---------|-------------|
| `packages/types/surveys/constants.ts` | `TSurveyElementTypeEnum` definition (lines 1–18) | MODIFY — add two new enum members |
| `packages/types/surveys/elements.ts` | Zod element schemas and `ZSurveyElement` union (lines 354–375) | MODIFY — add two new Zod schemas, extend union |
| `packages/types/surveys/types.ts` | Deprecated `TSurveyQuestionTypeEnum`, `ZSurveyQuestion` union, summary schemas, logic validators | MODIFY — add deprecated mirrors, summary schemas, operator validators |
| `packages/types/surveys/validation-rules.ts` | `APPLICABLE_RULES` mapping (lines 289–299) | MODIFY — add rule entries for new types if applicable |
| `packages/types/surveys/logic.ts` | Logic operator definitions | NO CHANGE — operators are generic |
| `packages/types/surveys/blocks.ts` | Block definition and logic actions | NO CHANGE — uses `ZSurveyElements` which auto-includes new types |
| `packages/types/surveys/validation.ts` | Shared validation utilities | EVALUATE — may need updates to `validateQuestionLabels`/`validateElementLabels` |
| `packages/types/surveys/elements-validation.ts` | Element-specific label validation | EVALUATE — check for type-specific branches |

**Survey Editor — `apps/web/modules/survey/`**

| File | Purpose | Change Type |
|------|---------|-------------|
| `apps/web/modules/survey/lib/elements.tsx` | Element type registry, presets, icons, defaults | MODIFY — add entries to `getElementTypes()` array |
| `apps/web/modules/survey/editor/components/add-element-button.tsx` | Element addition UI | NO CHANGE — reads dynamically from `getElementTypes()` |
| `apps/web/modules/survey/editor/components/add-element-to-block-button.tsx` | Block element addition UI | NO CHANGE — reads dynamically from `getElementTypes()` |
| `apps/web/modules/survey/editor/components/elements-view.tsx` | Elements view orchestrator | EVALUATE — element rendering logic |
| `apps/web/modules/survey/editor/components/block-settings.tsx` | Block settings panel | EVALUATE — may need type-specific branches |
| `apps/web/modules/survey/editor/lib/logic-rule-engine.ts` | Logic operator mappings per element type | MODIFY — add operator definitions for new types |
| `apps/web/modules/survey/editor/lib/logic-rule-engine.test.ts` | Logic rule engine tests | MODIFY — add test cases for new types |
| `apps/web/modules/survey/editor/lib/validation.ts` | Survey editor validation | EVALUATE — may need type-specific validation |
| `apps/web/modules/survey/editor/lib/survey.test.ts` | Survey editor tests | MODIFY — update tests for new types |
| `apps/web/modules/survey/components/element-form-input/index.tsx` | Element form input routing | MODIFY — add case branch for new types |
| `apps/web/modules/survey/components/element-form-input/utils.test.ts` | Form input utility tests | MODIFY — add test coverage |

**New Editor Form Components to CREATE:**

| File | Purpose |
|------|---------|
| `apps/web/modules/survey/editor/components/type-a-element-form.tsx` | Editor form for TypeA element |
| `apps/web/modules/survey/editor/components/type-b-element-form.tsx` | Editor form for TypeB element |

**Survey Renderer — `packages/surveys/src/`**

| File | Purpose | Change Type |
|------|---------|-------------|
| `packages/surveys/src/components/general/element-conditional.tsx` | Conditional element rendering switch | MODIFY — add case branches for new types |
| `packages/surveys/src/lib/logic.ts` | Client-side logic evaluation | EVALUATE — may need type-specific handling |
| `packages/surveys/src/lib/logic.test.ts` | Logic evaluation tests | MODIFY — add test coverage |
| `packages/surveys/src/lib/recall.ts` | Recall/piping data resolution | EVALUATE — type-specific value extraction |
| `packages/surveys/src/lib/validation/evaluator.ts` | Client-side validation evaluator | MODIFY — add type branches for new types |
| `packages/surveys/src/lib/validation/evaluator.test.ts` | Validation evaluator tests | MODIFY — add test cases |
| `packages/surveys/src/lib/validation/validators.test.ts` | Validator unit tests | MODIFY — add test coverage |

**New Renderer Components to CREATE:**

| File | Purpose |
|------|---------|
| `packages/surveys/src/components/elements/type-a-element.tsx` | Renderer for TypeA in legacy survey package |
| `packages/surveys/src/components/elements/type-b-element.tsx` | Renderer for TypeB in legacy survey package |
| `packages/survey-ui/src/elements/type-a-element.tsx` | Renderer for TypeA in survey-ui package |
| `packages/survey-ui/src/elements/type-b-element.tsx` | Renderer for TypeB in survey-ui package |
| `packages/survey-ui/src/elements/type-a-element.stories.tsx` | Storybook story for TypeA |
| `packages/survey-ui/src/elements/type-b-element.stories.tsx` | Storybook story for TypeB |

**Analytics & Summary — `apps/web/app/.../summary/`**

| File | Purpose | Change Type |
|------|---------|-------------|
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/SummaryList.tsx` | Summary rendering dispatcher | MODIFY — add conditional branches for new types |
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/lib/surveySummary.ts` | Server-side summary computation | MODIFY — add computation logic for new types |
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/lib/utils.ts` | Summary utility functions | EVALUATE |

**New Summary Components to CREATE:**

| File | Purpose |
|------|---------|
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/TypeASummary.tsx` | Summary display for TypeA |
| `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/TypeBSummary.tsx` | Summary display for TypeB |

**API & Integration Layer**

| File | Purpose | Change Type |
|------|---------|-------------|
| `apps/web/modules/api/v2/lib/element.ts` | API v2 element validation | EVALUATE — multi-choice validation pattern |
| `apps/web/app/api/(internal)/pipeline/lib/handleIntegrations.ts` | Integration pipeline handler | MODIFY — ensure new types flow through |
| `apps/web/app/(app)/environments/[environmentId]/workspace/integrations/notion/constants.ts` | Notion type mapping | MODIFY — add TYPE_MAPPING entries |
| `apps/web/lib/responses.ts` | Response value conversion | MODIFY — add case branches in `convertResponseValue` |
| `apps/web/lib/survey/utils.ts` | Survey utility functions | EVALUATE |
| `apps/web/modules/analysis/components/SingleResponseCard/components/RenderResponse.tsx` | Single response rendering | MODIFY — add type branches |
| `apps/web/modules/analysis/components/SingleResponseCard/components/SingleResponseCardBody.tsx` | Response card body | MODIFY — add type branches |
| `apps/web/app/lib/survey-block-builder.ts` | Survey block builder utilities | EVALUATE — add builder function if applicable |

**Supporting Files**

| File | Purpose | Change Type |
|------|---------|-------------|
| `apps/web/app/lib/templates.ts` | Survey template definitions | EVALUATE — add template if applicable |
| `apps/web/lib/surveyLogic/utils.ts` | Shared survey logic utilities | EVALUATE |
| `apps/web/modules/survey/editor/lib/shared-conditions-factory.test.ts` | Shared conditions factory tests | MODIFY — add coverage |
| `apps/web/lib/i18n/i18n.mock.ts` | i18n test mocks | EVALUATE |
| `apps/web/lib/survey/__mock__/survey.mock.ts` | Survey test mocks | MODIFY — add mock data for new types |
| `packages/types/formbricks-surveys.ts` | Embed surface configuration | NO CHANGE — uses generic element union |
| `packages/types/js.ts` | JS SDK contracts | NO CHANGE — uses generic survey schema |

### 0.2.2 Web Search Research Conducted

No external web search was necessary for this feature. The addition of new survey element types follows a well-established internal pattern documented in `.cursor/commands/create-question.md` and evidenced by the consistent architecture of all 15 existing element types. The existing codebase serves as the authoritative reference for implementation conventions.

### 0.2.3 New File Requirements

**New source files to create:**

- `apps/web/modules/survey/editor/components/type-a-element-form.tsx` — Editor configuration form for TypeA element, following the pattern of existing forms like `rating-element-form.tsx`
- `apps/web/modules/survey/editor/components/type-b-element-form.tsx` — Editor configuration form for TypeB element
- `packages/surveys/src/components/elements/type-a-element.tsx` — Preact/React renderer for TypeA in legacy survey package
- `packages/surveys/src/components/elements/type-b-element.tsx` — Preact/React renderer for TypeB in legacy survey package
- `packages/survey-ui/src/elements/type-a-element.tsx` — React renderer for TypeA in survey-ui design system package
- `packages/survey-ui/src/elements/type-b-element.tsx` — React renderer for TypeB in survey-ui design system package
- `packages/survey-ui/src/elements/type-a-element.stories.tsx` — Storybook stories for TypeA per `.cursor/commands/create-question.md`
- `packages/survey-ui/src/elements/type-b-element.stories.tsx` — Storybook stories for TypeB
- Summary analysis components (paths dependent on summary display strategy — see §0.5)

**New test files to create:**

- Test files are co-located in this repository; new test cases should be added to existing `.test.ts` files rather than creating standalone test files.

**New configuration:**

- No new configuration files needed; element types are registered via code, not config files.


## 0.3 Dependency Inventory

### 0.3.1 Private and Public Packages

All dependencies listed below are already installed in the monorepo. No new external packages are required for adding two new element types — the existing type system infrastructure is sufficient.

| Registry | Package | Version | Purpose |
|----------|---------|---------|---------|
| npm (workspace) | `@formbricks/types` | 0.0.0 (workspace) | Central Zod schema and TypeScript type definitions for the entire monorepo |
| npm (workspace) | `@formbricks/database` | workspace:* | Prisma-backed persistence layer; devDependency of types |
| npm (workspace) | `@formbricks/config-typescript` | workspace:* | Shared TypeScript configuration presets |
| npm (workspace) | `@formbricks/survey-ui` | workspace:* | React-based survey UI toolkit (elements, components, Storybook) |
| npm | `zod` | 3.24.4 | Runtime schema validation for all element type definitions |
| npm | `zod-openapi` | 4.2.4 | OpenAPI metadata extension for Zod schemas (logic.ts) |
| npm | `@prisma/client` | 6.14.0 | ORM client for database persistence (enum re-export) |
| npm | `react` | 19.2.3 | UI framework for editor forms and renderer components |
| npm | `next` | 16.1.6 | App Router framework for web application |
| npm | `i18next` / `react-i18next` | (workspace-managed) | Translation support for element labels and descriptions |
| npm | `@paralleldrive/cuid2` | (workspace-managed) | Unique ID generation for element and choice IDs |
| npm | `lucide-react` | (workspace-managed) | Icon library for element type icons in the editor |

### 0.3.2 Dependency Updates

**No new dependencies are required.** This feature is purely additive, extending existing type definitions, schemas, and component patterns that are already fully supported by the current dependency tree.

**Import Updates**

Files requiring import updates when new types are added (use wildcards):

- `packages/types/surveys/types.ts` — Will import newly created `ZSurveyTypeAElement`, `ZSurveyTypeBElement` from `./elements`
- `packages/surveys/src/components/general/element-conditional.tsx` — Will import new renderer components from `../elements/`
- `apps/web/modules/survey/lib/elements.tsx` — Will import new `TSurveyElementTypeEnum` members (already imported)
- `apps/web/modules/survey/editor/components/block-settings.tsx` — Will import new editor form components
- `apps/web/app/(app)/**/summary/components/SummaryList.tsx` — Will import new summary components

Import transformation rules:
- Old: N/A (new imports only)
- New: `import { ZSurveyTypeAElement, ZSurveyTypeBElement } from "./elements";`
- Apply to: All files listed in §0.2.1 that require new type references

**External Reference Updates**

- `openapi.yml` — May need schema additions if API v2 exposes new element types in request/response schemas
- No build file changes needed — the monorepo's Turbo pipeline and `pnpm-workspace.yaml` already include all affected packages


## 0.4 Integration Analysis

### 0.4.1 Existing Code Touchpoints

**Direct modifications required:**

- **`packages/types/surveys/constants.ts` (line 17):** Add two new enum members after `ContactInfo`. This is the single source of truth for all element type identifiers.
  ```ts
  TypeA = "typeA",
  TypeB = "typeB",
  ```
- **`packages/types/surveys/elements.ts` (lines 354–375):** Add new Zod schemas extending `ZSurveyElementBase`, then include them in the `ZSurveyElement` discriminated union.
- **`packages/types/surveys/types.ts` — Multiple insertion points:**
  - `TSurveyQuestionTypeEnum` (line 91–107): Add deprecated mirror enum members
  - `ZSurveyQuestion` union (lines 703–718): Add deprecated question schemas
  - `ZSurveyQuestionType` enum (lines 738–754): Add deprecated type entries
  - `isInvalidOperatorsForQuestionType` switch (lines 1877–2020): Add `case` branches for new types
  - `isInvalidOperatorsForElementType` switch (lines 2903–3047): Add `case` branches for new types
  - Summary schemas (lines 4132–4219): Add `ZSurveyElementSummaryTypeA` and `ZSurveyElementSummaryTypeB`
  - `ZSurveyElementSummary` union (lines 4204–4219): Include new summary schemas
  - Block element validation section (lines 1307–1697): Add type-specific validation branches if the new types have special fields

**Dependency injections:**

- **`apps/web/modules/survey/lib/elements.tsx`:** Register new element types in the `getElementTypes()` array with icon, label, description, and default preset configuration. This is the central registry that the editor UI reads dynamically.
- **`apps/web/modules/survey/editor/lib/logic-rule-engine.ts`:** Add logic operator definitions for new types. The engine maps `TSurveyElementTypeEnum` members to arrays of valid `ZSurveyLogicConditionsOperator` values.

**Database / Schema updates:**

- **No database migrations required.** Survey questions and elements are stored as JSON columns in PostgreSQL (via Prisma's `Json` type). The `TSurveyElementTypeEnum` is a TypeScript-only enum, not a Prisma enum — element types are persisted as string values within the JSON payload. Adding new enum members is fully backward-compatible with existing stored data.

### 0.4.2 Integration Pipeline Touchpoints

The following integration pathways must handle new element types:

**Webhook / Pipeline Integration:**
- `apps/web/app/api/(internal)/pipeline/lib/handleIntegrations.ts` — Fans out response events to integrations. Uses element types to determine data transformation. Must pass through new types correctly.

**Notion Integration:**
- `apps/web/app/(app)/environments/[environmentId]/workspace/integrations/notion/constants.ts` — The `TYPE_MAPPING` object maps each `TSurveyElementTypeEnum` member to Notion property types. New entries must be added:
  ```ts
  [TSurveyElementTypeEnum.TypeA]: ["rich_text"],
  [TSurveyElementTypeEnum.TypeB]: ["rich_text"],
  ```

**Response Processing:**
- `apps/web/lib/responses.ts` — The `convertResponseValue` switch statement must handle new types. If new types return standard string responses, the `default` branch suffices. If they return arrays or objects, explicit `case` branches are required.

**Single Response Card Rendering:**
- `apps/web/modules/analysis/components/SingleResponseCard/components/RenderResponse.tsx` — Must render responses for new types in the single-response detail view.
- `apps/web/modules/analysis/components/SingleResponseCard/components/SingleResponseCardBody.tsx` — Must map new types to appropriate display components.

**Survey Renderer Conditional:**
- `packages/surveys/src/components/general/element-conditional.tsx` — The central switch statement (15 current cases) that routes element rendering. Two new cases must be added for TypeA and TypeB.

**Client-Side Validation:**
- `packages/surveys/src/lib/validation/evaluator.ts` — The `evaluateElement` function checks element types for special validation (Address, ContactInfo, CTA, Ranking, Matrix, OpenText). New types may need explicit handling depending on their response data shape.

### 0.4.3 Cross-Cutting Concerns

- **Internationalization:** All user-facing strings for new element types (labels, descriptions, placeholders) must use the `t()` translation function and be added to i18n locale files under `apps/web/locales/`.
- **Backward Compatibility:** The v1 API must accept old `TSurveyQuestionTypeEnum` values. Both `ZSurveyQuestion` and `ZSurveyElement` unions must recognize the new types.
- **Follow-ups:** `packages/types/surveys/types.ts` lines 1813–1864 check element types to determine valid "to" fields for follow-up emails. If new types capture email-like data, they must be included.
- **Quota Evaluation:** `apps/web/modules/ee/quotas/lib/evaluation-service.test.ts` references element types for quota logic evaluation — ensure new types don't break quota computations.


## 0.5 Technical Implementation

### 0.5.1 File-by-File Execution Plan

Every file listed below MUST be created or modified. Files are grouped by dependency order — Group 1 must be completed before Groups 2–4.

**Group 1 — Core Type System (Foundation)**

- **MODIFY: `packages/types/surveys/constants.ts`** — Add two new members to `TSurveyElementTypeEnum` after `ContactInfo` (line 17). This is the absolute first file to change as everything else derives from it.
- **MODIFY: `packages/types/surveys/elements.ts`** — Create two new Zod schemas (`ZSurveyTypeAElement`, `ZSurveyTypeBElement`) extending `ZSurveyElementBase` with type-specific fields. Add both to the `ZSurveyElement` union (line 354). Export the new schemas and inferred TypeScript types.
- **MODIFY: `packages/types/surveys/types.ts`** — Multi-point modification:
  - Add members to deprecated `TSurveyQuestionTypeEnum` (line 91)
  - Create deprecated `ZSurveyTypeAQuestion` and `ZSurveyTypeBQuestion` schemas
  - Add to `ZSurveyQuestion` union (line 703)
  - Add to `ZSurveyQuestionType` enum (line 738)
  - Add `case` branches to `isInvalidOperatorsForQuestionType` (line 1877)
  - Add `case` branches to `isInvalidOperatorsForElementType` (line 2903)
  - Add type-specific validation branches in the block element validation section (line 1307)
  - Create `ZSurveyElementSummaryTypeA` and `ZSurveyElementSummaryTypeB` schemas
  - Add to `ZSurveyElementSummary` union (line 4204)
- **MODIFY: `packages/types/surveys/validation-rules.ts`** — Add entries to `APPLICABLE_RULES` mapping (line 289) if the new types support field-level validation rules.

**Group 2 — Survey Editor (Authoring Experience)**

- **MODIFY: `apps/web/modules/survey/lib/elements.tsx`** — Add two new entries to the `getElementTypes()` array, each with `id`, `label`, `description`, `icon`, and `preset` properties. Choose appropriate Lucide icons and translation keys.
- **CREATE: `apps/web/modules/survey/editor/components/type-a-element-form.tsx`** — Editor form component for TypeA. Follow the pattern established by `rating-element-form.tsx` or `consent-element-form.tsx`. Must accept `localSurvey`, `element`, `blockIndex`, `elementIndex`, `updateElement` props.
- **CREATE: `apps/web/modules/survey/editor/components/type-b-element-form.tsx`** — Editor form component for TypeB, same pattern as TypeA.
- **MODIFY: `apps/web/modules/survey/editor/lib/logic-rule-engine.ts`** — Add operator definitions for both new types in the `element` section of the rules object. Follow the existing pattern for simple types (e.g., `isSubmitted`, `isSkipped` for types without complex operand comparisons).
- **MODIFY: `apps/web/modules/survey/editor/lib/logic-rule-engine.test.ts`** — Add test cases verifying operator rules for new types.
- **MODIFY: `apps/web/modules/survey/components/element-form-input/index.tsx`** — Add routing cases for new element types to render in the form input wrapper.

**Group 3 — Survey Renderer (Respondent Experience)**

- **CREATE: `packages/surveys/src/components/elements/type-a-element.tsx`** — Preact-compatible renderer component for TypeA. Follow the pattern of existing elements (accept `element`, `value`, `onChange`, `languageCode`, `ttc`, `setTtc`, `errorMessage` props).
- **CREATE: `packages/surveys/src/components/elements/type-b-element.tsx`** — Preact-compatible renderer component for TypeB.
- **MODIFY: `packages/surveys/src/components/general/element-conditional.tsx`** — Add two `case TSurveyElementTypeEnum.TypeA:` and `case TSurveyElementTypeEnum.TypeB:` branches to the rendering switch statement, importing and rendering the new components.
- **CREATE: `packages/survey-ui/src/elements/type-a-element.tsx`** — React survey-ui component following `.cursor/commands/create-question.md` scaffold pattern with `ElementHeader`, `useTextDirection`, and `errorMessage` display.
- **CREATE: `packages/survey-ui/src/elements/type-b-element.tsx`** — React survey-ui component.
- **CREATE: `packages/survey-ui/src/elements/type-a-element.stories.tsx`** — Storybook story per the documented scaffold.
- **CREATE: `packages/survey-ui/src/elements/type-b-element.stories.tsx`** — Storybook story.
- **MODIFY: `packages/surveys/src/lib/validation/evaluator.ts`** — Add validation branches for new types if they have custom response shapes.
- **MODIFY: `packages/surveys/src/lib/validation/evaluator.test.ts`** — Add test cases for new type validation.

**Group 4 — Analytics, Integrations, and Response Handling**

- **MODIFY: `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/SummaryList.tsx`** — Add conditional rendering branches for `TSurveyElementTypeEnum.TypeA` and `TSurveyElementTypeEnum.TypeB`.
- **CREATE: Summary display components** for each type (file paths depend on response data shape — could be shared with existing patterns like `OpenText` for text responses or `MultipleChoice` for selection responses).
- **MODIFY: `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/lib/surveySummary.ts`** — Add computation logic for building summary data for new types.
- **MODIFY: `apps/web/app/(app)/environments/[environmentId]/workspace/integrations/notion/constants.ts`** — Add `TYPE_MAPPING` entries for both new types.
- **MODIFY: `apps/web/lib/responses.ts`** — Add case branches to `convertResponseValue` if new types have non-default response shapes.
- **MODIFY: `apps/web/modules/analysis/components/SingleResponseCard/components/RenderResponse.tsx`** — Add rendering branches for new types.
- **MODIFY: `apps/web/modules/analysis/components/SingleResponseCard/components/SingleResponseCardBody.tsx`** — Add type mapping branches.

### 0.5.2 Implementation Approach per File

The implementation follows a strict dependency chain:

- **Establish type-system foundation** by modifying `constants.ts` → `elements.ts` → `types.ts` in the `packages/types/surveys/` directory. These files form the single source of truth consumed by all downstream code.
- **Integrate with the survey editor** by registering element presets in `elements.tsx`, creating form components, and wiring logic operators. The editor dynamically reads from `getElementTypes()`, so registration is the critical step.
- **Enable respondent-facing rendering** by creating renderer components in both `packages/surveys/` (Preact) and `packages/survey-ui/` (React), and wiring them into the conditional rendering switch in `element-conditional.tsx`.
- **Ensure analytics completeness** by adding summary schemas, computation logic, and display components. This enables admins to view aggregated response data for the new types.
- **Maintain integration parity** by updating Notion type mappings, response conversion, and pipeline handlers.

### 0.5.3 User Interface Design

The survey editor UI requires no structural changes — element types are dynamically registered through the `getElementTypes()` array in `apps/web/modules/survey/lib/elements.tsx`. The key UI deliverables are:

- **Element picker cards:** Each new type appears as a selectable card in the "Add Block" collapsible panel, showing an icon, label, and description. The icon should be selected from the `lucide-react` library to maintain visual consistency.
- **Editor form panels:** Each new type gets a dedicated form component rendered when the element is selected in the editor. These forms must support headline editing, subheader, image/video attachment, required toggle, and any type-specific configuration fields.
- **Respondent-facing elements:** The renderer components must support text direction detection (`useTextDirection`), error message display, TTC (Time to Complete) tracking, and accessibility standards (semantic HTML, keyboard navigation).
- **Summary visualizations:** Summary display components should follow existing patterns — text-response types use the OpenText sample list pattern; selection types use the MultipleChoice bar chart pattern; numeric types use the Rating/NPS distribution pattern.


## 0.6 Scope Boundaries

### 0.6.1 Exhaustively In Scope

**Type system files (must change):**
- `packages/types/surveys/constants.ts`
- `packages/types/surveys/elements.ts`
- `packages/types/surveys/types.ts`
- `packages/types/surveys/validation-rules.ts`

**Survey editor files:**
- `apps/web/modules/survey/lib/elements.tsx`
- `apps/web/modules/survey/editor/components/type-a-element-form.tsx` (CREATE)
- `apps/web/modules/survey/editor/components/type-b-element-form.tsx` (CREATE)
- `apps/web/modules/survey/editor/lib/logic-rule-engine.ts`
- `apps/web/modules/survey/editor/lib/logic-rule-engine.test.ts`
- `apps/web/modules/survey/components/element-form-input/**/*`

**Survey renderer files:**
- `packages/surveys/src/components/elements/type-a-element.tsx` (CREATE)
- `packages/surveys/src/components/elements/type-b-element.tsx` (CREATE)
- `packages/surveys/src/components/general/element-conditional.tsx`
- `packages/surveys/src/lib/validation/evaluator.ts`
- `packages/surveys/src/lib/validation/evaluator.test.ts`
- `packages/survey-ui/src/elements/type-a-element.tsx` (CREATE)
- `packages/survey-ui/src/elements/type-b-element.tsx` (CREATE)
- `packages/survey-ui/src/elements/type-a-element.stories.tsx` (CREATE)
- `packages/survey-ui/src/elements/type-b-element.stories.tsx` (CREATE)

**Analytics and summary files:**
- `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/SummaryList.tsx`
- `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/lib/surveySummary.ts`
- `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/lib/utils.ts`
- Summary display components for new types (CREATE)

**Integration and response files:**
- `apps/web/app/(app)/environments/[environmentId]/workspace/integrations/notion/constants.ts`
- `apps/web/lib/responses.ts`
- `apps/web/modules/analysis/components/SingleResponseCard/components/RenderResponse.tsx`
- `apps/web/modules/analysis/components/SingleResponseCard/components/SingleResponseCardBody.tsx`
- `apps/web/app/api/(internal)/pipeline/lib/handleIntegrations.ts`

**Test and mock files:**
- `apps/web/lib/survey/__mock__/survey.mock.ts`
- `apps/web/modules/survey/editor/lib/survey.test.ts`
- `apps/web/modules/survey/components/element-form-input/utils.test.ts`
- `packages/surveys/src/lib/validation/validators.test.ts`
- `packages/surveys/src/lib/logic.test.ts`

**i18n locale files:**
- `apps/web/locales/en-US/*.json` — Add translation keys for element labels and descriptions
- Corresponding locale files for all 13 other supported languages

### 0.6.2 Explicitly Out of Scope

- **Database migrations:** The survey JSON column schema does not need migration. Element types are string identifiers within JSON, not Prisma-level enums.
- **Prisma schema changes:** `packages/database/schema.prisma` requires no changes.
- **API v2 OpenAPI spec:** `openapi.yml` does not need modification unless the new types introduce novel request/response schemas. Survey payloads are generic JSON.
- **Existing element types:** No modifications to the 15 existing element types (FileUpload, OpenText, etc.).
- **Performance optimization:** No caching, indexing, or query optimization work beyond basic feature implementation.
- **Mobile-specific rendering:** The survey renderer is responsive via CSS; no dedicated mobile component work is in scope.
- **Refactoring of deprecated `ZSurveyQuestion` code:** Deprecated v1 API compatibility code must remain; refactoring is explicitly out of scope.
- **CI/CD pipeline changes:** No changes to `.github/workflows/`, `turbo.json`, or build configurations.
- **Docker or Helm chart changes:** No infrastructure modifications in `docker/`, `charts/`, or `docker-compose*.yml`.
- **License or billing gating:** New element types are Core Platform features, not Enterprise-gated.
- **Unrelated features or modules:** Authentication, organization management, billing, SSO, contact management, and all other modules outside the survey type system.


## 0.7 Rules for Feature Addition

### 0.7.1 Enum Registration Convention

Every new element type MUST be registered in `TSurveyElementTypeEnum` with a `camelCase` string value matching the enum member name (lowercased first letter). This convention is enforced by all downstream code that performs string-literal comparisons.

```ts
TypeA = "typeA",
```

### 0.7.2 Dual-Schema Requirement (Element + Deprecated Question)

For v1 API backward compatibility, every new element type requires TWO Zod schemas:
- A **primary element schema** in `packages/types/surveys/elements.ts` extending `ZSurveyElementBase`
- A **deprecated question schema** in `packages/types/surveys/types.ts` extending `ZSurveyQuestionBase`, annotated with `@deprecated` JSDoc comments

Both schemas must be added to their respective union types (`ZSurveyElement` and `ZSurveyQuestion`).

### 0.7.3 Logic Operator Coverage

The `isInvalidOperatorsForQuestionType` and `isInvalidOperatorsForElementType` functions use exhaustive `switch` statements with a `default: return true` (invalid) fallback. If a new type is NOT added as an explicit `case`, all logic conditions referencing that type will silently fail validation. This is a **critical requirement** — both switch statements MUST include explicit case branches.

### 0.7.4 Summary Schema Registration

Each new type MUST have a corresponding `ZSurveyElementSummaryXxx` schema registered in the `ZSurveyElementSummary` union. Without this, the analytics summary computation will skip responses for the new types.

### 0.7.5 Storybook Documentation

Per `.cursor/commands/create-question.md`, every new survey-ui element component MUST have an accompanying `.stories.tsx` file with baseline stories demonstrating default, required, error, and RTL states.

### 0.7.6 Translation Key Convention

All user-facing strings (element labels, descriptions, placeholders, validation messages) MUST use i18next translation keys via the `t()` function. Keys should follow the existing namespace pattern:
- Element type label: `templates.type_a`
- Element type description: `templates.type_a_description`
- Lower/upper labels: `templates.type_a_lower_label` / `templates.type_a_upper_label`

### 0.7.7 ID Generation

All element IDs, choice IDs, and block IDs must use `createId()` from `@paralleldrive/cuid2`. Never use UUIDs, sequential integers, or custom ID formats.

### 0.7.8 Sprint Dependency Contract

This Sprint 1 output forms the foundation for all subsequent sprints. The type definitions created here will be consumed by logic operator extensions, webhook payload serializers, export formatters, and API endpoint handlers in future sprints. The type definitions must therefore be:
- **Complete:** All fields, validation rules, and constraints defined
- **Stable:** No breaking changes expected from future sprints
- **Documented:** JSDoc comments on all exported types and schemas


## 0.8 References

### 0.8.1 Codebase Files and Folders Searched

The following files and directories were directly inspected to derive the conclusions in this Agent Action Plan:

**Root-level configuration:**
- `/` (repository root) — folder structure, `package.json`, `pnpm-workspace.yaml`, `turbo.json`

**Type system (`packages/types/`):**
- `packages/types/package.json` — Dependencies and version information
- `packages/types/surveys/constants.ts` — `TSurveyElementTypeEnum` definition (18 lines)
- `packages/types/surveys/elements.ts` — All 15 Zod element schemas and `ZSurveyElement` union (376 lines)
- `packages/types/surveys/types.ts` — Deprecated question types, survey schema, logic validators, summary schemas (4307 lines)
- `packages/types/surveys/logic.ts` — Logic operators, condition schemas, connector types (247 lines)
- `packages/types/surveys/blocks.ts` — Block definition, block logic actions (147 lines)
- `packages/types/surveys/validation-rules.ts` — Validation rule types and `APPLICABLE_RULES` (345 lines)
- `packages/types/surveys/elements-validation.ts` — Element label validation
- `packages/types/surveys/validation.ts` — Shared validation utilities
- `packages/types/formbricks-surveys.ts` — Embed surface configuration

**Survey editor (`apps/web/modules/survey/`):**
- `apps/web/modules/survey/lib/elements.tsx` — Element type registry, icons, presets, defaults
- `apps/web/modules/survey/editor/components/` — All editor form components (50+ files listed)
- `apps/web/modules/survey/editor/components/add-element-button.tsx` — Element addition UI
- `apps/web/modules/survey/editor/components/elements-view.tsx` — Elements view orchestrator
- `apps/web/modules/survey/editor/lib/logic-rule-engine.ts` — Logic operator engine (17 element type references)
- `apps/web/modules/survey/editor/lib/logic-rule-engine.test.ts` — Logic rule tests
- `apps/web/modules/survey/components/element-form-input/index.tsx` — Form input routing

**Survey renderer (`packages/surveys/`, `packages/survey-ui/`):**
- `packages/surveys/src/components/general/element-conditional.tsx` — Conditional rendering switch (15 cases)
- `packages/surveys/src/components/elements/` — All 15 element renderer components
- `packages/surveys/src/lib/validation/evaluator.ts` — Client-side validation evaluator
- `packages/survey-ui/src/elements/` — All 15 survey-ui element components

**Analytics and integrations (`apps/web/`):**
- `apps/web/app/(app)/environments/[environmentId]/surveys/[surveyId]/(analysis)/summary/components/SummaryList.tsx` — Summary renderer (15 type branches)
- `apps/web/app/(app)/environments/[environmentId]/workspace/integrations/notion/constants.ts` — Notion type mapping
- `apps/web/lib/responses.ts` — Response value conversion
- `apps/web/modules/api/v2/lib/element.ts` — API v2 element validation
- `apps/web/app/api/(internal)/pipeline/lib/handleIntegrations.ts` — Integration pipeline
- `apps/web/modules/analysis/components/SingleResponseCard/components/RenderResponse.tsx` — Single response rendering
- `apps/web/modules/analysis/components/SingleResponseCard/components/SingleResponseCardBody.tsx` — Response card body
- `apps/web/app/lib/survey-block-builder.ts` — Survey block builder utilities
- `apps/web/app/lib/templates.ts` — Survey template definitions

**Scaffold documentation:**
- `.cursor/commands/create-question.md` — Scaffold for new survey question components with Storybook guidelines

**Cross-references via `grep`:**
- All files matching `TSurveyElementTypeEnum` (40+ files across the monorepo)
- All files matching `TSurveyQuestionTypeEnum` (23 files)

### 0.8.2 Attachments

No attachments were provided for this project.

### 0.8.3 Tech Spec Sections Referenced

- **Section 2.1 Feature Catalog** — Confirmed the Survey Engine (F-001) supports 15 distinct question types, validated the architecture of the type system, and confirmed the core platform vs. enterprise feature boundary.

### 0.8.4 External References

No external URLs or Figma screens were provided or referenced for this task. All implementation guidance is derived from the existing codebase patterns and the `.cursor/commands/create-question.md` scaffold documentation.


