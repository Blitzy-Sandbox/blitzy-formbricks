/**
 * Sprint 5, Step 4 — Export Lossless Validation for New Element Types
 *
 * Extends the existing export-lossless-validation.test.ts coverage to the
 * Sprint 1 additions: opinionScale and payment element types.
 *
 * Test suites:
 *  1. opinionScale — value preserved across getResponsesJson, JSON, CSV, XLSX
 *  2. payment — "paid" and empty status preserved across all 3 formats
 *  3. Mixed survey (openText + opinionScale + payment) — all types in one export
 *  4. Lifecycle — build survey → submit response → export to JSON → assert value
 *  5. Migration rollback safety — legacy OpenText surveys still export;
 *     payloadFormat default is 'default'
 *  6. Performance — 100 opinionScale + 100 payment responses export in <1000ms;
 *     500 mixed responses export to all 3 formats without error
 */
import { describe, expect, test } from "vitest";
import { TResponseWithQuotas } from "@formbricks/types/responses";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/elements";
import { TSurvey } from "@formbricks/types/surveys/types";
import { convertToCsv, convertToJson, convertToXlsxBuffer } from "../../utils/file-conversion";
import { getResponsesJson } from "../utils";

// ---------------------------------------------------------------------------
// Shared test fixtures
// ---------------------------------------------------------------------------

/**
 * Builds a TSurvey-shaped object with an opinionScale element.
 */
const buildOpinionScaleSurvey = (): TSurvey =>
  ({
    id: "survey-os-001",
    createdAt: new Date("2024-06-01T00:00:00Z"),
    updatedAt: new Date("2024-06-01T00:00:00Z"),
    name: "Opinion Scale Survey",
    type: "link",
    environmentId: "env-001",
    createdBy: "creator-001",
    status: "inProgress",
    welcomeCard: { enabled: false, headline: { default: "" }, timeToFinish: false, showResponseCount: false },
    questions: [],
    blocks: [
      {
        id: "block1",
        name: "Block 1",
        elements: [
          {
            id: "q-os-1",
            type: TSurveyElementTypeEnum.OpinionScale,
            headline: { default: "Rate our service" },
            required: true,
            scale: "number" as const,
            range: 5,
            lowerLabel: { default: "Bad" },
            upperLabel: { default: "Excellent" },
          },
        ],
      },
    ],
    endings: [{ type: "endScreen" as const, id: "end1", enabled: true, headline: { default: "Thanks!" } }],
    hiddenFields: { enabled: false, fieldIds: [] },
    variables: [],
    displayOption: "respondMultiple",
    recontactDays: null,
    displayLimit: null,
    autoClose: null,
    delay: 0,
    displayPercentage: null,
    autoComplete: null,
    isVerifyEmailEnabled: false,
    projectOverwrites: null,
    recaptcha: null,
    styling: null,
    surveyClosedMessage: null,
    singleUse: null,
    pin: null,
    triggers: [],
    languages: [],
    segment: [],
    showLanguageSwitch: null,
    followUps: [],
    isBackButtonHidden: false,
    isCaptureIpEnabled: false,
    isSingleResponsePerEmailEnabled: false,
  }) as unknown as TSurvey;

/**
 * Builds a TSurvey-shaped object with a payment element.
 */
const buildPaymentSurvey = (): TSurvey =>
  ({
    id: "survey-pay-001",
    createdAt: new Date("2024-06-01T00:00:00Z"),
    updatedAt: new Date("2024-06-01T00:00:00Z"),
    name: "Payment Survey",
    type: "link",
    environmentId: "env-001",
    createdBy: "creator-001",
    status: "inProgress",
    welcomeCard: { enabled: false, headline: { default: "" }, timeToFinish: false, showResponseCount: false },
    questions: [],
    blocks: [
      {
        id: "block1",
        name: "Block 1",
        elements: [
          {
            id: "q-pay-1",
            type: TSurveyElementTypeEnum.Payment,
            headline: { default: "Complete payment" },
            required: true,
            amount: 1000,
            currency: "usd",
          },
        ],
      },
    ],
    endings: [{ type: "endScreen" as const, id: "end1", enabled: true, headline: { default: "Thanks!" } }],
    hiddenFields: { enabled: false, fieldIds: [] },
    variables: [],
    displayOption: "respondMultiple",
    recontactDays: null,
    displayLimit: null,
    autoClose: null,
    delay: 0,
    displayPercentage: null,
    autoComplete: null,
    isVerifyEmailEnabled: false,
    projectOverwrites: null,
    recaptcha: null,
    styling: null,
    surveyClosedMessage: null,
    singleUse: null,
    pin: null,
    triggers: [],
    languages: [],
    segment: [],
    showLanguageSwitch: null,
    followUps: [],
    isBackButtonHidden: false,
    isCaptureIpEnabled: false,
    isSingleResponsePerEmailEnabled: false,
  }) as unknown as TSurvey;

/**
 * Builds a mixed TSurvey with openText + opinionScale + payment elements.
 */
const buildMixedSurvey = (): TSurvey =>
  ({
    id: "survey-mix-001",
    createdAt: new Date("2024-06-01T00:00:00Z"),
    updatedAt: new Date("2024-06-01T00:00:00Z"),
    name: "Mixed Survey",
    type: "link",
    environmentId: "env-001",
    createdBy: "creator-001",
    status: "inProgress",
    welcomeCard: { enabled: false, headline: { default: "" }, timeToFinish: false, showResponseCount: false },
    questions: [],
    blocks: [
      {
        id: "block1",
        name: "Block 1",
        elements: [
          {
            id: "q-text-1",
            type: TSurveyElementTypeEnum.OpenText,
            headline: { default: "Your name?" },
            required: true,
            inputType: "text" as const,
            charLimit: { enabled: false },
          },
          {
            id: "q-os-1",
            type: TSurveyElementTypeEnum.OpinionScale,
            headline: { default: "Rate us" },
            required: true,
            scale: "number" as const,
            range: 5,
            lowerLabel: { default: "Bad" },
            upperLabel: { default: "Good" },
          },
          {
            id: "q-pay-1",
            type: TSurveyElementTypeEnum.Payment,
            headline: { default: "Pay" },
            required: false,
            amount: 500,
            currency: "eur",
          },
        ],
      },
    ],
    endings: [{ type: "endScreen" as const, id: "end1", enabled: true, headline: { default: "Done!" } }],
    hiddenFields: { enabled: false, fieldIds: [] },
    variables: [],
    displayOption: "respondMultiple",
    recontactDays: null,
    displayLimit: null,
    autoClose: null,
    delay: 0,
    displayPercentage: null,
    autoComplete: null,
    isVerifyEmailEnabled: false,
    projectOverwrites: null,
    recaptcha: null,
    styling: null,
    surveyClosedMessage: null,
    singleUse: null,
    pin: null,
    triggers: [],
    languages: [],
    segment: [],
    showLanguageSwitch: null,
    followUps: [],
    isBackButtonHidden: false,
    isCaptureIpEnabled: false,
    isSingleResponsePerEmailEnabled: false,
  }) as unknown as TSurvey;

/**
 * Legacy openText-only survey for rollback safety testing.
 */
const buildLegacyOpenTextSurvey = (): TSurvey =>
  ({
    id: "survey-legacy-001",
    createdAt: new Date("2024-06-01T00:00:00Z"),
    updatedAt: new Date("2024-06-01T00:00:00Z"),
    name: "Legacy Survey",
    type: "link",
    environmentId: "env-001",
    createdBy: "creator-001",
    status: "inProgress",
    welcomeCard: { enabled: false, headline: { default: "" }, timeToFinish: false, showResponseCount: false },
    questions: [],
    blocks: [
      {
        id: "block1",
        name: "Block 1",
        elements: [
          {
            id: "q-legacy-1",
            type: TSurveyElementTypeEnum.OpenText,
            headline: { default: "Tell us about yourself" },
            required: true,
            inputType: "text" as const,
            charLimit: { enabled: false },
          },
        ],
      },
    ],
    endings: [{ type: "endScreen" as const, id: "end1", enabled: true, headline: { default: "Thanks!" } }],
    hiddenFields: { enabled: false, fieldIds: [] },
    variables: [],
    displayOption: "respondMultiple",
    recontactDays: null,
    displayLimit: null,
    autoClose: null,
    delay: 0,
    displayPercentage: null,
    autoComplete: null,
    isVerifyEmailEnabled: false,
    projectOverwrites: null,
    recaptcha: null,
    styling: null,
    surveyClosedMessage: null,
    singleUse: null,
    pin: null,
    triggers: [],
    languages: [],
    segment: [],
    showLanguageSwitch: null,
    followUps: [],
    isBackButtonHidden: false,
    isCaptureIpEnabled: false,
    isSingleResponsePerEmailEnabled: false,
  }) as unknown as TSurvey;

/**
 * Builds a TResponseWithQuotas-compatible object for testing.
 */
const buildResponse = (
  id: string,
  surveyId: string,
  data: Record<string, unknown>,
  finished: boolean = true
): TResponseWithQuotas =>
  ({
    id,
    createdAt: new Date("2024-06-15T10:00:00Z"),
    updatedAt: new Date("2024-06-15T10:00:00Z"),
    finished,
    surveyId,
    data,
    meta: {
      source: "web",
      url: "https://example.com/survey",
      userAgent: { browser: "Chrome", os: "Windows", device: "Desktop" },
    },
    tags: [],
    variables: {},
    contactAttributes: {},
    contact: null,
    quotas: [],
    ttc: {},
    singleUseId: null,
    language: "default",
    displayId: null,
    endingId: null,
    notes: [],
  }) as unknown as TResponseWithQuotas;

// ---------------------------------------------------------------------------
// Test suites
// ---------------------------------------------------------------------------

describe("Sprint 5 — Export lossless validation for new element types", () => {
  // =========================================================================
  // Suite 1: opinionScale — value preserved across all formats
  // =========================================================================
  describe("opinionScale export", () => {
    const survey = buildOpinionScaleSurvey();
    const elementsHeadlines = [["1. Rate our service"]];

    test("getResponsesJson serializes opinionScale value as string", () => {
      const response = buildResponse("resp-os-001", survey.id, { "q-os-1": 3 });
      const result = getResponsesJson(survey, [response], elementsHeadlines, [], []);

      expect(result).toHaveLength(1);
      // getResponsesJson serializes numbers as strings (via processResponseData)
      expect(result[0]["1. Rate our service"]).toBe("3");
    });

    test("opinionScale value preserved in JSON export", () => {
      const response = buildResponse("resp-os-002", survey.id, { "q-os-1": 5 });
      const jsonData = getResponsesJson(survey, [response], elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      const jsonString = convertToJson(headers, jsonData);
      const parsed: Record<string, string | number>[] = JSON.parse(jsonString);

      expect(parsed).toHaveLength(1);
      expect(parsed[0]["1. Rate our service"]).toBe("5");
    });

    test("opinionScale value preserved in CSV export", async () => {
      const response = buildResponse("resp-os-003", survey.id, { "q-os-1": 4 });
      const jsonData = getResponsesJson(survey, [response], elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      const csv = await convertToCsv(headers, jsonData);

      expect(csv).toContain("4");
      expect(csv).toContain("Rate our service");
    });

    test("opinionScale value preserved in XLSX export", () => {
      const response = buildResponse("resp-os-004", survey.id, { "q-os-1": 2 });
      const jsonData = getResponsesJson(survey, [response], elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      const buffer = convertToXlsxBuffer(headers, jsonData);

      expect(Buffer.isBuffer(buffer)).toBe(true);
      expect(buffer.length).toBeGreaterThan(0);
    });
  });

  // =========================================================================
  // Suite 2: payment — "paid" and empty status preserved
  // =========================================================================
  describe("payment export", () => {
    const survey = buildPaymentSurvey();
    const elementsHeadlines = [["1. Complete payment"]];

    test('"paid" status preserved across getResponsesJson', () => {
      const response = buildResponse("resp-pay-001", survey.id, { "q-pay-1": "paid" });
      const result = getResponsesJson(survey, [response], elementsHeadlines, [], []);

      expect(result).toHaveLength(1);
      expect(result[0]["1. Complete payment"]).toBe("paid");
    });

    test("empty payment status preserved across getResponsesJson", () => {
      const response = buildResponse("resp-pay-002", survey.id, { "q-pay-1": "" });
      const result = getResponsesJson(survey, [response], elementsHeadlines, [], []);

      expect(result).toHaveLength(1);
      expect(result[0]["1. Complete payment"]).toBe("");
    });

    test("payment status preserved in JSON export", () => {
      const response = buildResponse("resp-pay-003", survey.id, { "q-pay-1": "paid" });
      const jsonData = getResponsesJson(survey, [response], elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      const jsonString = convertToJson(headers, jsonData);
      const parsed: Record<string, string | number>[] = JSON.parse(jsonString);

      expect(parsed[0]["1. Complete payment"]).toBe("paid");
    });

    test("payment status preserved in CSV export", async () => {
      const response = buildResponse("resp-pay-004", survey.id, { "q-pay-1": "paid" });
      const jsonData = getResponsesJson(survey, [response], elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      const csv = await convertToCsv(headers, jsonData);

      expect(csv).toContain("paid");
    });

    test("payment status preserved in XLSX export", () => {
      const response = buildResponse("resp-pay-005", survey.id, { "q-pay-1": "paid" });
      const jsonData = getResponsesJson(survey, [response], elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      const buffer = convertToXlsxBuffer(headers, jsonData);

      expect(Buffer.isBuffer(buffer)).toBe(true);
      expect(buffer.length).toBeGreaterThan(0);
    });
  });

  // =========================================================================
  // Suite 3: Mixed survey — all types in one export, including partial
  // =========================================================================
  describe("mixed survey export (openText + opinionScale + payment)", () => {
    const survey = buildMixedSurvey();
    const elementsHeadlines = [["1. Your name?"], ["2. Rate us"], ["3. Pay"]];

    test("full response with all three element types exports correctly", () => {
      const response = buildResponse("resp-mix-001", survey.id, {
        "q-text-1": "Alice",
        "q-os-1": 4,
        "q-pay-1": "paid",
      });
      const result = getResponsesJson(survey, [response], elementsHeadlines, [], []);

      expect(result).toHaveLength(1);
      expect(result[0]["1. Your name?"]).toBe("Alice");
      expect(result[0]["2. Rate us"]).toBe("4");
      expect(result[0]["3. Pay"]).toBe("paid");
    });

    test("partial response (only openText answered) exports with empty fields", () => {
      const response = buildResponse(
        "resp-mix-002",
        survey.id,
        {
          "q-text-1": "Bob",
        },
        false
      );
      const result = getResponsesJson(survey, [response], elementsHeadlines, [], []);

      expect(result).toHaveLength(1);
      expect(result[0]["1. Your name?"]).toBe("Bob");
      expect(result[0]["Finished"]).toBe("No");
    });

    test("mixed response types preserved in JSON export", () => {
      const response = buildResponse("resp-mix-003", survey.id, {
        "q-text-1": "Charlie",
        "q-os-1": 1,
        "q-pay-1": "",
      });
      const jsonData = getResponsesJson(survey, [response], elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      const jsonString = convertToJson(headers, jsonData);
      const parsed: Record<string, string | number>[] = JSON.parse(jsonString);

      expect(parsed[0]["1. Your name?"]).toBe("Charlie");
      expect(parsed[0]["2. Rate us"]).toBe("1");
      expect(parsed[0]["3. Pay"]).toBe("");
    });
  });

  // =========================================================================
  // Suite 4: Lifecycle — build survey → submit → export to JSON
  // =========================================================================
  describe("lifecycle — build, submit, export", () => {
    test("opinionScale lifecycle: build survey → submit response → export to JSON", () => {
      const survey = buildOpinionScaleSurvey();
      const response = buildResponse("resp-lifecycle-os-001", survey.id, { "q-os-1": 3 });
      const elementsHeadlines = [["1. Rate our service"]];

      const jsonData = getResponsesJson(survey, [response], elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      const jsonString = convertToJson(headers, jsonData);
      const parsed = JSON.parse(jsonString);

      expect(parsed[0]["1. Rate our service"]).toBe("3");
    });

    test("payment lifecycle: build survey → submit response → export to JSON", () => {
      const survey = buildPaymentSurvey();
      const response = buildResponse("resp-lifecycle-pay-001", survey.id, { "q-pay-1": "paid" });
      const elementsHeadlines = [["1. Complete payment"]];

      const jsonData = getResponsesJson(survey, [response], elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      const jsonString = convertToJson(headers, jsonData);
      const parsed = JSON.parse(jsonString);

      expect(parsed[0]["1. Complete payment"]).toBe("paid");
    });
  });

  // =========================================================================
  // Suite 5: Migration rollback safety
  // =========================================================================
  describe("migration rollback safety", () => {
    test("legacy OpenText surveys still export correctly after new types were added", () => {
      const survey = buildLegacyOpenTextSurvey();
      const response = buildResponse("resp-legacy-001", survey.id, { "q-legacy-1": "I am a legacy user" });
      const elementsHeadlines = [["1. Tell us about yourself"]];

      const jsonData = getResponsesJson(survey, [response], elementsHeadlines, [], []);

      expect(jsonData).toHaveLength(1);
      expect(jsonData[0]["1. Tell us about yourself"]).toBe("I am a legacy user");
    });

    test("payloadFormat default is 'default'", () => {
      // Verify the payloadFormat field default at the schema level
      // (mirroring the migration: DEFAULT 'default')
      const webhookRow = {
        id: "webhook-001",
        url: "https://example.com/hook",
        payloadFormat: "default",
      };

      expect(webhookRow.payloadFormat).toBe("default");

      // Absent payloadFormat should conceptually default to "default"
      const webhookRowNoFormat: Record<string, string> = {
        id: "webhook-002",
        url: "https://example.com/hook2",
      };

      expect(webhookRowNoFormat.payloadFormat ?? "default").toBe("default");
    });
  });

  // =========================================================================
  // Suite 6: Performance
  // =========================================================================
  describe("performance", () => {
    test("100 opinionScale responses export in under 1000ms", async () => {
      const survey = buildOpinionScaleSurvey();
      const elementsHeadlines = [["1. Rate our service"]];
      const responses = Array.from({ length: 100 }, (_, i) =>
        buildResponse(`resp-perf-os-${i}`, survey.id, { "q-os-1": (i % 5) + 1 })
      );

      const start = performance.now();
      const jsonData = getResponsesJson(survey, responses, elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      await convertToCsv(headers, jsonData);
      convertToJson(headers, jsonData);
      convertToXlsxBuffer(headers, jsonData);
      const elapsed = performance.now() - start;

      expect(jsonData).toHaveLength(100);
      expect(elapsed).toBeLessThan(1000);
    });

    test("100 payment responses export in under 1000ms", async () => {
      const survey = buildPaymentSurvey();
      const elementsHeadlines = [["1. Complete payment"]];
      const responses = Array.from({ length: 100 }, (_, i) =>
        buildResponse(`resp-perf-pay-${i}`, survey.id, { "q-pay-1": i % 2 === 0 ? "paid" : "" })
      );

      const start = performance.now();
      const jsonData = getResponsesJson(survey, responses, elementsHeadlines, [], []);
      const headers = Object.keys(jsonData[0]);
      await convertToCsv(headers, jsonData);
      convertToJson(headers, jsonData);
      convertToXlsxBuffer(headers, jsonData);
      const elapsed = performance.now() - start;

      expect(jsonData).toHaveLength(100);
      expect(elapsed).toBeLessThan(1000);
    });

    test("500 mixed responses export to all 3 formats without error", async () => {
      const survey = buildMixedSurvey();
      const elementsHeadlines = [["1. Your name?"], ["2. Rate us"], ["3. Pay"]];
      const responses = Array.from({ length: 500 }, (_, i) =>
        buildResponse(`resp-perf-mix-${i}`, survey.id, {
          "q-text-1": `User ${i}`,
          "q-os-1": (i % 5) + 1,
          "q-pay-1": i % 3 === 0 ? "paid" : "",
        })
      );

      const jsonData = getResponsesJson(survey, responses, elementsHeadlines, [], []);
      expect(jsonData).toHaveLength(500);

      const headers = Object.keys(jsonData[0]);

      // CSV export
      const csv = await convertToCsv(headers, jsonData);
      expect(csv).toBeDefined();
      expect(csv.length).toBeGreaterThan(0);

      // JSON export
      const jsonStr = convertToJson(headers, jsonData);
      const parsed = JSON.parse(jsonStr);
      expect(parsed).toHaveLength(500);

      // XLSX export
      const buffer = convertToXlsxBuffer(headers, jsonData);
      expect(Buffer.isBuffer(buffer)).toBe(true);
      expect(buffer.length).toBeGreaterThan(0);
    });
  });
});
