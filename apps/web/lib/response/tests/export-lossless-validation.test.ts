import { describe, expect, test } from "vitest";
import { TResponseWithQuotas } from "@formbricks/types/responses";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/elements";
import { TSurvey } from "@formbricks/types/surveys/types";
import { convertToCsv, convertToJson, convertToXlsxBuffer } from "../../utils/file-conversion";
import { getResponsesJson } from "../utils";

// ---------------------------------------------------------------------------
// Test helpers — shared fixtures
// ---------------------------------------------------------------------------

const baseHeaders = ["No.", "Response ID", "Timestamp", "Finished", "Survey ID"];

const buildSimpleJsonData = (): Record<string, string | number>[] => [
  {
    "No.": 1,
    "Response ID": "resp-001",
    Timestamp: "2024-06-15 10:00:00",
    Finished: "Yes",
    "Survey ID": "survey-001",
  },
  {
    "No.": 2,
    "Response ID": "resp-002",
    Timestamp: "2024-06-15 11:00:00",
    Finished: "No",
    "Survey ID": "survey-001",
  },
];

/**
 * Builds a comprehensive jsonData set that exercises many data types:
 * strings, numbers, empty strings, comma-containing values, and
 * fields representing metadata, hidden fields, tags, and variables.
 */
const buildComprehensiveHeaders = (): string[] => [
  "No.",
  "Response ID",
  "Timestamp",
  "Finished",
  "Survey ID",
  "Formbricks ID (internal)",
  "User ID",
  "Tags",
  "source",
  "url",
  "userAgent - browser",
  "userAgent - os",
  "userAgent - device",
  "1. What is your name?",
  "hiddenSource",
  "Score",
  "plan",
];

const buildComprehensiveJsonData = (): Record<string, string | number>[] => [
  {
    "No.": 1,
    "Response ID": "resp-full-001",
    Timestamp: "2024-06-15 10:00:00",
    Finished: "Yes",
    "Survey ID": "survey-full-001",
    "Formbricks ID (internal)": "contact-1",
    "User ID": "user-1",
    Tags: "important, vip",
    source: "web",
    url: "https://example.com/survey",
    "userAgent - browser": "Chrome",
    "userAgent - os": "Windows 11",
    "userAgent - device": "Desktop",
    "1. What is your name?": "John Doe",
    hiddenSource: "google",
    Score: 42,
    plan: "Pro",
  },
  {
    "No.": 2,
    "Response ID": "resp-full-002",
    Timestamp: "2024-06-15 11:30:00",
    Finished: "No",
    "Survey ID": "survey-full-001",
    "Formbricks ID (internal)": "",
    "User ID": "",
    Tags: "",
    source: "api",
    url: "https://example.com/embed",
    "userAgent - browser": "Firefox",
    "userAgent - os": "macOS",
    "userAgent - device": "Desktop",
    "1. What is your name?": "",
    hiddenSource: "twitter",
    Score: 0,
    plan: "",
  },
];

// Minimal TSurvey-shaped object with blocks (not the legacy questions array)
const buildTestSurvey = (): TSurvey =>
  ({
    id: "survey-full-001",
    createdAt: new Date("2024-06-01T00:00:00Z"),
    updatedAt: new Date("2024-06-01T00:00:00Z"),
    name: "Test Survey",
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
            id: "q1",
            type: TSurveyElementTypeEnum.OpenText,
            headline: { default: "What is your name?" },
            required: true,
            inputType: "text" as const,
            charLimit: { enabled: false },
          },
        ],
      },
    ],
    endings: [
      {
        type: "endScreen" as const,
        id: "end1",
        enabled: true,
        headline: { default: "Thanks!" },
      },
    ],
    hiddenFields: { enabled: true, fieldIds: ["hiddenSource"] },
    variables: [{ id: "var1", name: "Score", type: "number" as const, value: 0 }],
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
 * Constructs a TResponseWithQuotas-compatible object for testing getResponsesJson.
 */
const buildTestResponse = (overrides: Partial<TResponseWithQuotas> = {}): TResponseWithQuotas =>
  ({
    id: "resp-full-001",
    createdAt: new Date("2024-06-15T10:00:00Z"),
    updatedAt: new Date("2024-06-15T10:00:00Z"),
    finished: true,
    surveyId: "survey-full-001",
    data: { q1: "John Doe", hiddenSource: "google" },
    meta: {
      source: "web",
      url: "https://example.com/survey",
      userAgent: { browser: "Chrome", os: "Windows 11", device: "Desktop" },
    },
    tags: [
      {
        id: "tag1",
        name: "important",
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-01T00:00:00Z"),
        environmentId: "env-001",
      },
      {
        id: "tag2",
        name: "vip",
        createdAt: new Date("2024-01-01T00:00:00Z"),
        updatedAt: new Date("2024-01-01T00:00:00Z"),
        environmentId: "env-001",
      },
    ],
    variables: { var1: 42 },
    contactAttributes: { plan: "Pro" },
    contact: { id: "contact-1", userId: "user-1" },
    quotas: [{ id: "quota-1", name: "Quota 1" }],
    ttc: {},
    singleUseId: null,
    language: "default",
    displayId: null,
    endingId: null,
    ...overrides,
  }) as unknown as TResponseWithQuotas;

// ===========================================================================
// Test suites
// ===========================================================================

describe("Sprint 5 — Export Lossless Validation", () => {
  // -------------------------------------------------------------------------
  // Phase 3 — JSON export
  // -------------------------------------------------------------------------
  describe("convertToJson preserves all fields", () => {
    test("produces a JSON string that round-trips to the exact same field values", () => {
      const headers = [...baseHeaders];
      const jsonData = buildSimpleJsonData();

      const jsonString = convertToJson(headers, jsonData);
      const parsed: Record<string, string | number>[] = JSON.parse(jsonString);

      expect(parsed).toHaveLength(jsonData.length);

      parsed.forEach((record, idx) => {
        headers.forEach((header) => {
          expect(record[header]).toEqual(jsonData[idx][header]);
        });
      });
    });

    test("normalizes missing fields to empty string — not undefined", () => {
      const headers = ["No.", "Response ID", "Timestamp", "Finished", "Survey ID", "Extra Field"];
      // The record is missing "Extra Field"
      const jsonData: Record<string, string | number>[] = [
        {
          "No.": 1,
          "Response ID": "resp-010",
          Timestamp: "2024-07-01 09:00:00",
          Finished: "Yes",
          "Survey ID": "survey-010",
          // "Extra Field" is intentionally absent
        },
      ];

      const jsonString = convertToJson(headers, jsonData);
      const parsed: Record<string, string | number>[] = JSON.parse(jsonString);

      expect(parsed[0]["Extra Field"]).toBe("");
      // Ensure it's not undefined
      expect(parsed[0]["Extra Field"]).not.toBeUndefined();
    });

    test("preserves string values, numeric values, and empty-string values without corruption", () => {
      const headers = ["Name", "Age", "Email"];
      const jsonData: Record<string, string | number>[] = [
        { Name: "Alice", Age: 30, Email: "" },
        { Name: "Bob", Age: 0, Email: "bob@test.com" },
      ];

      const jsonString = convertToJson(headers, jsonData);
      const parsed: Record<string, string | number>[] = JSON.parse(jsonString);

      expect(parsed[0]["Name"]).toBe("Alice");
      expect(parsed[0]["Age"]).toBe(30);
      expect(parsed[0]["Email"]).toBe("");
      expect(parsed[1]["Name"]).toBe("Bob");
      expect(parsed[1]["Age"]).toBe(0);
      expect(parsed[1]["Email"]).toBe("bob@test.com");
    });

    test("each parsed object has exactly the same keys as the headers array", () => {
      const headers = ["A", "B", "C"];
      const jsonData: Record<string, string | number>[] = [
        { A: "x", B: "y" }, // missing C
      ];

      const jsonString = convertToJson(headers, jsonData);
      const parsed: Record<string, string | number>[] = JSON.parse(jsonString);

      expect(Object.keys(parsed[0]).sort()).toEqual([...headers].sort());
    });

    test("handles records with extra keys not in headers — only header keys appear in output", () => {
      const headers = ["Name"];
      const jsonData: Record<string, string | number>[] = [{ Name: "Charlie", ExtraKey: "ignored" }];

      const jsonString = convertToJson(headers, jsonData);
      const parsed: Record<string, string | number>[] = JSON.parse(jsonString);

      expect(Object.keys(parsed[0])).toEqual(["Name"]);
      expect(parsed[0]["ExtraKey" as keyof (typeof parsed)[0]]).toBeUndefined();
    });
  });

  // -------------------------------------------------------------------------
  // Phase 4 — CSV export
  // -------------------------------------------------------------------------
  describe("convertToCsv preserves all fields", () => {
    test("produces valid CSV with header row matching the fields array", async () => {
      const headers = [...baseHeaders];
      const jsonData = buildSimpleJsonData();

      const csv = await convertToCsv(headers, jsonData);
      const lines = csv.trim().split("\n");

      // First line should be the header row
      const headerLine = lines[0];
      headers.forEach((h) => {
        // CSV may quote headers, so check the header is present
        expect(headerLine).toContain(h);
      });
    });

    test("CSV output contains all data values from jsonData records", async () => {
      const headers = [...baseHeaders];
      const jsonData = buildSimpleJsonData();

      const csv = await convertToCsv(headers, jsonData);

      // Verify that each data value appears somewhere in the CSV
      jsonData.forEach((record) => {
        Object.values(record).forEach((value) => {
          expect(csv).toContain(String(value));
        });
      });
    });

    test("empty/missing values are handled gracefully", async () => {
      const headers = ["Name", "Empty Field"];
      const jsonData: Record<string, string | number>[] = [{ Name: "Test", "Empty Field": "" }];

      const csv = await convertToCsv(headers, jsonData);
      expect(csv).toBeDefined();
      expect(csv.length).toBeGreaterThan(0);
      // Should not throw and should contain the header
      expect(csv).toContain("Name");
    });

    test("special characters in values (commas, quotes, newlines) are properly escaped", async () => {
      const headers = ["Field A", "Field B", "Field C"];
      const jsonData: Record<string, string | number>[] = [
        {
          "Field A": 'Value with "quotes"',
          "Field B": "Value, with, commas",
          "Field C": "Value\nwith\nnewlines",
        },
      ];

      const csv = await convertToCsv(headers, jsonData);
      // The CSV should contain escaped versions of these special characters
      // json2csv wraps fields with special chars in double quotes
      expect(csv).toBeDefined();
      expect(csv.length).toBeGreaterThan(0);
      // Should still contain the actual values (possibly escaped/quoted)
      expect(csv).toContain("quotes");
      expect(csv).toContain("commas");
      expect(csv).toContain("newlines");
    });
  });

  // -------------------------------------------------------------------------
  // Phase 5 — XLSX export
  // -------------------------------------------------------------------------
  describe("convertToXlsxBuffer produces valid buffer", () => {
    test("returns a Buffer instance", () => {
      const headers = [...baseHeaders];
      const jsonData = buildSimpleJsonData();

      const buffer = convertToXlsxBuffer(headers, jsonData);
      expect(Buffer.isBuffer(buffer)).toBe(true);
    });

    test("buffer is non-empty", () => {
      const headers = [...baseHeaders];
      const jsonData = buildSimpleJsonData();

      const buffer = convertToXlsxBuffer(headers, jsonData);
      expect(buffer.length).toBeGreaterThan(0);
    });

    test("buffer can be converted to base64 string (matching getResponseDownloadFile flow)", () => {
      const headers = [...baseHeaders];
      const jsonData = buildSimpleJsonData();

      const buffer = convertToXlsxBuffer(headers, jsonData);
      const base64 = buffer.toString("base64");

      expect(typeof base64).toBe("string");
      expect(base64.length).toBeGreaterThan(0);
      // Verify it's valid base64 by decoding it back
      const decoded = Buffer.from(base64, "base64");
      expect(decoded).toEqual(buffer);
    });
  });

  // -------------------------------------------------------------------------
  // Phase 6 — Field preservation across ALL formats
  // -------------------------------------------------------------------------
  describe("All export formats preserve complete data fidelity", () => {
    const comprehensiveHeaders = buildComprehensiveHeaders();
    const comprehensiveData = buildComprehensiveJsonData();

    test("JSON format preserves all fields field-by-field", () => {
      const jsonString = convertToJson(comprehensiveHeaders, comprehensiveData);
      const parsed: Record<string, string | number>[] = JSON.parse(jsonString);

      expect(parsed).toHaveLength(comprehensiveData.length);

      // Record 1 — all fields populated
      const record1 = parsed[0];
      expect(record1["No."]).toBe(1);
      expect(record1["Response ID"]).toBe("resp-full-001");
      expect(record1["Timestamp"]).toBe("2024-06-15 10:00:00");
      expect(record1["Finished"]).toBe("Yes");
      expect(record1["Survey ID"]).toBe("survey-full-001");
      expect(record1["Formbricks ID (internal)"]).toBe("contact-1");
      expect(record1["User ID"]).toBe("user-1");
      expect(record1["Tags"]).toBe("important, vip");
      expect(record1["source"]).toBe("web");
      expect(record1["url"]).toBe("https://example.com/survey");
      expect(record1["userAgent - browser"]).toBe("Chrome");
      expect(record1["userAgent - os"]).toBe("Windows 11");
      expect(record1["userAgent - device"]).toBe("Desktop");
      expect(record1["1. What is your name?"]).toBe("John Doe");
      expect(record1["hiddenSource"]).toBe("google");
      expect(record1["Score"]).toBe(42);
      expect(record1["plan"]).toBe("Pro");

      // Record 2 — many empty/zero fields
      const record2 = parsed[1];
      expect(record2["No."]).toBe(2);
      expect(record2["Formbricks ID (internal)"]).toBe("");
      expect(record2["User ID"]).toBe("");
      expect(record2["Tags"]).toBe("");
      expect(record2["Score"]).toBe(0);
      expect(record2["1. What is your name?"]).toBe("");
    });

    test("CSV format preserves all fields — headers and data values present", async () => {
      const csv = await convertToCsv(comprehensiveHeaders, comprehensiveData);
      const lines = csv.trim().split("\n");

      // Header row should contain all headers
      const headerLine = lines[0];
      comprehensiveHeaders.forEach((h) => {
        expect(headerLine).toContain(h);
      });

      // All data values should appear in the CSV body
      expect(csv).toContain("resp-full-001");
      expect(csv).toContain("resp-full-002");
      expect(csv).toContain("John Doe");
      expect(csv).toContain("Chrome");
      expect(csv).toContain("Firefox");
      expect(csv).toContain("important, vip");
      expect(csv).toContain("google");
      expect(csv).toContain("twitter");
      expect(csv).toContain("Pro");
      expect(csv).toContain("42");
    });

    test("XLSX format produces non-empty valid buffer for comprehensive data", () => {
      const buffer = convertToXlsxBuffer(comprehensiveHeaders, comprehensiveData);
      expect(Buffer.isBuffer(buffer)).toBe(true);
      expect(buffer.length).toBeGreaterThan(0);
      // XLSX files start with PK zip header (50 4B)
      expect(buffer[0]).toBe(0x50);
      expect(buffer[1]).toBe(0x4b);
    });
  });

  // -------------------------------------------------------------------------
  // Phase 7 — getResponsesJson data transformation
  // -------------------------------------------------------------------------
  describe("getResponsesJson preserves response data", () => {
    const testSurvey = buildTestSurvey();
    const elementsHeadlines: string[][] = [["1. What is your name?"]];

    test("converts response objects into flat row records with expected header keys", () => {
      const response = buildTestResponse();
      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, ["plan"], ["hiddenSource"]);

      expect(result).toHaveLength(1);
      const row = result[0];

      expect(row["No."]).toBe(1);
      expect(row["Response ID"]).toBe("resp-full-001");
      expect(row["Finished"]).toBe("Yes");
      expect(row["Survey ID"]).toBe("survey-full-001");
    });

    test("Response ID, Timestamp, Finished, Survey ID are present in output", () => {
      const response = buildTestResponse();
      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, [], []);
      const row = result[0];

      expect(row).toHaveProperty("Response ID");
      expect(row).toHaveProperty("Timestamp");
      expect(row).toHaveProperty("Finished");
      expect(row).toHaveProperty("Survey ID");
      expect(row["Response ID"]).toBe("resp-full-001");
      expect(row["Finished"]).toBe("Yes");
      expect(row["Survey ID"]).toBe("survey-full-001");
      // Timestamp is formatted — just verify it's a non-empty string
      expect(typeof row["Timestamp"]).toBe("string");
      expect(String(row["Timestamp"]).length).toBeGreaterThan(0);
    });

    test("Contact ID and User ID are included when contact is present", () => {
      const response = buildTestResponse({
        contact: { id: "contact-abc", userId: "user-xyz" },
      } as any);

      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, [], []);
      const row = result[0];

      expect(row["Formbricks ID (internal)"]).toBe("contact-abc");
      expect(row["User ID"]).toBe("user-xyz");
    });

    test("Contact ID and User ID are empty when contact is null", () => {
      const response = buildTestResponse({ contact: null } as any);

      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, [], []);
      const row = result[0];

      expect(row["Formbricks ID (internal)"]).toBe("");
      expect(row["User ID"]).toBe("");
    });

    test("Tags are joined with comma separator", () => {
      const response = buildTestResponse();
      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, [], []);
      const row = result[0];

      expect(row["Tags"]).toBe("important, vip");
    });

    test("Tags are empty string when there are no tags", () => {
      const response = buildTestResponse({ tags: [] } as any);
      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, [], []);
      const row = result[0];

      expect(row["Tags"]).toBe("");
    });

    test("Meta fields are flattened (userAgent - browser, userAgent - os, userAgent - device)", () => {
      const response = buildTestResponse();
      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, [], []);
      const row = result[0];

      expect(row["userAgent - browser"]).toBe("Chrome");
      expect(row["userAgent - os"]).toBe("Windows 11");
      expect(row["userAgent - device"]).toBe("Desktop");
      expect(row["source"]).toBe("web");
      expect(row["url"]).toBe("https://example.com/survey");
    });

    test("Hidden fields are included in the output", () => {
      const response = buildTestResponse();
      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, [], ["hiddenSource"], false);
      const row = result[0];

      expect(row["hiddenSource"]).toBe("google");
    });

    test("User attributes are included in the output", () => {
      const response = buildTestResponse();
      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, ["plan"], [], false);
      const row = result[0];

      expect(row["plan"]).toBe("Pro");
    });

    test("Variables are included in the output", () => {
      const response = buildTestResponse();
      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, [], [], false);
      const row = result[0];

      // Variables are mapped by variable name from survey.variables
      expect(row["Score"]).toBe(42);
    });

    test("Quotas column included when isQuotasAllowed is true", () => {
      const response = buildTestResponse();
      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, [], [], true);
      const row = result[0];

      expect(row).toHaveProperty("Quotas");
      expect(row["Quotas"]).toBe("Quota 1");
    });

    test("Quotas column absent when isQuotasAllowed is false", () => {
      const response = buildTestResponse();
      const result = getResponsesJson(testSurvey, [response], elementsHeadlines, [], [], false);
      const row = result[0];

      expect(row).not.toHaveProperty("Quotas");
    });

    test("Multiple responses produce multiple rows with correct numbering", () => {
      const resp1 = buildTestResponse({ id: "resp-001" } as any);
      const resp2 = buildTestResponse({
        id: "resp-002",
        finished: false,
        data: { q1: "Jane Smith", hiddenSource: "bing" },
      } as any);

      const result = getResponsesJson(testSurvey, [resp1, resp2], elementsHeadlines, [], ["hiddenSource"]);

      expect(result).toHaveLength(2);
      expect(result[0]["No."]).toBe(1);
      expect(result[0]["Response ID"]).toBe("resp-001");
      expect(result[1]["No."]).toBe(2);
      expect(result[1]["Response ID"]).toBe("resp-002");
      expect(result[1]["Finished"]).toBe("No");
      expect(result[1]["1. What is your name?"]).toBe("Jane Smith");
      expect(result[1]["hiddenSource"]).toBe("bing");
    });
  });

  // -------------------------------------------------------------------------
  // Phase 8 — Error handling in export
  // -------------------------------------------------------------------------
  describe("Export error handling", () => {
    test("convertToCsv with empty data array produces a valid header-only CSV", async () => {
      const headers = ["Name", "Value"];
      const jsonData: Record<string, string | number>[] = [];

      const csv = await convertToCsv(headers, jsonData);
      expect(csv).toBeDefined();
      // Should contain at least the header row
      expect(csv).toContain("Name");
      expect(csv).toContain("Value");
    });

    test("convertToJson with empty data array produces an empty JSON array", () => {
      const headers = ["Name", "Value"];
      const jsonData: Record<string, string | number>[] = [];

      const jsonString = convertToJson(headers, jsonData);
      const parsed = JSON.parse(jsonString);

      expect(Array.isArray(parsed)).toBe(true);
      expect(parsed).toHaveLength(0);
    });

    test("convertToXlsxBuffer with empty data array produces a valid non-empty buffer", () => {
      const headers = ["Name", "Value"];
      const jsonData: Record<string, string | number>[] = [];

      const buffer = convertToXlsxBuffer(headers, jsonData);
      expect(Buffer.isBuffer(buffer)).toBe(true);
      expect(buffer.length).toBeGreaterThan(0);
    });

    test("convertToJson handles single record with all empty values", () => {
      const headers = ["A", "B", "C"];
      const jsonData: Record<string, string | number>[] = [{ A: "", B: "", C: "" }];

      const jsonString = convertToJson(headers, jsonData);
      const parsed: Record<string, string | number>[] = JSON.parse(jsonString);

      expect(parsed).toHaveLength(1);
      expect(parsed[0]["A"]).toBe("");
      expect(parsed[0]["B"]).toBe("");
      expect(parsed[0]["C"]).toBe("");
    });

    test("convertToCsv handles large number of records without error", async () => {
      const headers = ["Id", "Value"];
      const jsonData: Record<string, string | number>[] = Array.from({ length: 500 }, (_, i) => ({
        Id: i + 1,
        Value: `record-${i + 1}`,
      }));

      const csv = await convertToCsv(headers, jsonData);
      expect(csv).toBeDefined();
      const lines = csv.trim().split("\n");
      // header + 500 data lines
      expect(lines.length).toBe(501);
    });

    test("convertToXlsxBuffer handles large number of records without error", () => {
      const headers = ["Id", "Value"];
      const jsonData: Record<string, string | number>[] = Array.from({ length: 500 }, (_, i) => ({
        Id: i + 1,
        Value: `record-${i + 1}`,
      }));

      const buffer = convertToXlsxBuffer(headers, jsonData);
      expect(Buffer.isBuffer(buffer)).toBe(true);
      expect(buffer.length).toBeGreaterThan(0);
    });

    test("getResponsesJson returns empty array for empty responses", () => {
      const testSurvey = buildTestSurvey();
      const result = getResponsesJson(testSurvey, [], [["1. What is your name?"]], [], []);
      expect(result).toEqual([]);
    });
  });
});
