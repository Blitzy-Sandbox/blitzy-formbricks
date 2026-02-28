# Technical Specification

# 0. Agent Action Plan

## 0.1 Intent Clarification

### 0.1.1 Core Documentation Objective

Based on the provided requirements, the Blitzy platform understands that the documentation objective is to **create and maintain a complete, production-grade documentation suite for a functionally equivalent open-source form and survey platform** generated through the Blitzy Autonomous Gap Closure process against Formbricks (OSS TARGET, v3.7.0) and Typeform (COMMERCIAL SOURCE).

**Request Category:** Create new documentation + Update existing documentation

**Documentation Types:**
- API Reference Documentation (OpenAPI 3.0 v1, OpenAPI 3.1.0 v2)
- User Guides (XM &amp; Surveys, question types, distribution channels)
- Technical Specifications (architecture, database model, tenant separation)
- Self-Hosting Guides (Docker, Kubernetes, one-click setup, monitoring)
- Developer Documentation (local setup, standards, contribution guidelines)
- Integration Guides (Slack, Google Sheets, Notion, Airtable, Zapier, n8n, webhooks)
- Enterprise Feature Documentation (SSO, audit logging, team access, billing)
- Best Practice Tutorials (PMF surveys, feedback boxes, interview prompts, etc.)
- README Files (root README, docs README, Docker README)

**Documentation Requirements with Enhanced Clarity:**
- The existing Formbricks documentation suite (190 MDX files across 6 navigation tabs) must be fully preserved, updated, and extended to cover all 26 features (16 core + 10 enterprise)
- All documentation must follow the established Mintlify-based infrastructure using `docs.json` configuration, MDX format with required frontmatter (title, description, icon), and Mintlify component syntax
- The API reference documentation must remain synchronized with OpenAPI specifications: v1 at `docs/api-reference/openapi.json` (OpenAPI 3.0) and v2 at `docs/api-v2-reference/openapi.yml` (OpenAPI 3.1.0)
- Documentation must cover all 4 distribution channels (in-app, website, link, email), 15 question types, 6+ native integrations, and 7+ deployment methods
- The 14-locale internationalization system must be documented comprehensively
- Enterprise features (SSO SAML/OIDC, audit logging, team access, billing, quotas) require dedicated documentation with license-gate notation

**Inferred Documentation Needs:**
- Based on code analysis: The `apps/web/modules/` directory contains 16 feature modules, several of which have advanced capabilities (e.g., `ee/` enterprise modules for billing, audit logs, role management, teams, SAML SSO, OIDC SSO) that require thorough user-facing documentation
- Based on structure: The API v2 documentation currently consists of a single introduction page (`docs/api-v2-reference/introduction.mdx`) while the OpenAPI specification covers 13+ domain modules — requiring expanded API v2 reference documentation
- Based on dependencies: The OAuth integration flow between Formbricks and 4 native platforms (Slack, Google Sheets, Notion, Airtable) requires consolidated setup guides for both cloud and self-hosted deployments
- Based on user journey: New users require a progressive documentation path from introduction → self-hosting setup → first survey creation → SDK integration → analytics review → integration configuration

### 0.1.2 Special Instructions and Constraints

**Critical Directives:**
- Follow the existing Mintlify documentation style as established in `docs/docs.json` and `AGENTS.md`
- All MDX files must include frontmatter with `title`, `description`, and `icon` fields
- No H1 headings — Mintlify generates these automatically from the frontmatter title
- Use Camel Case for all headings
- Employ Mintlify components for callouts, step sequences, and card layouts (`<Note>`, `<Warning>`, `<Steps>`, `<Card>`, `<CardGroup>`)
- Enterprise features must be annotated with clear enterprise-license blocks using `<Note>` components
- All images stored in `docs/images/` subdirectories with descriptive alt text and `.webp` format
- Internal navigation uses relative paths without file extensions

**Documentation Standards (from `AGENTS.md`):**
- Use Mintlify components for steps and callouts
- Include frontmatter with title, description, and icon metadata
- Maintain consistent heading hierarchy starting at H2 (`##`)
- Code snippets must include language identifiers for syntax highlighting
- Embed interactive survey previews using iframe components where applicable

**Style Preferences:**
- Clear, concise technical language accessible to developers and product managers
- Progressive disclosure: simple concepts first, advanced configurations later
- Practical code examples with every API endpoint and SDK integration method
- Mermaid diagrams for architecture and data flow visualizations
- Tables for parameter descriptions, environment variables, and configuration options

### 0.1.3 Technical Interpretation

These documentation requirements translate to the following technical documentation strategy:

- To document the complete survey engine, we will update and extend the 85 MDX files in `docs/xm-and-surveys/` covering survey general features, link surveys, website/app surveys, question types, core features (integrations, styling, user management), and best practices
- To document the REST API, we will maintain and extend the 43 API v1 MDX files in `docs/api-reference/` and expand the single API v2 introduction page in `docs/api-v2-reference/` to cover all 13+ domain modules
- To document self-hosting, we will update and extend the 36 MDX files in `docs/self-hosting/` covering setup methods (Docker, Kubernetes, one-click, cluster), configuration (env vars, auth/SSO, integrations, SMTP, SSL, domain, file uploads), and advanced features (enterprise, migration, rate limiting, license)
- To document development practices, we will update the 22 MDX files in `docs/development/` covering local setup (Mac, Linux, Windows, Codespaces, Gitpod), standards (organization, practices, QA, technical), technical handbook (database model, tenant separation), and contribution guidelines
- To document the platform overview, we will update the 3 MDX files in `docs/overview/` (introduction, what-is-formbricks, open-source)
- To maintain navigation integrity, we will update `docs/docs.json` to register any new pages, adjust tab configurations, and ensure all redirect rules remain valid
- To support visual documentation, we will create and maintain the 393+ image assets in `docs/images/` organized by documentation section

## 0.2 Documentation Discovery and Analysis

### 0.2.1 Existing Documentation Infrastructure Assessment

Repository analysis reveals a **mature, Mintlify-powered documentation workspace** with comprehensive coverage across 6 navigation tabs and 190 MDX content files, backed by 393 image assets and 2 OpenAPI specifications.

**Documentation Framework:**
- **Engine:** Mintlify (SaaS documentation platform)
- **CLI Package:** `mintlify` v4.2.378 (npm), also available as `@mintlify/cli` v4.0.712
- **Configuration File:** `docs/docs.json` (760 lines, migrated from legacy `mint.json` format)
- **Content Format:** MDX (Markdown + JSX) with frontmatter metadata
- **Theme:** Mintlify `mint` theme with brand teal (#00C4B8) color scheme
- **Analytics:** PostHog EU integration (project key embedded in docs.json)
- **Node.js Requirement:** v20.17.0+ (LTS versions recommended for Mintlify CLI)

**Documentation Generator Configuration:**
- Location: `docs/docs.json`
- Six navigation tabs: Overview, XM &amp; Surveys, Self Hosting, Development, API v1 Reference, API v2 Reference (Beta)
- Navbar with Support link (GitHub Discussions) and "Go to app" CTA button
- Footer with GitHub, LinkedIn, and X social links
- Error handling: 404 redirects instead of static error pages
- Extensive redirect rules for URL reorganization (legacy path → modern path mappings)

**API Documentation Tools:**
- OpenAPI 3.0 (JSON): `docs/api-reference/openapi.json` — v1.0.0 client and management API
- OpenAPI 3.1.0 (YAML): `docs/api-v2-reference/openapi.yml` — v2.0.0 management API with `x-api-key` auth
- Root-level OpenAPI 3.1.0 (YAML): `openapi.yml` — simplified responses endpoint specification
- Runtime OpenAPI generation: `apps/web/modules/api/v2/openapi-document.ts` using `zod-openapi` library

**Diagram Tools:** Mermaid diagrams embedded in MDX content blocks

**Storybook Documentation:** `apps/storybook` workspace running Storybook 10.1.11 for component-level visual documentation (separate from Mintlify docs)

### 0.2.2 Documentation File Distribution

| Section | Path | MDX Files | Description |
|---------|------|-----------|-------------|
| Overview | `docs/overview/` | 3 | Introduction, What is Formbricks, Open Source |
| XM &amp; Surveys | `docs/xm-and-surveys/` | 85 | Survey features, question types, integrations, best practices |
| Self Hosting | `docs/self-hosting/` | 36 | Setup, configuration, auth/SSO, advanced enterprise |
| Development | `docs/development/` | 22 | Local setup, standards, technical handbook, contributions |
| API v1 Reference | `docs/api-reference/` | 43 | REST API, client API, management API endpoint pages |
| API v2 Reference | `docs/api-v2-reference/` | 1 | Introduction page only (Beta) |
| **Total** | `docs/` | **190** | All documentation content |

**Image Assets:**
- Total image files: 393 (predominantly `.webp` format)
- Organized by section: `docs/images/api-reference/`, `docs/images/self-hosting/`, `docs/images/xm-and-surveys/`, `docs/images/development/`
- Brand assets: `docs/images/favicon.svg`, `docs/images/logo-dark.svg`, `docs/images/logo-light.svg`

**Navigation Integrity:** All 150 page references in `docs.json` navigation map to existing MDX files — zero broken navigation links detected.

### 0.2.3 Repository Code Analysis for Documentation

**Search Patterns Used:**
- `find docs/ -name "*.mdx"` — located all 190 documentation content files
- `docs/docs.json` navigation analysis — cross-referenced 150 page references against filesystem
- `AGENTS.md` lines 1-80 — extracted documentation standards and coding conventions
- `apps/web/modules/` structure — identified 16 feature modules requiring documentation coverage
- `packages/` directory — catalogued 14 shared packages with documentation implications

**Key Directories Examined:**

| Directory | Modules/Files | Documentation Relevance |
|-----------|---------------|------------------------|
| `apps/web/modules/survey/` | Survey editor, components, actions | Core survey feature documentation |
| `apps/web/modules/api/` | API v2 routes, middleware, OpenAPI | API reference documentation |
| `apps/web/modules/auth/` | Authentication, signup, password | Auth setup and configuration docs |
| `apps/web/modules/integrations/` | Webhooks, native integrations | Integration guides |
| `apps/web/modules/ee/` | Enterprise: billing, audit, SSO, teams | Enterprise feature documentation |
| `apps/web/modules/analysis/` | Response analysis, summaries | Analytics documentation |
| `apps/web/modules/organization/` | Organization, API keys, billing | Admin and management docs |
| `apps/web/modules/projects/` | Project settings, teams | Project management docs |
| `packages/surveys/` | Preact/React survey renderer | SDK and embedding docs |
| `packages/js-core/` | 7KB browser SDK | SDK integration docs |
| `packages/database/` | Prisma schema, 32 models | Database model documentation |
| `packages/types/` | Zod schemas, shared types | API contract documentation |

**Related Documentation Found:**
- `AGENTS.md` — Repository-wide coding and documentation guidelines
- `README.md` — Root marketing README with feature overview
- `CONTRIBUTING.md` — Community contribution guidelines
- `docs/README.md` — Mintlify local dev instructions
- `docker/README.md` — Docker deployment instructions
- `docs/development/standards/practices/documentation.mdx` — Internal documentation standards page

### 0.2.4 Web Search Research Conducted

- **Mintlify CLI versions:** Current stable is `mintlify` v4.2.378 on npm (published continuously), `@mintlify/cli` v4.0.712. Requires Node.js v20.17.0+ (LTS recommended). Configuration now uses `docs.json` (migrated from legacy `mint.json` via `mintlify upgrade` command).
- **Formbricks documentation standards:** Formbricks mandates `.mdx` file extensions, frontmatter with title/description/icon, no H1 headings, Camel Case headings, Mintlify components for callouts (`<Note>`), and images stored in `/images` subdirectories with descriptive alt text.
- **Mintlify CLI capabilities:** Local preview (`mintlify dev`), broken link checking (`mint check-links`), accessibility audits (`mint a11y` for contrast ratios and alt text), OpenAPI validation (`mint openapi-check`), strict build validation (`mint validate --strict` for CI/CD), and file renaming with link updates (`mint rename`).
- **Documentation deployment:** Mintlify auto-deploys on push to default branch via GitHub App integration. PostHog EU analytics are integrated for visitor behavior tracking.

## 0.3 Documentation Scope Analysis

### 0.3.1 Code-to-Documentation Mapping

**Feature Modules Requiring Documentation:**

- **Module: `apps/web/modules/survey/`**
  - Public APIs: Survey CRUD, editor components, question type configuration, conditional logic, template library
  - Current documentation: 85 MDX files in `docs/xm-and-surveys/` — covers general features (16 pages), link surveys (12 pages), website/app surveys (8 pages), question types (15 pages)
  - Documentation needed: Ensure all 15 question types are documented, update conditional logic branching docs, document auto-save behavior

- **Module: `apps/web/modules/api/` (API v2)**
  - Endpoints: 13+ domain modules (health, roles, me, responses, contacts, bulk contacts, contact attribute keys, surveys, survey contact links, webhooks, teams, project teams, users)
  - Current documentation: 1 MDX file (`docs/api-v2-reference/introduction.mdx`) — introduction page only
  - Documentation needed: Complete API v2 reference pages for all domain modules, endpoint-level documentation with request/response examples, authentication guide

- **Module: `apps/web/modules/auth/`**
  - Public APIs: Login, signup, password reset, email verification, OAuth callbacks, CAPTCHA
  - Current documentation: `docs/self-hosting/auth-behavior.mdx`, `docs/self-hosting/configuration/auth-sso/` (4 pages)
  - Documentation needed: Update authentication behavior docs with all 6+ identity providers, document CAPTCHA configuration (Turnstile/reCAPTCHA)

- **Module: `apps/web/modules/integrations/`**
  - Components: Webhook CRUD, Standard Webhooks signing, native integration dispatch
  - Current documentation: `docs/xm-and-surveys/core-features/integrations/` (12 pages), `docs/self-hosting/configuration/integrations/` (7 pages)
  - Documentation needed: Update webhook documentation with Standard Webhooks compliance details, document Discord blocking, ensure all integration setup guides are current

- **Module: `apps/web/modules/ee/` (Enterprise)**
  - Sub-modules: billing, audit-logs, role-management, teams, saml-sso, oidc-sso, contacts, insights, multi-language, follow-ups, whitelabel
  - Current documentation: `docs/self-hosting/advanced/enterprise-features/` (8 pages), `docs/self-hosting/advanced/license.mdx`, `docs/self-hosting/advanced/license-activation.mdx`
  - Documentation needed: Ensure all 10 enterprise features (F-017 through F-026) have dedicated documentation, update billing docs with Stripe plan tiers

- **Module: `apps/web/modules/analysis/`**
  - Public APIs: Response summaries, aggregation dashboards, shareable analytics
  - Current documentation: Limited coverage within survey feature pages
  - Documentation needed: Dedicated analytics documentation for response dashboard, insight generation, CSAT scoring, shareable links

- **Module: `apps/web/modules/organization/`**
  - Public APIs: Organization CRUD, API key management, member invitation, billing portal
  - Current documentation: `docs/xm-and-surveys/core-features/user-management/` (5 pages)
  - Documentation needed: Update user management docs with bulk invitation, API key permission scoping, multi-org enterprise capability

- **Module: `apps/web/modules/setup/`**
  - Public APIs: Fresh instance detection, onboarding wizard
  - Current documentation: Partially covered in self-hosting setup guides
  - Documentation needed: Document the complete onboarding flow for fresh instances

**SDK and Package Documentation:**

| Package | Path | Current Docs | Status |
|---------|------|-------------|--------|
| `packages/js-core` | Browser SDK (7KB) | `docs/xm-and-surveys/surveys/website-app-surveys/quickstart.mdx` | Exists — update for SDK API changes |
| `packages/surveys` | Preact/React renderer | Covered within survey embedding docs | Exists — verify accuracy |
| `packages/database` | Prisma 6.14.0 schema | `docs/development/technical-handbook/database-model.mdx` | Exists — update for 32 models |
| `packages/types` | Zod validation schemas | Documented via OpenAPI specs | Exists — sync with API docs |

**Configuration Options Requiring Documentation:**

| Config File | Options Documented | Missing Documentation |
|-------------|-------------------|----------------------|
| `.env.example` | 75+ environment variables | All documented in `docs/self-hosting/configuration/environment-variables.mdx` |
| `docs/docs.json` | Mintlify navigation config | Documented in `docs/README.md` for contributors |
| `docker/docker-compose.yml` | Docker deployment | Documented in `docs/self-hosting/setup/docker.mdx` |

### 0.3.2 Documentation Gap Analysis

Given the requirements and repository analysis, documentation gaps include:

**Undocumented or Under-documented Areas:**

| Gap Category | Specific Gap | Severity | Affected Files |
|-------------|-------------|----------|----------------|
| API v2 Reference | Only 1 introduction page exists for 13+ domain modules | High | `docs/api-v2-reference/` |
| Webhook Standards | Standard Webhooks compliance, signing verification, secret format not documented | Medium | `docs/xm-and-surveys/core-features/integrations/webhooks.mdx` |
| Rate Limiting | Self-hosting rate limit configuration guide incomplete | Medium | `docs/self-hosting/advanced/rate-limiting.mdx` |
| Database Model | 32 Prisma models, 21 enums need comprehensive reference | Medium | `docs/development/technical-handbook/database-model.mdx` |
| Environment Variables | New variables for Stripe, CAPTCHA, observability need documentation | Medium | `docs/self-hosting/configuration/environment-variables.mdx` |
| CSAT/Analytics | CSAT scoring methodology, insight generation caps, shareable dashboards | Medium | Analytics section under survey features |
| Monitoring | OpenTelemetry, Prometheus, Sentry setup for self-hosted | Medium | `docs/self-hosting/setup/monitoring.mdx` |
| Email Templates | Transactional email template customization | Low | `docs/xm-and-surveys/core-features/email-customization.mdx` |
| SDK Framework Guides | Framework-specific integration guides need version updates | Low | `docs/xm-and-surveys/surveys/website-app-surveys/framework-guides.mdx` |

**Feature-to-Documentation Coverage Matrix:**

| Feature ID | Feature Name | Docs Exist | Coverage Level |
|-----------|-------------|------------|----------------|
| F-001 | Survey Creation &amp; Editor | Yes | High |
| F-002 | Multi-Channel Distribution | Yes | High |
| F-003 | User Targeting &amp; Segmentation | Yes | Medium |
| F-004 | Response Collection | Yes | Medium |
| F-005 | Analytics &amp; Insights | Partial | Low |
| F-006 | REST API v1/v2 | v1: High, v2: Low | Mixed |
| F-007 | Authentication | Yes | Medium |
| F-008 | Organization Management | Yes | Medium |
| F-009 | Project Management | Partial | Low |
| F-010 | Webhook Integrations | Yes | Medium |
| F-011 | Native Integrations | Yes | High |
| F-012 | File Storage | Partial | Low |
| F-013 | Internationalization | Yes | Medium |
| F-014 | Rate Limiting | Yes | Medium |
| F-015 | Email Notifications | Yes | Medium |
| F-016 | Setup &amp; Onboarding | Yes | Medium |
| F-017 | SSO (SAML/OIDC) | Yes | High |
| F-018 | Contact Management | Yes | Medium |
| F-019 | Two-Factor Auth | Yes | Medium |
| F-020 | Audit Logging | Yes | Medium |
| F-021 | Billing &amp; Subscription | Partial | Low |
| F-022 | Role Management | Yes | Medium |
| F-023 | Multi-Language Surveys | Yes | High |
| F-024 | Email Follow-ups | Yes | Medium |
| F-025 | Quotas &amp; Limits | Partial | Low |
| F-026 | License Management | Yes | Medium |

## 0.4 Documentation Implementation Design

### 0.4.1 Documentation Structure Planning

The documentation hierarchy preserves the established Mintlify structure while addressing identified gaps:

```
docs/
├── docs.json                              (Mintlify navigation config — UPDATE)
├── README.md                              (Contributor instructions — UPDATE)
├── overview/
│   ├── introduction.mdx                   (Welcome page — UPDATE)
│   ├── what-is-formbricks.mdx             (Platform overview — UPDATE)
│   └── open-source.mdx                    (Open source details — UPDATE)
├── xm-and-surveys/
│   ├── overview.mdx                       (XM overview — UPDATE)
│   ├── surveys/
│   │   ├── general-features/              (16 pages — UPDATE)
│   │   ├── link-surveys/                  (12 pages — UPDATE)
│   │   ├── website-app-surveys/           (8 pages — UPDATE)
│   │   └── question-type/                 (15 pages — UPDATE)
│   ├── core-features/
│   │   ├── integrations/                  (12 pages — UPDATE)
│   │   ├── user-management/               (5 pages — UPDATE)
│   │   ├── styling-theme.mdx              (UPDATE)
│   │   ├── test-environment.mdx           (UPDATE)
│   │   └── email-customization.mdx        (UPDATE)
│   └── xm/
│       └── best-practices/                (13 pages — UPDATE)
├── self-hosting/
│   ├── overview.mdx                       (UPDATE)
│   ├── auth-behavior.mdx                  (UPDATE)
│   ├── setup/                             (5 pages — UPDATE)
│   ├── configuration/
│   │   ├── environment-variables.mdx      (UPDATE)
│   │   ├── auth-sso/                      (4 pages — UPDATE)
│   │   ├── integrations/                  (7 pages — UPDATE)
│   │   └── [smtp, ssl, subpath, domain, uploads].mdx  (UPDATE)
│   └── advanced/
│       ├── enterprise-features/           (8 pages — UPDATE)
│       └── [license, migration, rate-limiting].mdx     (UPDATE)
├── development/
│   ├── overview.mdx                       (UPDATE)
│   ├── local-setup/                       (5 pages — UPDATE)
│   ├── standards/                         (10 pages — UPDATE)
│   ├── technical-handbook/                (3 pages — UPDATE)
│   ├── contribution/                      (1 page — UPDATE)
│   ├── guides/                            (1 page — UPDATE)
│   └── support/                           (1 page — UPDATE)
├── api-reference/
│   ├── openapi.json                       (OpenAPI 3.0 spec — UPDATE)
│   ├── rest-api.mdx + 42 endpoint pages   (UPDATE)
│   └── health/                            (1 page — UPDATE)
├── api-v2-reference/
│   ├── openapi.yml                        (OpenAPI 3.1.0 spec — UPDATE)
│   └── introduction.mdx                   (UPDATE)
└── images/                                (393 assets — UPDATE as needed)
```

### 0.4.2 Content Generation Strategy

**Information Extraction Approach:**
- Extract API signatures from `apps/web/modules/api/v2/` route handlers and Zod validation schemas in `packages/database/zod/`
- Generate endpoint examples by analyzing OpenAPI specifications at `docs/api-reference/openapi.json` and `docs/api-v2-reference/openapi.yml`
- Create architecture diagrams by mapping component relationships across `apps/web/modules/` and `packages/`
- Extract configuration documentation from `.env.example` and `apps/web/lib/constants.ts` (75+ environment variables)
- Derive integration setup steps from OAuth route handlers in `apps/web/app/api/v1/integrations/`
- Map question type documentation to Zod schemas in `packages/types/surveys/`

**Template Application:**
- Apply Mintlify frontmatter template to every MDX file with title, description, and icon fields
- Apply consistent section structure: Overview → Configuration → Usage → Examples → Troubleshooting
- Use Mintlify component patterns established in existing docs (CardGroup for navigation, Note for callouts, Steps for procedures)

**Documentation Standards:**
- Markdown/MDX formatting with headings starting at H2
- Mermaid diagram integration for architecture, data flow, and sequence diagrams
- Code examples with language identifiers for syntax highlighting (typescript, bash, yaml, json)
- Source citations as inline references pointing to source file paths with line numbers
- Tables for parameter descriptions, environment variables, and API endpoints
- Consistent terminology aligned with existing documentation
- Interactive survey embeds via iframe components for question type demos

### 0.4.3 Diagram and Visual Strategy

**Mermaid Diagrams to Create/Update:**

| Diagram Type | Subject | Target File |
|-------------|---------|-------------|
| Flowchart | Survey creation workflow | `docs/xm-and-surveys/overview.mdx` |
| Sequence | OAuth integration flow (4 providers) | `docs/xm-and-surveys/core-features/integrations/overview.mdx` |
| Sequence | API v2 authentication flow | `docs/api-v2-reference/introduction.mdx` |
| Flowchart | Self-hosting deployment decision tree | `docs/self-hosting/overview.mdx` |
| Entity-Relationship | Core database model (32 models) | `docs/development/technical-handbook/database-model.mdx` |
| Flowchart | SDK initialization and survey display | `docs/xm-and-surveys/surveys/website-app-surveys/quickstart.mdx` |
| Sequence | Webhook delivery with Standard Webhooks signing | `docs/xm-and-surveys/core-features/integrations/webhooks.mdx` |
| Flowchart | Rate limiting decision flow | `docs/self-hosting/advanced/rate-limiting.mdx` |
| Flowchart | Response collection pipeline | `docs/development/technical-handbook/overview.mdx` |
| Sequence | SAML/OIDC SSO authentication flow | `docs/self-hosting/configuration/auth-sso/saml-sso.mdx` |

**Screenshot/Image Requirements:**
- All images in `.webp` format stored in `docs/images/` subdirectories mirroring the documentation structure
- Descriptive alt text on all images for accessibility compliance
- Existing 393 image assets to be reviewed and updated where UI changes have occurred

## 0.5 Documentation File Transformation Mapping

### 0.5.1 File-by-File Documentation Plan

Every documentation file to be created, updated, or used as a reference is mapped below. Target documentation files are listed first.

**Transformation Modes:**
- **CREATE** — Create a new documentation file
- **UPDATE** — Update an existing documentation file
- **REFERENCE** — Use as an example for documentation style and structure

**Overview Section (3 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/overview/introduction.mdx` | UPDATE | `docs/overview/introduction.mdx`, `README.md` | Update welcome page with current feature list, ensure CardGroup links are accurate, verify platform description matches v3.7.0 capabilities |
| `docs/overview/what-is-formbricks.mdx` | UPDATE | `docs/overview/what-is-formbricks.mdx`, `apps/web/modules/` | Update platform capabilities overview with all 26 features, 4 distribution channels, 15 question types |
| `docs/overview/open-source.mdx` | UPDATE | `docs/overview/open-source.mdx`, `LICENSE` | Verify AGPLv3 license information, update community links, document EE dual-licensing model |

**XM &amp; Surveys — Survey General Features (16 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/xm-and-surveys/overview.mdx` | UPDATE | `docs/xm-and-surveys/overview.mdx` | Update XM overview with complete feature catalog, add survey creation workflow diagram |
| `docs/xm-and-surveys/surveys/general-features/conditional-logic.mdx` | UPDATE | `apps/web/modules/survey/`, `packages/types/surveys/` | Update DFS-based cycle detection docs, branching logic actions (calculate, requireAnswer, jumpToBlock) |
| `docs/xm-and-surveys/surveys/general-features/hidden-fields.mdx` | UPDATE | existing MDX | Verify hidden field configuration and data passing documentation |
| `docs/xm-and-surveys/surveys/general-features/multi-language-surveys.mdx` | UPDATE | `packages/i18n-utils/`, `apps/web/modules/ee/` | Update 14-locale support documentation, enterprise license requirement |
| `docs/xm-and-surveys/surveys/general-features/partial-submissions.mdx` | UPDATE | `apps/web/modules/survey/` | Update partial submission capture with `finished: false` behavior |
| `docs/xm-and-surveys/surveys/general-features/email-followups.mdx` | UPDATE | `apps/web/modules/ee/follow-ups/` | Update email follow-up documentation, enterprise license gate |
| `docs/xm-and-surveys/surveys/general-features/recall.mdx` | UPDATE | existing MDX | Verify recall/piping feature documentation |
| `docs/xm-and-surveys/surveys/general-features/variables.mdx` | UPDATE | existing MDX | Verify variable usage in surveys |
| `docs/xm-and-surveys/surveys/general-features/spam-protection.mdx` | UPDATE | existing MDX | Update CAPTCHA (Turnstile/reCAPTCHA) configuration docs |
| `docs/xm-and-surveys/surveys/general-features/validation-rules.mdx` | UPDATE | `packages/types/surveys/` | Update Zod-based validation rule documentation |
| `docs/xm-and-surveys/surveys/general-features/tags.mdx` | UPDATE | existing MDX | Verify tag management (rename, merge, delete) |
| `docs/xm-and-surveys/surveys/general-features/metadata.mdx` | UPDATE | existing MDX | Verify survey metadata documentation |
| `docs/xm-and-surveys/surveys/general-features/limit-submissions.mdx` | UPDATE | existing MDX | Update response quota management documentation |
| `docs/xm-and-surveys/surveys/general-features/quota-management.mdx` | UPDATE | `apps/web/modules/ee/` | Update quota management with plan limits (Free: 1500, Startup: 5000) |
| `docs/xm-and-surveys/surveys/general-features/overwrite-styling.mdx` | UPDATE | existing MDX | Verify styling override documentation |
| `docs/xm-and-surveys/surveys/general-features/add-image-or-video-question.mdx` | UPDATE | existing MDX | Verify media attachment documentation |
| `docs/xm-and-surveys/surveys/general-features/hide-back-button.mdx` | UPDATE | existing MDX | Verify hide back button feature docs |

**XM &amp; Surveys — Link Surveys (12 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/xm-and-surveys/surveys/link-surveys/quickstart.mdx` | UPDATE | existing MDX | Verify link survey quickstart flow |
| `docs/xm-and-surveys/surveys/link-surveys/link-settings.mdx` | UPDATE | existing MDX | Update link survey configuration options |
| `docs/xm-and-surveys/surveys/link-surveys/single-use-links.mdx` | UPDATE | existing MDX | Document single-use token invalidation after submission |
| `docs/xm-and-surveys/surveys/link-surveys/pin-protected-surveys.mdx` | UPDATE | existing MDX | Verify PIN validation documentation |
| `docs/xm-and-surveys/surveys/link-surveys/personal-links.mdx` | UPDATE | existing MDX | Verify personal link documentation |
| `docs/xm-and-surveys/surveys/link-surveys/data-prefilling.mdx` | UPDATE | existing MDX | Verify data prefilling documentation |
| `docs/xm-and-surveys/surveys/link-surveys/embed-surveys.mdx` | UPDATE | existing MDX | Update embed survey methods and iframe configuration |
| `docs/xm-and-surveys/surveys/link-surveys/source-tracking.mdx` | UPDATE | existing MDX | Verify source tracking documentation |
| `docs/xm-and-surveys/surveys/link-surveys/start-at-question.mdx` | UPDATE | existing MDX | Verify start-at-question parameter docs |
| `docs/xm-and-surveys/surveys/link-surveys/verify-email-before-survey.mdx` | UPDATE | existing MDX | Verify email verification flow docs |
| `docs/xm-and-surveys/surveys/link-surveys/custom-head-scripts.mdx` | UPDATE | existing MDX | Verify custom script injection docs |
| `docs/xm-and-surveys/surveys/link-surveys/market-research-panel.mdx` | UPDATE | existing MDX | Verify market research panel integration |

**XM &amp; Surveys — Website/App Surveys (8 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/xm-and-surveys/surveys/website-app-surveys/quickstart.mdx` | UPDATE | `packages/js-core/` | Update SDK quickstart with `formbricks.setup()` initialization, 7KB bundle size |
| `docs/xm-and-surveys/surveys/website-app-surveys/framework-guides.mdx` | UPDATE | `packages/js-core/`, `packages/surveys/` | Update framework-specific integration guides (React, Vue, Angular, etc.) |
| `docs/xm-and-surveys/surveys/website-app-surveys/actions.mdx` | UPDATE | `apps/web/modules/survey/` | Update action-based trigger documentation |
| `docs/xm-and-surveys/surveys/website-app-surveys/advanced-targeting.mdx` | UPDATE | `apps/web/modules/ee/contacts/` | Update segment-based targeting with attribute operators |
| `docs/xm-and-surveys/surveys/website-app-surveys/user-identification.mdx` | UPDATE | `packages/js-core/` | Update user identification and attribute tracking |
| `docs/xm-and-surveys/surveys/website-app-surveys/recontact.mdx` | UPDATE | existing MDX | Verify recontact settings documentation |
| `docs/xm-and-surveys/surveys/website-app-surveys/show-survey-to-percent-of-users.mdx` | UPDATE | existing MDX | Update displayPercentage configuration |
| `docs/xm-and-surveys/surveys/website-app-surveys/google-tag-manager.mdx` | UPDATE | existing MDX | Verify GTM integration guide |

**XM &amp; Surveys — Question Types (15 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/xm-and-surveys/surveys/question-type/free-text.mdx` | UPDATE | `packages/types/surveys/` | Update OpenText question type documentation |
| `docs/xm-and-surveys/surveys/question-type/select-single.mdx` | UPDATE | `packages/types/surveys/` | Update MultipleChoiceSingle documentation |
| `docs/xm-and-surveys/surveys/question-type/select-multiple.mdx` | UPDATE | `packages/types/surveys/` | Update MultipleChoiceMulti documentation |
| `docs/xm-and-surveys/surveys/question-type/net-promoter-score.mdx` | UPDATE | `packages/types/surveys/` | Update NPS question type docs |
| `docs/xm-and-surveys/surveys/question-type/statement-cta.mdx` | UPDATE | `packages/types/surveys/` | Update CTA/statement card docs |
| `docs/xm-and-surveys/surveys/question-type/rating.mdx` | UPDATE | `packages/types/surveys/` | Update rating question with CSAT scoring methodology |
| `docs/xm-and-surveys/surveys/question-type/consent.mdx` | UPDATE | `packages/types/surveys/` | Update consent question docs |
| `docs/xm-and-surveys/surveys/question-type/select-picture.mdx` | UPDATE | `packages/types/surveys/` | Update PictureSelection docs |
| `docs/xm-and-surveys/surveys/question-type/schedule-a-meeting.mdx` | UPDATE | `packages/types/surveys/` | Update Cal.com integration docs |
| `docs/xm-and-surveys/surveys/question-type/date.mdx` | UPDATE | `packages/types/surveys/` | Update date question type docs |
| `docs/xm-and-surveys/surveys/question-type/matrix.mdx` | UPDATE | `packages/types/surveys/` | Update matrix question type docs |
| `docs/xm-and-surveys/surveys/question-type/address.mdx` | UPDATE | `packages/types/surveys/` | Update address question type docs |
| `docs/xm-and-surveys/surveys/question-type/ranking.mdx` | UPDATE | `packages/types/surveys/` | Update ranking question type docs |
| `docs/xm-and-surveys/surveys/question-type/contact-info.mdx` | UPDATE | `packages/types/surveys/` | Update ContactInfo question type docs |
| `docs/xm-and-surveys/surveys/question-type/file-upload.mdx` | UPDATE | `packages/types/surveys/`, `packages/storage/` | Update FileUpload docs with 5MB/10MB/1GB size limits |

**XM &amp; Surveys — Core Features (20 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/xm-and-surveys/core-features/integrations/overview.mdx` | UPDATE | `apps/web/modules/integrations/` | Add OAuth flow diagram, update integration list |
| `docs/xm-and-surveys/core-features/integrations/slack.mdx` | UPDATE | `apps/web/lib/slack/` | Update Slack integration with OAuth scopes, 2995 char limit |
| `docs/xm-and-surveys/core-features/integrations/google-sheets.mdx` | UPDATE | `apps/web/lib/googleSheet/` | Update Google Sheets with encrypted token storage, 49995 char limit |
| `docs/xm-and-surveys/core-features/integrations/notion.mdx` | UPDATE | `apps/web/lib/notion/` | Update Notion with rich text limit (1995 chars), PKCE details |
| `docs/xm-and-surveys/core-features/integrations/airtable.mdx` | UPDATE | `apps/web/lib/airtable/` | Update Airtable with PKCE S256 challenge, 99995 char limit |
| `docs/xm-and-surveys/core-features/integrations/zapier.mdx` | UPDATE | existing MDX | Update Zapier webhook-based integration docs |
| `docs/xm-and-surveys/core-features/integrations/n8n.mdx` | UPDATE | existing MDX | Update n8n webhook integration docs |
| `docs/xm-and-surveys/core-features/integrations/webhooks.mdx` | UPDATE | `apps/web/modules/integrations/webhooks/` | Add Standard Webhooks compliance, HMAC-SHA256 signing, whsec_ format, Discord blocking |
| `docs/xm-and-surveys/core-features/integrations/wordpress.mdx` | UPDATE | existing MDX | Verify WordPress integration docs |
| `docs/xm-and-surveys/core-features/integrations/activepieces.mdx` | UPDATE | existing MDX | Verify Activepieces integration docs |
| `docs/xm-and-surveys/core-features/integrations/hubspot.mdx` | UPDATE | existing MDX | Verify HubSpot integration docs |
| `docs/xm-and-surveys/core-features/integrations/make.mdx` | UPDATE | existing MDX | Verify Make integration docs |
| `docs/xm-and-surveys/core-features/styling-theme.mdx` | UPDATE | `packages/survey-ui/` | Update styling/theming docs with CSS variable system, #fbjs scoping |
| `docs/xm-and-surveys/core-features/test-environment.mdx` | UPDATE | existing MDX | Verify test environment documentation |
| `docs/xm-and-surveys/core-features/email-customization.mdx` | UPDATE | `packages/email/` | Update email template customization with branding, legal footers |
| `docs/xm-and-surveys/core-features/user-management.mdx` | UPDATE | `apps/web/modules/organization/` | Update user management overview |
| `docs/xm-and-surveys/core-features/user-management/organizations-and-roles.mdx` | UPDATE | `apps/web/modules/organization/` | Update org roles (owner, manager, member, billing) |
| `docs/xm-and-surveys/core-features/user-management/teams-and-roles.mdx` | UPDATE | `apps/web/modules/ee/teams/` | Update team roles (admin, contributor), enterprise feature |
| `docs/xm-and-surveys/core-features/user-management/invite-members.mdx` | UPDATE | existing MDX | Update member invitation with bulk CSV upload |
| `docs/xm-and-surveys/core-features/user-management/two-factor-auth.mdx` | UPDATE | `apps/web/modules/ee/two-factor-auth/` | Update TOTP setup, backup codes, enterprise feature |

**XM &amp; Surveys — Best Practices (13 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/xm-and-surveys/xm/best-practices/pmf-survey.mdx` | UPDATE | existing MDX | Verify PMF survey best practices |
| `docs/xm-and-surveys/xm/best-practices/feedback-box.mdx` | UPDATE | existing MDX | Verify feedback box best practices |
| `docs/xm-and-surveys/xm/best-practices/feature-chaser.mdx` | UPDATE | existing MDX | Verify feature chaser guide |
| `docs/xm-and-surveys/xm/best-practices/cancel-subscription.mdx` | UPDATE | existing MDX | Verify churn survey guide |
| `docs/xm-and-surveys/xm/best-practices/interview-prompt.mdx` | UPDATE | existing MDX | Verify interview prompt guide |
| `docs/xm-and-surveys/xm/best-practices/improve-trial-cr.mdx` | UPDATE | existing MDX | Verify trial improvement guide |
| `docs/xm-and-surveys/xm/best-practices/improve-email-content.mdx` | UPDATE | existing MDX | Verify email improvement guide |
| `docs/xm-and-surveys/xm/best-practices/docs-feedback.mdx` | UPDATE | existing MDX | Verify docs feedback guide |
| `docs/xm-and-surveys/xm/best-practices/contact-form.mdx` | UPDATE | existing MDX | Verify contact form guide |
| `docs/xm-and-surveys/xm/best-practices/headless-surveys.mdx` | UPDATE | existing MDX | Verify headless survey integration |
| `docs/xm-and-surveys/xm/best-practices/quiz-time.mdx` | UPDATE | existing MDX | Verify quiz creation guide |
| `docs/xm-and-surveys/xm/best-practices/research-panel.mdx` | UPDATE | existing MDX | Verify research panel management |
| `docs/xm-and-surveys/xm/best-practices/understanding-survey-types.mdx` | UPDATE | existing MDX | Update survey types guide (app vs link) |

**Self Hosting Section (36 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/self-hosting/overview.mdx` | UPDATE | existing MDX | Update self-hosting overview with deployment decision tree diagram |
| `docs/self-hosting/auth-behavior.mdx` | UPDATE | `apps/web/modules/auth/` | Update auth behavior with all env vars, SSO skip invite, default team |
| `docs/self-hosting/setup/docker.mdx` | UPDATE | `docker/docker-compose.yml` | Update Docker setup with MinIO S3 storage, PostgreSQL pgvector:pg17, Valkey |
| `docs/self-hosting/setup/one-click.mdx` | UPDATE | `docker/formbricks.sh` | Verify one-click Ubuntu setup script documentation |
| `docs/self-hosting/setup/kubernetes.mdx` | UPDATE | `charts/` | Update Kubernetes/Helm deployment guide |
| `docs/self-hosting/setup/cluster-setup.mdx` | UPDATE | existing MDX | Verify cluster deployment documentation |
| `docs/self-hosting/setup/monitoring.mdx` | UPDATE | `apps/web/instrumentation-node.ts` | Update with OpenTelemetry, Prometheus (port 9464), Sentry, SigNoz config |
| `docs/self-hosting/configuration/environment-variables.mdx` | UPDATE | `.env.example`, `apps/web/lib/constants.ts` | Comprehensive update of 75+ environment variables |
| `docs/self-hosting/configuration/smtp.mdx` | UPDATE | existing MDX | Verify SMTP configuration docs |
| `docs/self-hosting/configuration/custom-ssl.mdx` | UPDATE | existing MDX | Verify custom SSL certificate docs |
| `docs/self-hosting/configuration/custom-subpath.mdx` | UPDATE | existing MDX | Verify custom subpath configuration |
| `docs/self-hosting/configuration/domain-configuration.mdx` | UPDATE | existing MDX | Verify domain configuration docs |
| `docs/self-hosting/configuration/file-uploads.mdx` | UPDATE | `packages/storage/` | Update with S3, MinIO, size limits (5MB/10MB/1GB) |
| `docs/self-hosting/configuration/auth-sso/google-oauth.mdx` | UPDATE | `apps/web/modules/auth/` | Verify Google OAuth setup guide |
| `docs/self-hosting/configuration/auth-sso/azure-ad-oauth.mdx` | UPDATE | existing MDX | Verify Azure AD OAuth setup guide |
| `docs/self-hosting/configuration/auth-sso/open-id-connect.mdx` | UPDATE | `apps/web/modules/ee/oidc-sso/` | Update OIDC SSO configuration |
| `docs/self-hosting/configuration/auth-sso/saml-sso.mdx` | UPDATE | `apps/web/modules/ee/saml-sso/` | Update SAML SSO with dedicated database, BoxyHQ saml-jackson 1.52.2 |
| `docs/self-hosting/configuration/integrations/slack.mdx` | UPDATE | existing MDX | Verify self-hosted Slack integration config |
| `docs/self-hosting/configuration/integrations/google-sheets.mdx` | UPDATE | existing MDX | Verify self-hosted Google Sheets config |
| `docs/self-hosting/configuration/integrations/notion.mdx` | UPDATE | existing MDX | Verify self-hosted Notion config |
| `docs/self-hosting/configuration/integrations/airtable.mdx` | UPDATE | existing MDX | Verify self-hosted Airtable config |
| `docs/self-hosting/configuration/integrations/zapier.mdx` | UPDATE | existing MDX | Verify self-hosted Zapier config |
| `docs/self-hosting/configuration/integrations/n8n.mdx` | UPDATE | existing MDX | Verify self-hosted n8n config |
| `docs/self-hosting/configuration/integrations/activepieces.mdx` | UPDATE | existing MDX | Verify self-hosted Activepieces config |
| `docs/self-hosting/advanced/license.mdx` | UPDATE | `apps/web/modules/ee/license-check/` | Update license management with remote validation, caching, grace period |
| `docs/self-hosting/advanced/license-activation.mdx` | UPDATE | existing MDX | Verify license activation process |
| `docs/self-hosting/advanced/migration.mdx` | UPDATE | `packages/database/` | Update migration guide for 120+ migration files |
| `docs/self-hosting/advanced/rate-limiting.mdx` | UPDATE | `apps/web/modules/core/rate-limit/` | Update with Redis Lua scripts, fail-open design, 12 rate limit categories |
| `docs/self-hosting/advanced/enterprise-features/saml-sso.mdx` | UPDATE | `apps/web/modules/ee/saml-sso/` | Update SAML SSO enterprise guide |
| `docs/self-hosting/advanced/enterprise-features/oidc-sso.mdx` | UPDATE | `apps/web/modules/ee/oidc-sso/` | Update OIDC SSO enterprise guide |
| `docs/self-hosting/advanced/enterprise-features/audit-logging.mdx` | UPDATE | `apps/web/modules/ee/audit-logs/` | Update audit logging with async queue, Zod-validated events |
| `docs/self-hosting/advanced/enterprise-features/team-access.mdx` | UPDATE | `apps/web/modules/ee/teams/` | Update team-based access control |
| `docs/self-hosting/advanced/enterprise-features/multi-language-surveys.mdx` | UPDATE | `packages/i18n-utils/` | Update multi-language enterprise feature |
| `docs/self-hosting/advanced/enterprise-features/contact-management-segments.mdx` | UPDATE | `apps/web/modules/ee/contacts/` | Update contact/segment management |
| `docs/self-hosting/advanced/enterprise-features/hide-powered-by-formbricks.mdx` | UPDATE | existing MDX | Verify whitelabel feature docs |
| `docs/self-hosting/advanced/enterprise-features/whitelabel-email-follow-ups.mdx` | UPDATE | `apps/web/modules/ee/follow-ups/` | Update email follow-up whitelabel |

**Development Section (22 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/development/overview.mdx` | UPDATE | existing MDX | Update development overview with monorepo structure |
| `docs/development/local-setup/mac.mdx` | UPDATE | existing MDX | Verify macOS local setup (pnpm 10.28.2, Node ≥20) |
| `docs/development/local-setup/linux.mdx` | UPDATE | existing MDX | Verify Linux local setup |
| `docs/development/local-setup/windows.mdx` | UPDATE | existing MDX | Verify Windows local setup |
| `docs/development/local-setup/github-codespaces.mdx` | UPDATE | existing MDX | Verify Codespaces setup |
| `docs/development/local-setup/gitpod.mdx` | UPDATE | existing MDX | Verify Gitpod setup |
| `docs/development/standards/organization/file-and-directory-organization.mdx` | UPDATE | `AGENTS.md` | Update file organization standards |
| `docs/development/standards/organization/module-component-structure.mdx` | UPDATE | `AGENTS.md` | Update module structure standards |
| `docs/development/standards/organization/naming-conventions.mdx` | UPDATE | `AGENTS.md` | Update naming conventions |
| `docs/development/standards/practices/code-formatting.mdx` | UPDATE | `packages/config-eslint/`, `packages/config-prettier/` | Update ESLint/Prettier configuration |
| `docs/development/standards/practices/documentation.mdx` | UPDATE | `AGENTS.md` | Update internal documentation standards |
| `docs/development/standards/practices/error-handling.mdx` | UPDATE | existing MDX | Update Result pattern, Zod validation docs |
| `docs/development/standards/qa/code-reviews.mdx` | UPDATE | existing MDX | Verify code review standards |
| `docs/development/standards/qa/testing-methodology.mdx` | UPDATE | existing MDX | Update testing (Vitest for .ts, Playwright for .tsx) |
| `docs/development/standards/technical/framework-usage.mdx` | UPDATE | `AGENTS.md` | Update Next.js 16.1.6, React 19.2.3 framework docs |
| `docs/development/standards/technical/language-specific-conventions.mdx` | UPDATE | `AGENTS.md` | Update TypeScript strict mode conventions |
| `docs/development/technical-handbook/overview.mdx` | UPDATE | existing MDX | Update technical architecture overview |
| `docs/development/technical-handbook/database-model.mdx` | UPDATE | `packages/database/` | Update 32 Prisma models, 21 enums, ER diagram |
| `docs/development/technical-handbook/tenant-separation.mdx` | UPDATE | existing MDX | Update Organization → Project → Environment hierarchy |
| `docs/development/contribution/contribution.mdx` | UPDATE | `CONTRIBUTING.md` | Update contribution guidelines |
| `docs/development/guides/auth-and-provision/setup-saml-with-identity-providers.mdx` | UPDATE | existing MDX | Update SAML identity provider setup guide |
| `docs/development/support/troubleshooting.mdx` | UPDATE | existing MDX | Update troubleshooting guide |

**API v1 Reference Section (44 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/api-reference/openapi.json` | UPDATE | `apps/web/app/api/v1/` | Synchronize OpenAPI 3.0 spec with current v1 endpoints |
| `docs/api-reference/rest-api.mdx` | UPDATE | existing MDX | Update REST API overview with dual-version architecture |
| `docs/api-reference/generate-key.mdx` | UPDATE | existing MDX | Update API key generation guide |
| `docs/api-reference/test-key.mdx` | UPDATE | existing MDX | Update API key testing guide |
| `docs/api-reference/health/health-check.mdx` | UPDATE | existing MDX | Verify health check endpoint docs |
| `docs/api-reference/client-api--display/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update display create/update endpoint docs (2 files) |
| `docs/api-reference/client-api--people/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update people create/update endpoint docs (2 files) |
| `docs/api-reference/client-api--response/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update response create/update endpoint docs (2 files) |
| `docs/api-reference/management-api--action-class/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update action class CRUD docs (4 files) |
| `docs/api-reference/management-api--attribute-class/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update attribute class CRUD docs (4 files) |
| `docs/api-reference/management-api--contact-attribute-keys/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update contact attribute key docs (2 files) |
| `docs/api-reference/management-api--contact-attributes/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update contact attributes docs (1 file) |
| `docs/api-reference/management-api--contacts/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update contacts endpoint docs (2 files) |
| `docs/api-reference/management-api--me/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update me endpoint docs (1 file) |
| `docs/api-reference/management-api--people/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update people endpoint docs (3 files) |
| `docs/api-reference/management-api--response/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update response CRUD docs (5 files) |
| `docs/api-reference/management-api--storage/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update storage upload docs (1 file) |
| `docs/api-reference/management-api--survey/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update survey CRUD docs (6 files) |
| `docs/api-reference/management-api--webhook/*.mdx` | UPDATE | `apps/web/app/api/v1/` | Update webhook CRUD docs (4 files) |

**API v2 Reference Section (2 files):**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/api-v2-reference/openapi.yml` | UPDATE | `apps/web/modules/api/v2/openapi-document.ts` | Regenerate OpenAPI 3.1.0 spec from Zod schemas for all 13+ domain modules |
| `docs/api-v2-reference/introduction.mdx` | UPDATE | `apps/web/modules/api/v2/` | Update API v2 introduction with authentication guide, Result pattern, endpoint catalog |

**Configuration and Navigation Files:**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `docs/docs.json` | UPDATE | `docs/docs.json` | Update navigation for any new pages, verify redirect rules, ensure tab configuration accuracy |
| `docs/README.md` | UPDATE | `docs/README.md` | Update local development instructions for Mintlify CLI v4.x |

**Reference Files:**

| Target Documentation File | Transformation | Source Code/Docs | Content/Changes |
|---------------------------|----------------|------------------|-----------------|
| `README.md` | UPDATE | `README.md` | Update root README with current feature list and documentation links |
| `CONTRIBUTING.md` | REFERENCE | `CONTRIBUTING.md` | Use as style reference for contribution documentation |
| `AGENTS.md` | REFERENCE | `AGENTS.md` | Use as authoritative source for documentation standards |

### 0.5.2 Cross-Documentation Dependencies

**Shared Content and Includes:**
- OpenAPI specifications (`openapi.json`, `openapi.yml`) are referenced by multiple MDX files through Mintlify's automatic API page generation
- Brand assets (`docs/images/favicon.svg`, `docs/images/logo-dark.svg`, `docs/images/logo-light.svg`) are shared across all documentation pages via `docs.json` configuration
- Integration setup guides in `docs/xm-and-surveys/core-features/integrations/` cross-reference self-hosting configuration guides in `docs/self-hosting/configuration/integrations/`

**Navigation Link Dependencies:**
- `docs/docs.json` navigation must be updated whenever new pages are added
- Redirect rules in `docs/docs.json` must be maintained for any URL path changes
- CardGroup cross-references in overview pages must point to valid page paths

**Table of Contents Updates:**
- The `docs/docs.json` `navigation` → `tabs` structure serves as the master table of contents
- Any new page additions require corresponding navigation entries

**Index/Glossary Updates:**
- No dedicated glossary file exists; terminology is maintained inline
- Internal links between documentation sections use Mintlify's relative path format

## 0.6 Dependency Inventory

### 0.6.1 Documentation Dependencies

All key documentation tools and packages relevant to this documentation exercise:

| Registry | Package Name | Version | Purpose |
|----------|--------------|---------|---------|
| npm | mintlify | 4.2.378 | Mintlify CLI for local documentation preview, link checking, validation, and deployment |
| npm | @mintlify/cli | 4.0.712 | Alternative Mintlify CLI package (scoped registry) |
| - | Mintlify SaaS | - | Hosted documentation platform (deployment via GitHub App integration) |
| npm | zod-openapi | (used in codebase) | Runtime OpenAPI 3.1.0 specification generation from Zod schemas for API v2 docs |
| npm | yaml | (used in codebase) | YAML serialization for OpenAPI spec output (`yaml.stringify()`) |
| - | Mermaid | (embedded in MDX) | Diagram rendering within Mintlify MDX pages (flowcharts, sequences, ER diagrams) |
| - | PostHog (EU) | - | Analytics integration configured in `docs/docs.json` for documentation visitor tracking |

**Runtime and Infrastructure Requirements:**

| Component | Requirement | Evidence |
|-----------|------------|----------|
| Node.js | ≥ 20.17.0 (LTS recommended) | Mintlify CLI requirement; monorepo requires Node.js ≥20.0.0 per `package.json` engines |
| pnpm | 10.28.2 | Package manager for monorepo (required for `pnpm dev` in `apps/storybook`) |
| Git | Latest stable | Version control; GitHub App integration for Mintlify auto-deployment |

**OpenAPI Specification Dependencies:**

| Specification | Format | Source | Generator |
|--------------|--------|--------|-----------|
| API v1 OpenAPI | 3.0 (JSON) | `docs/api-reference/openapi.json` | Static specification file (manually maintained) |
| API v2 OpenAPI | 3.1.0 (YAML) | `docs/api-v2-reference/openapi.yml` | Runtime-generated via `apps/web/modules/api/v2/openapi-document.ts` using `zod-openapi` |
| Root OpenAPI | 3.1.0 (YAML) | `openapi.yml` | Static specification file (simplified responses endpoint) |

### 0.6.2 Documentation Reference Updates

**Documentation Files Requiring Link Updates:**

When pages are reorganized or new pages are added, internal links must be updated across the documentation suite. The following rules apply:

- All internal documentation links use relative paths without file extensions (e.g., `/self-hosting/setup/docker` not `self-hosting/setup/docker.mdx`)
- Legacy redirect rules in `docs/docs.json` handle historical URL path changes (dozens of redirect mappings currently exist)
- Cross-section references between XM &amp; Surveys ↔ Self Hosting ↔ Development sections must maintain bidirectional accuracy
- CardGroup navigation links in overview pages must point to valid page paths within the current tab structure
- API reference pages auto-generated from OpenAPI specs maintain their own internal link structure managed by Mintlify

## 0.7 Coverage and Quality Targets

### 0.7.1 Documentation Coverage Metrics

**Current Coverage Analysis:**

| Coverage Area | Documented | Total | Coverage % |
|--------------|-----------|-------|------------|
| Core Features (F-001 to F-016) | 16 | 16 | 100% (varying depth) |
| Enterprise Features (F-017 to F-026) | 10 | 10 | 100% (varying depth) |
| Question Types | 15 | 15 | 100% |
| Distribution Channels | 4 | 4 | 100% |
| Native Integrations | 6+ | 6+ | 100% |
| API v1 Endpoints | 43 pages | 43 pages | 100% |
| API v2 Endpoints | 1 page | 13+ modules | ~8% |
| Self-Hosting Methods | 5 | 5 | 100% |
| Auth/SSO Providers | 4 | 6+ | ~67% |
| Environment Variables | 75+ | 75+ | ~90% |
| Development Setup (OS) | 5 | 5 | 100% |
| Best Practice Guides | 13 | 13 | 100% |

**Navigation Integrity:** 150 out of 150 page references in `docs.json` resolve to existing MDX files (100% link integrity).

**Target Coverage after Documentation Update:**

| Coverage Area | Current | Target | Gap to Close |
|--------------|---------|--------|-------------|
| API v2 Reference | ~8% | 100% | Create endpoint docs for 13+ domain modules |
| Auth/SSO Providers | ~67% | 100% | Add CAPTCHA configuration, update OIDC/SAML |
| Environment Variables | ~90% | 100% | Add Stripe, CAPTCHA, observability variables |
| Analytics/Insights | ~40% | 100% | Add CSAT scoring, insight generation, dashboards |
| Webhook Standards | ~50% | 100% | Add Standard Webhooks signing documentation |
| Monitoring/Observability | ~60% | 100% | Add OpenTelemetry, Prometheus, Sentry self-hosted config |
| Database Model Reference | ~50% | 100% | Document all 32 models, 21 enums with ER diagram |

### 0.7.2 Documentation Quality Criteria

**Completeness Requirements:**
- All API endpoints have descriptions, parameter tables, request/response examples, and authentication requirements
- All user guides include overview, setup steps, configuration options, usage examples, and troubleshooting sections
- All self-hosting guides include prerequisites, step-by-step procedures, verification steps, and common issues
- All enterprise features clearly annotate license requirements with `<Note>` components
- All integration guides include OAuth setup, configuration, data mapping, and error handling sections

**Accuracy Validation:**
- API documentation must match current OpenAPI specifications (`openapi.json` for v1, `openapi.yml` for v2)
- Environment variable documentation must match `.env.example` and `apps/web/lib/constants.ts`
- Code examples must use current SDK syntax (e.g., `formbricks.setup()` initialization)
- Screenshots and UI images in `docs/images/` must reflect the current UI state
- Plan limits must match billing constants: Free (3 projects, 1500 responses, 2000 MIU), Startup (3/5000/7500)

**Clarity Standards:**
- Technical accuracy with accessible language for developers and product managers
- Progressive disclosure: quickstart guides → detailed configuration → advanced topics
- Consistent terminology aligned with existing documentation (e.g., "survey" not "form", "contact" not "person", "environment" not "workspace")
- Every page follows the Mintlify frontmatter template with descriptive title, description, and icon

**Maintainability:**
- Source citations linking documentation claims to source code files
- Version annotations for features introduced or changed in specific versions
- Clear enterprise feature designation throughout
- Mintlify navigation in `docs/docs.json` stays synchronized with actual page structure

### 0.7.3 Example and Diagram Requirements

| Requirement | Standard | Application |
|------------|----------|-------------|
| Examples per API method | Minimum 1 request + 1 response | All API v1 and v2 endpoint pages |
| Diagrams per architecture section | Minimum 1 Mermaid diagram | Technical handbook, integration overview, deployment guides |
| Interactive demos | Iframe embeds for question types | All 15 question type pages (where live survey URLs exist) |
| Code examples per SDK method | Minimum 1 JavaScript/TypeScript | SDK quickstart, framework guides, user identification |
| Configuration examples | Complete environment variable blocks | Self-hosting setup, integration configuration, auth/SSO |
| Verification method | `mintlify dev` for local preview, `mint check-links` for link validation | Pre-deployment CI/CD validation |
| Visual content freshness | Review all 393 images for current UI accuracy | Update `.webp` screenshots where UI has changed |

## 0.8 Scope Boundaries

### 0.8.1 Exhaustively In Scope

**Documentation Content Files (with trailing patterns):**
- `docs/overview/**/*.mdx` — All platform overview documentation (3 files)
- `docs/xm-and-surveys/**/*.mdx` — All XM and survey documentation including surveys, question types, integrations, user management, and best practices (85 files)
- `docs/self-hosting/**/*.mdx` — All self-hosting documentation including setup, configuration, auth/SSO, integrations, and advanced enterprise features (36 files)
- `docs/development/**/*.mdx` — All developer documentation including local setup, standards, technical handbook, contribution guides, and troubleshooting (22 files)
- `docs/api-reference/**/*.mdx` — All API v1 reference documentation including client API and management API endpoints (43 files)
- `docs/api-v2-reference/**/*.mdx` — All API v2 reference documentation (1 file — introduction)

**API Specification Files:**
- `docs/api-reference/openapi.json` — OpenAPI 3.0 specification for REST API v1
- `docs/api-v2-reference/openapi.yml` — OpenAPI 3.1.0 specification for REST API v2
- `openapi.yml` — Root-level OpenAPI 3.1.0 specification (simplified responses)

**Documentation Configuration:**
- `docs/docs.json` — Mintlify navigation configuration, theme, redirects, analytics, navbar
- `docs/README.md` — Documentation contributor instructions

**Documentation Assets:**
- `docs/images/**/*` — All documentation images and screenshots (393 files including `.webp`, `.svg`)

**Root Documentation Files:**
- `README.md` — Project root marketing README
- `CONTRIBUTING.md` — Community contribution guidelines
- `SECURITY.md` — Security policy

**Reference Files (read-only analysis):**
- `AGENTS.md` — Documentation standards and coding guidelines
- `.env.example` — Environment variable reference
- `apps/web/lib/constants.ts` — Application constants (plan limits, file sizes, pagination)
- `packages/types/surveys/` — Zod survey schemas (documentation source of truth)
- `packages/database/zod/` — Database validation schemas
- `apps/web/modules/api/v2/openapi-document.ts` — API v2 OpenAPI generator

### 0.8.2 Explicitly Out of Scope

- **Source code modifications** — No changes to application source code in `apps/web/`, `packages/`, or any TypeScript/JavaScript files (unless adding JSDoc comments/docstrings is explicitly requested)
- **Test file modifications** — No changes to test files in any `__tests__/`, `tests/`, or `*.test.*` files
- **Feature additions or code refactoring** — Documentation changes only; no new features, bug fixes, or code restructuring
- **Deployment configuration changes** — No modifications to `docker/`, `charts/`, `.github/`, CI/CD workflows, or infrastructure manifests (documentation content about these topics is in scope)
- **Storybook documentation** — The `apps/storybook` workspace is a separate documentation system and is out of scope for this Mintlify documentation effort
- **Unrelated documentation** — Any documentation not referenced in `docs/docs.json` navigation or not within the `docs/` directory
- **Dedicated mobile applications** — No mobile app documentation (mobile apps are out of project scope per tech spec Section 1.3)
- **Offline capabilities** — No offline mode documentation
- **Alternative database backends** — Documentation assumes PostgreSQL only
- **Custom ML/AI pipelines** — No AI/ML-specific documentation
- **White-label reselling** — No reseller or white-label distribution documentation
- **Third-party hosting platforms** — No documentation for Railway, RepoCloud, Zeabur, or Vercel-specific deployments beyond what currently exists
- **Items explicitly excluded by the user** — No additional exclusions were specified

## 0.9 Execution Parameters

### 0.9.1 Documentation-Specific Instructions

**Documentation Build and Preview Commands:**

| Command | Purpose | Working Directory |
|---------|---------|-------------------|
| `npm i -g mintlify` | Install Mintlify CLI globally | Any |
| `mintlify dev` | Start local documentation preview server (default port 3000) | `docs/` |
| `mintlify dev --port 3333` | Start preview on custom port | `docs/` |
| `mintlify dev --disable-openapi` | Skip OpenAPI processing for faster startup | `docs/` |
| `mint check-links` | Check for broken internal links | `docs/` |
| `mint check-links --check-anchors` | Check broken links including anchor references | `docs/` |
| `mint a11y` | Accessibility audit (contrast ratios, alt text) | `docs/` |
| `mint openapi-check` | Validate OpenAPI specification files | `docs/` |
| `mint validate --strict` | Strict build validation for CI/CD (exits on warnings) | `docs/` |
| `mint rename` | Rename files and update all internal link references | `docs/` |
| `mint update` | Update Mintlify CLI to latest version | Any |

**OpenAPI Specification Regeneration (API v2):**

The API v2 OpenAPI specification is generated at runtime from Zod schemas. To regenerate:
- Source: `apps/web/modules/api/v2/openapi-document.ts`
- Method: Execute the document generator which compiles Zod schemas via `zod-openapi` and serializes to YAML via `yaml.stringify()`
- Output: `docs/api-v2-reference/openapi.yml`

**Default Documentation Format:**
- Markdown/MDX with Mintlify components
- Mermaid diagrams for visual content (rendered natively by Mintlify)
- Code blocks with language identifiers for syntax highlighting

**Citation Requirement:**
- Every technical documentation section must reference source code files using inline path references
- Format: `Source: path/to/file.ts` or as Mintlify footnote links

**Style Guide:**
- Primary: `AGENTS.md` documentation section and `docs/development/standards/practices/documentation.mdx`
- Secondary: Mintlify documentation best practices
- Frontmatter: Required on every MDX file (title, description, icon)
- Headings: Camel Case, starting at H2 (no H1 — Mintlify generates from title)
- Components: Use Mintlify `<Note>`, `<Warning>`, `<Steps>`, `<Card>`, `<CardGroup>` components

**Documentation Validation Pipeline:**
- Pre-commit: `mint check-links` to verify no broken links introduced
- CI/CD: `mint validate --strict` in GitHub Actions workflow
- Accessibility: `mint a11y` for contrast ratio and alt text compliance
- OpenAPI: `mint openapi-check` against both `openapi.json` and `openapi.yml` specifications
- Deployment: Automatic via Mintlify GitHub App on push to default branch

## 0.10 Rules for Documentation

The following rules govern all documentation changes in this scope:

- **Follow existing Mintlify documentation style and structure** — All new and updated content must adhere to the patterns established in the existing 190 MDX files, using the same heading hierarchy, component usage, and formatting conventions
- **All documentation files must use the `.mdx` extension** — As specified in Formbricks documentation standards (`docs/development/standards/practices/documentation.mdx`)
- **Include required frontmatter metadata on every page** — Every MDX file must have a YAML frontmatter block with `title` (in Camel Case), `description` (brief content summary), and `icon` (Mintlify icon identifier)
- **No H1 headings in MDX content** — Mintlify automatically generates the H1 from the frontmatter `title`; all content headings start at H2 (`##`)
- **Use Camel Case for all headings** — Per AGENTS.md documentation standards
- **Use Mintlify components for structured content** — `<Note>` for important information, `<Warning>` for critical warnings, `<Steps>` for sequential procedures, `<Card>` and `<CardGroup>` for navigation cards, `<Accordion>` for collapsible content
- **Enterprise features must be clearly annotated** — Use `<Note>` blocks with enterprise license requirement messaging on all pages documenting EE features (SSO, audit logging, team access, billing, quotas, multi-language, whitelabel, contacts/segments, email follow-ups, insights)
- **Store all images in `docs/images/` subdirectories** — Mirror the documentation section structure (e.g., `docs/images/xm-and-surveys/core-features/integrations/slack/`)
- **Use descriptive alt text for all images** — Required for accessibility compliance
- **Optimize images for web delivery in `.webp` format** — Consistent with existing 393 image assets
- **Use relative paths for all internal links** — Without file extensions (e.g., `/self-hosting/setup/docker` not `self-hosting/setup/docker.mdx`)
- **Register all new pages in `docs/docs.json` navigation** — Every new MDX file must have a corresponding entry in the navigation structure
- **Add redirects for any URL path changes** — Use the `redirects` array in `docs/docs.json` to maintain backward compatibility
- **Include working code examples for API endpoints** — Every API reference page must include at least one request example and one response example
- **Document all environment variables in table format** — Using the pattern: Variable Name | Type | Default | Description
- **Source citations for all technical details** — Reference source code files inline when documenting implementation-specific behavior
- **Maintain Mintlify theme consistency** — Use the brand teal (#00C4B8) color scheme as configured in `docs/docs.json`
- **Keep documentation synchronized with code changes** — When the codebase evolves, documentation must reflect the current state of the application
- **Preserve PostHog analytics integration** — Do not remove or modify the PostHog EU analytics configuration in `docs/docs.json`
- **Validate documentation before deployment** — Run `mint check-links`, `mint a11y`, and `mint validate --strict` before merging changes

## 0.11 References

### 0.11.1 Repository Files and Folders Searched

**Root-Level Files Examined:**

| File Path | Purpose | Key Findings |
|-----------|---------|--------------|
| `README.md` | Root marketing README | Feature overview, trust logos, platform description |
| `AGENTS.md` | Repository coding and documentation guidelines | Documentation standards (Mintlify, frontmatter, Camel Case, components) |
| `CONTRIBUTING.md` | Community contribution guidelines | PR workflow, issue reporting, feature proposals |
| `SECURITY.md` | Security policy | Vulnerability reporting procedures |
| `LICENSE` | License file | AGPLv3 with EE dual-licensing |
| `package.json` | Root monorepo manifest | pnpm 10.28.2, Turborepo 2.5.3, Node ≥20.0.0, React 19.2.3, Next 16.1.6 |
| `pnpm-workspace.yaml` | Workspace configuration | apps/*, packages/* workspace definitions |
| `turbo.json` | Turborepo pipeline configuration | Build, dev, test task definitions |
| `openapi.yml` | Root OpenAPI 3.1.0 specification | Simplified responses endpoint |
| `docker-compose.dev.yml` | Development Docker services | PostgreSQL pgvector:pg17, Valkey, MinIO, MailHog |

**Documentation Directory (`docs/`):**

| File/Folder Path | Type | Files | Purpose |
|------------------|------|-------|---------|
| `docs/docs.json` | Config | 1 | Mintlify navigation config (760 lines, 6 tabs, redirects, analytics) |
| `docs/README.md` | Guide | 1 | Local dev instructions for Mintlify CLI |
| `docs/overview/` | Content | 3 MDX | Platform introduction, overview, open source |
| `docs/xm-and-surveys/` | Content | 85 MDX | Survey features, question types, integrations, best practices |
| `docs/self-hosting/` | Content | 36 MDX | Setup, configuration, auth/SSO, advanced/enterprise |
| `docs/development/` | Content | 22 MDX | Local setup, standards, technical handbook, contributions |
| `docs/api-reference/` | Content | 43 MDX + 1 JSON | API v1 endpoint pages + OpenAPI 3.0 spec |
| `docs/api-v2-reference/` | Content | 1 MDX + 1 YAML | API v2 introduction + OpenAPI 3.1.0 spec |
| `docs/images/` | Assets | 393 files | Screenshots, diagrams, brand assets (.webp, .svg) |

**Application Directory (`apps/`):**

| Folder Path | Purpose | Documentation Relevance |
|-------------|---------|------------------------|
| `apps/web/` | Next.js 16.x production application | Primary source of truth for feature behavior |
| `apps/web/modules/` | 16 feature modules | Module-level documentation mapping |
| `apps/web/modules/survey/` | Survey engine | Survey editor, question types, templates |
| `apps/web/modules/api/` | API v2 implementation | API reference documentation |
| `apps/web/modules/auth/` | Authentication | Auth behavior and SSO docs |
| `apps/web/modules/integrations/` | Webhook and integration management | Integration guides |
| `apps/web/modules/ee/` | Enterprise features | Enterprise feature documentation |
| `apps/web/modules/analysis/` | Response analysis | Analytics documentation |
| `apps/web/modules/organization/` | Organization management | User management docs |
| `apps/web/modules/core/rate-limit/` | Rate limiting | Rate limiting self-hosting docs |
| `apps/web/lib/constants.ts` | Application constants | Environment variable reference |
| `apps/web/lib/crypto.ts` | Cryptographic operations | Encryption and webhook signing docs |
| `apps/web/instrumentation-node.ts` | OpenTelemetry setup | Monitoring documentation |
| `apps/storybook/` | Storybook 10.1.11 | Component documentation (out of scope) |

**Packages Directory (`packages/`):**

| Package Path | Purpose | Documentation Relevance |
|-------------|---------|------------------------|
| `packages/database/` | Prisma 6.14.0 schema (32 models, 21 enums) | Database model documentation |
| `packages/js-core/` | Browser SDK (7KB) | SDK quickstart and integration guides |
| `packages/surveys/` | Preact/React survey renderer | Survey embedding documentation |
| `packages/types/` | Zod validation schemas | API contract documentation |
| `packages/survey-ui/` | React UI toolkit (15 elements) | Survey UI component documentation |
| `packages/email/` | Transactional email | Email template customization docs |
| `packages/i18n-utils/` | Internationalization utilities | Multi-language documentation |
| `packages/storage/` | S3-compatible storage | File upload documentation |
| `packages/cache/` | Redis caching abstraction | Caching architecture docs |
| `packages/logger/` | Pino structured logging | Logging configuration docs |
| `packages/config-eslint/` | ESLint configuration | Code formatting standards docs |
| `packages/config-prettier/` | Prettier configuration | Code formatting standards docs |
| `packages/config-typescript/` | TypeScript configuration | Language convention docs |

**Infrastructure Files:**

| File Path | Purpose | Documentation Relevance |
|-----------|---------|------------------------|
| `docker/docker-compose.yml` | Production Docker setup | Docker self-hosting documentation |
| `docker/formbricks.sh` | One-click Ubuntu installer | One-click setup documentation |
| `docker/README.md` | Docker deployment README | Docker deployment guide reference |
| `charts/` | Helm chart directory | Kubernetes deployment documentation |
| `.github/` | CI/CD workflows (19 files) | Development workflow documentation |

### 0.11.2 Tech Spec Sections Retrieved

| Section | Key Information Extracted |
|---------|-------------------------|
| 1.1 Executive Summary | Platform identity, version 3.7.0, 2 apps + 14 packages, AGPLv3 licensing |
| 1.2 System Overview | Capabilities, component table, technical approach, 75+ env vars |
| 1.3 Scope | In-scope features, out-of-scope items, deployment methods |
| 2.1 Feature Catalog | 26 features (F-001 through F-026), categories, priorities, statuses |
| 2.2 Functional Requirements | Detailed requirements for all features with acceptance criteria |
| 3.1 Programming Languages | TypeScript sole primary language, Node.js ≥20, secondary: SQL, Bash, CSS |
| 5.1 High-Level Architecture | Five-layer architecture, data flow, external integration points |
| 6.2 Database Design | PostgreSQL 17, 32 models, 21 enums, 4 bounded domains, caching strategy |
| 6.3 Integration Architecture | Dual REST API, OAuth integrations, webhook dispatch, rate limiting, encryption |
| 7.3 Component Library | 100+ admin components, 15 survey UI elements, Storybook 10.1.11 |
| 8.5 CI/CD Pipeline | 19 workflows, 6 composite actions, quality gates, deployment pipeline |

### 0.11.3 Web Searches Conducted

| Search Query | Key Findings |
|-------------|-------------|
| "Mintlify CLI latest version 2025" | Current stable: mintlify v4.2.378 (npm), @mintlify/cli v4.0.712; Node.js ≥20.17.0 required; docs.json config format (migrated from mint.json) |
| "Formbricks documentation structure Mintlify" | Confirmed Mintlify usage, MDX file format, frontmatter requirements, documentation standards (no H1, Camel Case, Note/Warning components) |

### 0.11.4 Attachments and External Resources

No attachments were provided for this project. No Figma screens were referenced.

**External Documentation URLs (referenced in codebase):**
- Formbricks live documentation: `https://formbricks.com/docs/` (hosted via Mintlify)
- Formbricks GitHub Discussions (support): `https://github.com/formbricks/formbricks/discussions`
- Standard Webhooks Specification: `https://github.com/standard-webhooks/standard-webhooks`
- Mintlify documentation: `https://mintlify.com/docs`
- PostHog EU analytics endpoint (configured in docs.json)

