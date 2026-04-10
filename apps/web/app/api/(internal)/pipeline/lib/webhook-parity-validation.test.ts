import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import {
  TTypeformCompatiblePayload,
  ZTypeformAnswer,
  ZTypeformCompatiblePayload,
  ZTypeformFieldDefinition,
  ZTypeformVariable,
} from "@formbricks/database/zod/webhook-payload";
import { TResponse } from "@formbricks/types/responses";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/elements";
import { TSurvey } from "@formbricks/types/surveys/types";
import { transformToTypeformPayload } from "./payload-transformer";

// ---------------------------------------------------------------------------
// Mock Dependencies
// ---------------------------------------------------------------------------

vi.mock("uuid", () => ({
  v7: vi.fn(() => "validation-uuid-v7"),
}));

vi.mock("@/lib/survey/utils", () => ({
  getElementsFromBlocks: vi.fn((blocks: any[]) => blocks.flatMap((b: any) => b.elements)),
}));

// ---------------------------------------------------------------------------
// Element Question IDs — one per element type for deterministic lookups
// ---------------------------------------------------------------------------

const ELEMENT_IDS: Record<string, string> = {
  openText: "q-open-text-001",
  multipleChoiceSingle: "q-mc-single-002",
  multipleChoiceMulti: "q-mc-multi-003",
  rating: "q-rating-004",
  opinionScale: "q-opinion-scale-005",
  nps: "q-nps-006",
  consent: "q-consent-007",
  date: "q-date-008",
  fileUpload: "q-file-upload-009",
  cal: "q-cal-010",
  matrix: "q-matrix-011",
  address: "q-address-012",
  contactInfo: "q-contact-info-013",
  ranking: "q-ranking-014",
  pictureSelection: "q-picture-sel-015",
  payment: "q-payment-016",
  cta: "q-cta-017",
};

// ---------------------------------------------------------------------------
// Full Survey Fixture — ALL 17 element types across 2 blocks
// ---------------------------------------------------------------------------

const fullSurvey = {
  id: "survey-parity-validation-001",
  name: "Sprint 5 Parity Validation Survey",
  type: "link",
  status: "inProgress",
  createdAt: new Date("2026-01-15T09:00:00Z"),
  updatedAt: new Date("2026-01-15T10:30:00Z"),
  environmentId: "env-parity-001",
  blocks: [
    {
      id: "block-1",
      name: "Block 1 — Core Types",
      elements: [
        {
          id: ELEMENT_IDS.openText,
          type: TSurveyElementTypeEnum.OpenText,
          headline: { default: "What is your feedback?" },
          required: true,
          inputType: "text",
          charLimit: 2000,
          subheader: { default: "" },
          placeholder: { default: "Type here..." },
        },
        {
          id: ELEMENT_IDS.multipleChoiceSingle,
          type: TSurveyElementTypeEnum.MultipleChoiceSingle,
          headline: { default: "Pick your favorite color" },
          required: true,
          choices: [
            { id: "c1", label: { default: "Red" } },
            { id: "c2", label: { default: "Blue" } },
            { id: "c3", label: { default: "Green" } },
          ],
          shuffleOption: "none",
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.multipleChoiceMulti,
          type: TSurveyElementTypeEnum.MultipleChoiceMulti,
          headline: { default: "Select all tools you use" },
          required: true,
          choices: [
            { id: "t1", label: { default: "VS Code" } },
            { id: "t2", label: { default: "IntelliJ" } },
            { id: "t3", label: { default: "Neovim" } },
          ],
          shuffleOption: "none",
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.rating,
          type: TSurveyElementTypeEnum.Rating,
          headline: { default: "Rate our service" },
          required: true,
          scale: "star",
          range: 5,
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.opinionScale,
          type: TSurveyElementTypeEnum.OpinionScale,
          headline: { default: "How likely to recommend?" },
          required: true,
          scale: "number",
          range: 10,
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.nps,
          type: TSurveyElementTypeEnum.NPS,
          headline: { default: "Net Promoter Score" },
          required: true,
          lowerLabel: { default: "Not likely" },
          upperLabel: { default: "Very likely" },
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.consent,
          type: TSurveyElementTypeEnum.Consent,
          headline: { default: "Do you agree to the terms?" },
          required: true,
          label: { default: "I agree" },
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.date,
          type: TSurveyElementTypeEnum.Date,
          headline: { default: "Select a date" },
          required: true,
          format: "M-d-y",
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.fileUpload,
          type: TSurveyElementTypeEnum.FileUpload,
          headline: { default: "Upload your resume" },
          required: true,
          allowMultipleFiles: false,
          subheader: { default: "" },
        },
      ],
    },
    {
      id: "block-2",
      name: "Block 2 — Extended Types",
      elements: [
        {
          id: ELEMENT_IDS.cal,
          type: TSurveyElementTypeEnum.Cal,
          headline: { default: "Schedule a call" },
          required: false,
          calUserName: "demo-user",
          calHost: "cal.com",
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.matrix,
          type: TSurveyElementTypeEnum.Matrix,
          headline: { default: "Rate each category" },
          required: true,
          rows: [{ default: "Speed" }, { default: "Quality" }],
          columns: [{ default: "Poor" }, { default: "Average" }, { default: "Excellent" }],
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.address,
          type: TSurveyElementTypeEnum.Address,
          headline: { default: "Your address" },
          required: true,
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.contactInfo,
          type: TSurveyElementTypeEnum.ContactInfo,
          headline: { default: "Contact information" },
          required: true,
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.ranking,
          type: TSurveyElementTypeEnum.Ranking,
          headline: { default: "Rank these features" },
          required: true,
          choices: [
            { id: "r1", label: { default: "Performance" } },
            { id: "r2", label: { default: "Security" } },
            { id: "r3", label: { default: "Usability" } },
          ],
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.pictureSelection,
          type: TSurveyElementTypeEnum.PictureSelection,
          headline: { default: "Pick a theme" },
          required: true,
          choices: [
            { id: "pic1", imageUrl: "https://cdn.example.com/dark.png" },
            { id: "pic2", imageUrl: "https://cdn.example.com/light.png" },
          ],
          allowMulti: false,
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.payment,
          type: TSurveyElementTypeEnum.Payment,
          headline: { default: "Complete payment" },
          required: true,
          currency: "usd",
          amount: 2999,
          subheader: { default: "" },
        },
        {
          id: ELEMENT_IDS.cta,
          type: TSurveyElementTypeEnum.CTA,
          headline: { default: "Click to proceed" },
          required: true,
          buttonLabel: { default: "Continue" },
          buttonUrl: "https://formbricks.com",
          subheader: { default: "" },
        },
      ],
    },
  ],
  hiddenFields: {
    enabled: true,
    fieldIds: ["utm_source", "utm_medium"],
  },
  variables: [
    { id: "var-total-score", name: "total_score", type: "number", value: 0 },
    { id: "var-completion-note", name: "completion_note", type: "text", value: "" },
  ],
  // Required survey metadata fields
  autoClose: null,
  triggers: [],
  languages: [],
  styling: null,
  segment: null,
  recontactDays: null,
  autoComplete: null,
  displayOption: "displayOnce",
  displayPercentage: null,
  singleUse: null,
  surveyClosedMessage: null,
  pin: null,
  followUps: [],
  questions: [],
  endings: [],
  welcomeCard: { enabled: false },
  metadata: {},
} as unknown as TSurvey;

// ---------------------------------------------------------------------------
// Full Response Fixture — answers for ALL 17 element types + hidden + variables
// ---------------------------------------------------------------------------

const fullResponse = {
  id: "response-parity-001",
  surveyId: "survey-parity-validation-001",
  createdAt: new Date("2026-01-15T10:00:00Z"),
  updatedAt: new Date("2026-01-15T10:25:00Z"),
  finished: true,
  language: "en",
  contact: null,
  contactAttributes: {},
  meta: {
    url: "https://example.com/survey",
    source: "web",
    userAgent: {
      browser: "Chrome",
      os: "Windows 11",
      device: "Desktop",
    },
    country: "US",
  },
  singleUseId: null,
  personId: "person-abc-123",
  tags: [],
  displayId: null,
  data: {
    // Answers for all 17 element types
    [ELEMENT_IDS.openText]: "This is my detailed feedback about the product experience.",
    [ELEMENT_IDS.multipleChoiceSingle]: "Blue",
    [ELEMENT_IDS.multipleChoiceMulti]: ["VS Code", "Neovim"],
    [ELEMENT_IDS.rating]: 4,
    [ELEMENT_IDS.opinionScale]: 8,
    [ELEMENT_IDS.nps]: 9,
    [ELEMENT_IDS.consent]: "accepted",
    [ELEMENT_IDS.date]: "2026-03-15",
    [ELEMENT_IDS.fileUpload]: ["https://storage.example.com/resumes/file1.pdf"],
    [ELEMENT_IDS.cal]: "2026-04-01T14:00:00Z",
    [ELEMENT_IDS.matrix]: { Speed: "Excellent", Quality: "Average" },
    [ELEMENT_IDS.address]: "123 Main St, Springfield, IL 62701",
    [ELEMENT_IDS.contactInfo]: "John Doe, john@example.com, +1-555-0100",
    [ELEMENT_IDS.ranking]: ["Security", "Performance", "Usability"],
    [ELEMENT_IDS.pictureSelection]: ["pic1"],
    [ELEMENT_IDS.payment]: { status: "succeeded", amount: 2999, currency: "usd" },
    [ELEMENT_IDS.cta]: "clicked",
    // Hidden fields
    utm_source: "google",
    utm_medium: "cpc",
  },
  variables: {
    "var-total-score": 21,
    "var-completion-note": "All sections completed successfully",
  },
  ttc: {},
} as unknown as TResponse;

// ---------------------------------------------------------------------------
// Resolved Response Data — matches the pattern from route.ts line 99
// (resolveStorageUrlsInObject simply passes through in test context)
// ---------------------------------------------------------------------------

const fullResolvedData: Record<string, unknown> = {
  [ELEMENT_IDS.openText]: "This is my detailed feedback about the product experience.",
  [ELEMENT_IDS.multipleChoiceSingle]: "Blue",
  [ELEMENT_IDS.multipleChoiceMulti]: ["VS Code", "Neovim"],
  [ELEMENT_IDS.rating]: 4,
  [ELEMENT_IDS.opinionScale]: 8,
  [ELEMENT_IDS.nps]: 9,
  [ELEMENT_IDS.consent]: "accepted",
  [ELEMENT_IDS.date]: "2026-03-15",
  [ELEMENT_IDS.fileUpload]: ["https://storage.example.com/resumes/file1.pdf"],
  [ELEMENT_IDS.cal]: "2026-04-01T14:00:00Z",
  [ELEMENT_IDS.matrix]: { Speed: "Excellent", Quality: "Average" },
  [ELEMENT_IDS.address]: "123 Main St, Springfield, IL 62701",
  [ELEMENT_IDS.contactInfo]: "John Doe, john@example.com, +1-555-0100",
  [ELEMENT_IDS.ranking]: ["Security", "Performance", "Usability"],
  [ELEMENT_IDS.pictureSelection]: ["pic1"],
  [ELEMENT_IDS.payment]: { status: "succeeded", amount: 2999, currency: "usd" },
  [ELEMENT_IDS.cta]: "clicked",
  // Hidden fields in resolved data (as they would appear in response.data)
  utm_source: "google",
  utm_medium: "cpc",
};

// ---------------------------------------------------------------------------
// Test Suite — Webhook Parity Validation (Sprint 5 End-to-End)
// ---------------------------------------------------------------------------

describe("Webhook Parity Validation — Sprint 5 End-to-End", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // =========================================================================
  // 3.1 — Full Schema Validation
  // =========================================================================
  describe("full payload schema validation", () => {
    test("should produce a payload that validates against ZTypeformCompatiblePayload", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const result = ZTypeformCompatiblePayload.safeParse(payload);
      expect(result.success).toBe(true);
      if (!result.success) {
        console.error("Validation errors:", result.error.flatten());
      }
    });

    test("should contain all required top-level fields", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(payload).toHaveProperty("event_id");
      expect(payload).toHaveProperty("event_type");
      expect(payload).toHaveProperty("form_id");
      expect(payload).toHaveProperty("landed_at");
      expect(payload).toHaveProperty("submitted_at");
      expect(payload).toHaveProperty("definition");
      expect(payload).toHaveProperty("answers");
      expect(payload).toHaveProperty("hidden");
      expect(payload).toHaveProperty("variables");
      expect(payload).toHaveProperty("calculated");
    });

    test("event_id should be a non-empty string (UUID v7)", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(typeof payload.event_id).toBe("string");
      expect(payload.event_id.length).toBeGreaterThan(0);
    });

    test("event_type should be 'form_response'", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(payload.event_type).toBe("form_response");
    });

    test("form_id should match survey ID", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(payload.form_id).toBe(fullSurvey.id);
    });

    test("landed_at should be a valid ISO 8601 timestamp", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(typeof payload.landed_at).toBe("string");
      const parsed = new Date(payload.landed_at);
      expect(parsed.toISOString()).toBe(payload.landed_at);
    });

    test("submitted_at should be a valid ISO 8601 timestamp", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(typeof payload.submitted_at).toBe("string");
      const parsed = new Date(payload.submitted_at);
      expect(parsed.toISOString()).toBe(payload.submitted_at);
    });
  });

  // =========================================================================
  // 3.2 — Typed Answers Array Validation
  // =========================================================================
  describe("typed answers array structural equivalence", () => {
    test("should produce an answers array with entries for each answered question", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      // 17 element types with answers, hidden fields excluded from answers
      expect(payload.answers.length).toBe(17);
    });

    test("each answer should validate against ZTypeformAnswer", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      payload.answers.forEach((answer: TTypeformCompatiblePayload["answers"][number], idx: number) => {
        const result = ZTypeformAnswer.safeParse(answer);
        expect(result.success).toBe(true);
        if (!result.success) {
          console.error(`Answer ${idx} validation failed:`, result.error.flatten());
        }
      });
    });

    test("each answer should have field.id, field.type, and field.ref", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      payload.answers.forEach((answer: TTypeformCompatiblePayload["answers"][number]) => {
        expect(answer.field).toHaveProperty("id");
        expect(answer.field).toHaveProperty("type");
        expect(answer.field).toHaveProperty("ref");
        expect(typeof answer.field.id).toBe("string");
        expect(typeof answer.field.type).toBe("string");
        expect(typeof answer.field.ref).toBe("string");
      });
    });

    test("each answer should have at least one type-specific value field", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const valueFields = [
        "text",
        "number",
        "boolean",
        "choice",
        "choices",
        "date",
        "email",
        "url",
        "file_url",
        "payment",
      ];
      payload.answers.forEach((answer: TTypeformCompatiblePayload["answers"][number]) => {
        const presentFields = valueFields.filter((f) => (answer as Record<string, unknown>)[f] !== undefined);
        expect(presentFields.length).toBeGreaterThanOrEqual(1);
      });
    });

    test("answer type field should match the type-specific value key", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      payload.answers.forEach((answer: TTypeformCompatiblePayload["answers"][number]) => {
        // The "type" field should correspond to the non-undefined value field
        expect((answer as Record<string, unknown>)[answer.type]).toBeDefined();
      });
    });

    test("field.ref should equal field.id for all answers", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      payload.answers.forEach((answer: TTypeformCompatiblePayload["answers"][number]) => {
        expect(answer.field.ref).toBe(answer.field.id);
      });
    });
  });

  // =========================================================================
  // 3.3 — Element-to-Answer Type Mapping Verification
  // =========================================================================
  describe("element type to Typeform answer type mapping", () => {
    const expectedMappings: Record<string, string> = {
      openText: "text",
      multipleChoiceSingle: "choice",
      multipleChoiceMulti: "choices",
      rating: "number",
      opinionScale: "number",
      nps: "number",
      consent: "boolean",
      date: "date",
      fileUpload: "file_url",
      cal: "text",
      matrix: "text",
      address: "text",
      contactInfo: "text",
      ranking: "choices",
      pictureSelection: "choice",
      payment: "payment",
      cta: "boolean",
    };

    test.each(Object.entries(expectedMappings))(
      "should map %s element to %s answer type",
      (elementType: string, expectedAnswerType: string) => {
        const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
        const fieldId = ELEMENT_IDS[elementType];
        const answer = payload.answers.find(
          (a: TTypeformCompatiblePayload["answers"][number]) => a.field.id === fieldId
        );
        expect(answer).toBeDefined();
        expect(answer?.type).toBe(expectedAnswerType);
      }
    );
  });

  // =========================================================================
  // 3.4 — Definition Fields Validation
  // =========================================================================
  describe("definition.fields array validation", () => {
    test("should include all survey elements in definition.fields", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(payload.definition.fields.length).toBe(17);
    });

    test("each field should validate against ZTypeformFieldDefinition", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      payload.definition.fields.forEach(
        (field: TTypeformCompatiblePayload["definition"]["fields"][number], idx: number) => {
          const result = ZTypeformFieldDefinition.safeParse(field);
          expect(result.success).toBe(true);
          if (!result.success) {
            console.error(`Field ${idx} validation failed:`, result.error.flatten());
          }
        }
      );
    });

    test("definition.id should match the survey ID", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(payload.definition.id).toBe(fullSurvey.id);
    });

    test("definition.title should match the survey name", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(payload.definition.title).toBe(fullSurvey.name);
    });

    test("each field should have id matching a survey element id", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const elementIds = (
        fullSurvey as unknown as { blocks: Array<{ elements: Array<{ id: string }> }> }
      ).blocks.flatMap((b) => b.elements.map((e) => e.id));
      payload.definition.fields.forEach(
        (field: TTypeformCompatiblePayload["definition"]["fields"][number]) => {
          expect(elementIds).toContain(field.id);
        }
      );
    });

    test("each field should have a non-empty title string", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      payload.definition.fields.forEach(
        (field: TTypeformCompatiblePayload["definition"]["fields"][number]) => {
          expect(typeof field.title).toBe("string");
          expect(field.title.length).toBeGreaterThan(0);
        }
      );
    });

    test("each field should have a non-empty type string", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      payload.definition.fields.forEach(
        (field: TTypeformCompatiblePayload["definition"]["fields"][number]) => {
          expect(typeof field.type).toBe("string");
          expect(field.type.length).toBeGreaterThan(0);
        }
      );
    });

    test("each field should have a ref matching its id", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      payload.definition.fields.forEach(
        (field: TTypeformCompatiblePayload["definition"]["fields"][number]) => {
          expect(field.ref).toBe(field.id);
        }
      );
    });
  });

  // =========================================================================
  // 3.5 — Hidden Object Separation Validation
  // =========================================================================
  describe("hidden object separation validation", () => {
    test("should separate hidden fields into the hidden object", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(payload.hidden).toHaveProperty("utm_source");
      expect(payload.hidden).toHaveProperty("utm_medium");
    });

    test("hidden field values should match response data", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(payload.hidden.utm_source).toBe(String(fullResolvedData.utm_source));
      expect(payload.hidden.utm_medium).toBe(String(fullResolvedData.utm_medium));
    });

    test("hidden fields should NOT appear in the answers array", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const hiddenIds =
        (fullSurvey as unknown as { hiddenFields?: { fieldIds?: string[] } }).hiddenFields?.fieldIds ?? [];
      const answerFieldIds = payload.answers.map(
        (a: TTypeformCompatiblePayload["answers"][number]) => a.field.id
      );
      hiddenIds.forEach((hfId: string) => {
        expect(answerFieldIds).not.toContain(hfId);
      });
    });

    test("hidden object should be a flat key-value map of strings", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(typeof payload.hidden).toBe("object");
      expect(Array.isArray(payload.hidden)).toBe(false);
      Object.entries(payload.hidden).forEach(([key, value]) => {
        expect(typeof key).toBe("string");
        expect(typeof value).toBe("string");
      });
    });
  });

  // =========================================================================
  // 3.6 — Variables Array Typing Validation
  // =========================================================================
  describe("variables array typing validation", () => {
    test("should restructure variables into typed array", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(payload.variables.length).toBe(2);
    });

    test("each variable should validate against ZTypeformVariable", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      payload.variables.forEach((variable: TTypeformCompatiblePayload["variables"][number], idx: number) => {
        const result = ZTypeformVariable.safeParse(variable);
        expect(result.success).toBe(true);
        if (!result.success) {
          console.error(`Variable ${idx} validation failed:`, result.error.flatten());
        }
      });
    });

    test("number variables should have type 'number' and a numeric value", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const numVar = payload.variables.find(
        (v: TTypeformCompatiblePayload["variables"][number]) => v.type === "number"
      );
      expect(numVar).toBeDefined();
      expect(numVar?.number).toBeDefined();
      expect(typeof numVar?.number).toBe("number");
    });

    test("text variables should have type 'text' and a string value", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const textVar = payload.variables.find(
        (v: TTypeformCompatiblePayload["variables"][number]) => v.type === "text"
      );
      expect(textVar).toBeDefined();
      expect(textVar?.text).toBeDefined();
      expect(typeof textVar?.text).toBe("string");
    });

    test("each variable should have a key property matching the variable name", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const variableKeys = payload.variables.map(
        (v: TTypeformCompatiblePayload["variables"][number]) => v.key
      );
      expect(variableKeys).toContain("total_score");
      expect(variableKeys).toContain("completion_note");
    });
  });

  // =========================================================================
  // 3.7 — Calculated Score Validation
  // =========================================================================
  describe("calculated.score field validation", () => {
    test("should include a calculated object with a score number", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      expect(payload.calculated).toHaveProperty("score");
      expect(typeof payload.calculated.score).toBe("number");
    });

    test("score should aggregate numeric element values (rating + opinionScale + nps)", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      // rating=4, opinionScale=8, nps=9 → expected score = 21
      expect(payload.calculated.score).toBe(21);
    });

    test("score should be 0 when no numeric element responses exist", () => {
      const surveyNoNumeric = {
        ...fullSurvey,
        blocks: [
          {
            id: "block-no-numeric",
            name: "Block No Numeric",
            elements: [
              {
                id: "q-text-only",
                type: TSurveyElementTypeEnum.OpenText,
                headline: { default: "Text only" },
                required: true,
                inputType: "text",
              },
            ],
          },
        ],
      } as unknown as TSurvey;
      const responseNoNumeric = {
        ...fullResponse,
        data: { "q-text-only": "Just text" },
        variables: {},
      } as unknown as TResponse;
      const resolvedNoNumeric: Record<string, unknown> = { "q-text-only": "Just text" };

      const payload = transformToTypeformPayload(responseNoNumeric, surveyNoNumeric, resolvedNoNumeric);
      expect(payload.calculated.score).toBe(0);
    });
  });

  // =========================================================================
  // 3.8 — Full Pipeline Integration Test
  // =========================================================================
  describe("full pipeline integration", () => {
    test("complete payload should match Typeform webhook structure", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);

      // Verify top-level structure
      expect(payload.event_type).toBe("form_response");
      expect(payload.form_id).toBe(fullSurvey.id);

      // Verify definition contains form metadata
      expect(payload.definition.id).toBe(fullSurvey.id);
      expect(payload.definition.title).toBe(fullSurvey.name);
      expect(payload.definition.fields).toBeInstanceOf(Array);

      // Verify answers is an array of typed objects
      expect(payload.answers).toBeInstanceOf(Array);
      expect(payload.answers.length).toBeGreaterThan(0);

      // Verify hidden is a flat key-value object
      expect(typeof payload.hidden).toBe("object");
      expect(Array.isArray(payload.hidden)).toBe(false);

      // Verify variables is a typed array
      expect(payload.variables).toBeInstanceOf(Array);

      // Verify calculated has score
      expect(payload.calculated).toHaveProperty("score");

      // Full schema validation — must not throw
      expect(() => ZTypeformCompatiblePayload.parse(payload)).not.toThrow();
    });

    test("payload should roundtrip through parse() producing identical structure", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const parsed = ZTypeformCompatiblePayload.parse(payload);

      expect(parsed.event_id).toBe(payload.event_id);
      expect(parsed.event_type).toBe(payload.event_type);
      expect(parsed.form_id).toBe(payload.form_id);
      expect(parsed.landed_at).toBe(payload.landed_at);
      expect(parsed.submitted_at).toBe(payload.submitted_at);
      expect(parsed.definition.id).toBe(payload.definition.id);
      expect(parsed.definition.title).toBe(payload.definition.title);
      expect(parsed.definition.fields.length).toBe(payload.definition.fields.length);
      expect(parsed.answers.length).toBe(payload.answers.length);
      expect(parsed.variables.length).toBe(payload.variables.length);
      expect(parsed.calculated.score).toBe(payload.calculated.score);
      expect(Object.keys(parsed.hidden).length).toBe(Object.keys(payload.hidden).length);
    });
  });

  // =========================================================================
  // 3.9 — Edge Cases and Boundary Conditions
  // =========================================================================
  describe("edge cases and boundary conditions", () => {
    test("should handle survey with empty hidden fields gracefully", () => {
      const surveyNoHidden = {
        ...fullSurvey,
        hiddenFields: { enabled: true, fieldIds: [] },
      } as unknown as TSurvey;

      const resolvedNoHidden: Record<string, unknown> = { ...fullResolvedData };
      delete resolvedNoHidden.utm_source;
      delete resolvedNoHidden.utm_medium;

      const payload = transformToTypeformPayload(fullResponse, surveyNoHidden, resolvedNoHidden);
      expect(Object.keys(payload.hidden).length).toBe(0);
      const result = ZTypeformCompatiblePayload.safeParse(payload);
      expect(result.success).toBe(true);
    });

    test("should handle survey with no variables gracefully", () => {
      const surveyNoVars = {
        ...fullSurvey,
        variables: [],
      } as unknown as TSurvey;

      const payload = transformToTypeformPayload(fullResponse, surveyNoVars, fullResolvedData);
      expect(payload.variables.length).toBe(0);
      const result = ZTypeformCompatiblePayload.safeParse(payload);
      expect(result.success).toBe(true);
    });

    test("should handle response with empty data object", () => {
      const emptyDataResponse = {
        ...fullResponse,
        data: {},
        variables: {},
      } as unknown as TResponse;

      const payload = transformToTypeformPayload(emptyDataResponse, fullSurvey, {});
      expect(payload.answers.length).toBe(0);
      expect(payload.hidden).toEqual({});
      expect(payload.variables.length).toBe(0);
      expect(payload.calculated.score).toBe(0);
      const result = ZTypeformCompatiblePayload.safeParse(payload);
      expect(result.success).toBe(true);
    });

    test("should handle consent element with 'accepted' response as boolean true", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const consentAnswer = payload.answers.find(
        (a: TTypeformCompatiblePayload["answers"][number]) => a.field.id === ELEMENT_IDS.consent
      );
      expect(consentAnswer).toBeDefined();
      expect(consentAnswer?.type).toBe("boolean");
      expect((consentAnswer as Record<string, unknown>).boolean).toBe(true);
    });

    test("should handle cta element with 'clicked' response as boolean true", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const ctaAnswer = payload.answers.find(
        (a: TTypeformCompatiblePayload["answers"][number]) => a.field.id === ELEMENT_IDS.cta
      );
      expect(ctaAnswer).toBeDefined();
      expect(ctaAnswer?.type).toBe("boolean");
      expect((ctaAnswer as Record<string, unknown>).boolean).toBe(true);
    });

    test("should handle matrix element by serializing object response to JSON text", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const matrixAnswer = payload.answers.find(
        (a: TTypeformCompatiblePayload["answers"][number]) => a.field.id === ELEMENT_IDS.matrix
      );
      expect(matrixAnswer).toBeDefined();
      expect(matrixAnswer?.type).toBe("text");
      // Matrix values should be JSON-stringified
      const textValue = (matrixAnswer as Record<string, unknown>).text as string;
      expect(typeof textValue).toBe("string");
      const parsed = JSON.parse(textValue);
      expect(parsed).toEqual({ Speed: "Excellent", Quality: "Average" });
    });

    test("should handle fileUpload by extracting first URL from array", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const fileAnswer = payload.answers.find(
        (a: TTypeformCompatiblePayload["answers"][number]) => a.field.id === ELEMENT_IDS.fileUpload
      );
      expect(fileAnswer).toBeDefined();
      expect(fileAnswer?.type).toBe("file_url");
      expect((fileAnswer as Record<string, unknown>).file_url).toBe(
        "https://storage.example.com/resumes/file1.pdf"
      );
    });

    test("should handle payment element with structured payment data", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const paymentAnswer = payload.answers.find(
        (a: TTypeformCompatiblePayload["answers"][number]) => a.field.id === ELEMENT_IDS.payment
      );
      expect(paymentAnswer).toBeDefined();
      expect(paymentAnswer?.type).toBe("payment");
      const paymentData = (paymentAnswer as Record<string, unknown>).payment as Record<string, unknown>;
      expect(paymentData).toBeDefined();
      expect(paymentData.amount).toBe("2999");
      expect(paymentData.currency).toBe("usd");
      expect(paymentData.status).toBe("succeeded");
    });

    test("should handle pictureSelection single-select as choice type", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const picAnswer = payload.answers.find(
        (a: TTypeformCompatiblePayload["answers"][number]) => a.field.id === ELEMENT_IDS.pictureSelection
      );
      expect(picAnswer).toBeDefined();
      expect(picAnswer?.type).toBe("choice");
      const choiceData = (picAnswer as Record<string, unknown>).choice as Record<string, unknown>;
      expect(choiceData).toBeDefined();
      expect(choiceData.label).toBe("pic1");
    });

    test("should handle ranking as choices type with labels array", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const rankAnswer = payload.answers.find(
        (a: TTypeformCompatiblePayload["answers"][number]) => a.field.id === ELEMENT_IDS.ranking
      );
      expect(rankAnswer).toBeDefined();
      expect(rankAnswer?.type).toBe("choices");
      const choicesData = (rankAnswer as Record<string, unknown>).choices as Record<string, unknown>;
      expect(choicesData).toBeDefined();
      expect(choicesData.labels).toEqual(["Security", "Performance", "Usability"]);
    });
  });

  // =========================================================================
  // 3.10 — Cross-validation: answers count matches definition.fields count
  //        (minus unanswered questions)
  // =========================================================================
  describe("structural consistency cross-checks", () => {
    test("answers array field ids should be a subset of definition.fields ids", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const definitionFieldIds = payload.definition.fields.map(
        (f: TTypeformCompatiblePayload["definition"]["fields"][number]) => f.id
      );
      payload.answers.forEach((answer: TTypeformCompatiblePayload["answers"][number]) => {
        expect(definitionFieldIds).toContain(answer.field.id);
      });
    });

    test("no duplicate field ids in definition.fields", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const fieldIds = payload.definition.fields.map(
        (f: TTypeformCompatiblePayload["definition"]["fields"][number]) => f.id
      );
      const uniqueIds = new Set(fieldIds);
      expect(uniqueIds.size).toBe(fieldIds.length);
    });

    test("no duplicate field ids in answers array", () => {
      const payload = transformToTypeformPayload(fullResponse, fullSurvey, fullResolvedData);
      const answerFieldIds = payload.answers.map(
        (a: TTypeformCompatiblePayload["answers"][number]) => a.field.id
      );
      const uniqueIds = new Set(answerFieldIds);
      expect(uniqueIds.size).toBe(answerFieldIds.length);
    });
  });
});
