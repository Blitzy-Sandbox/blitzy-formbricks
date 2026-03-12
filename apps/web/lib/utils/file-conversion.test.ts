import { AsyncParser } from "@json2csv/node";
import { describe, expect, test, vi } from "vitest";
import * as xlsx from "xlsx";
import { logger } from "@formbricks/logger";
import { convertToCsv, convertToJson, convertToXlsxBuffer } from "./file-conversion";

// Mock the logger to capture error calls
vi.mock("@formbricks/logger", () => ({
  logger: { error: vi.fn() },
}));

describe("convertToCsv", () => {
  const fields = ["name", "age"];
  const data = [
    { name: "Alice", age: 30 },
    { name: "Bob", age: 25 },
  ];

  test("should convert JSON array to CSV string with header", async () => {
    const csv = await convertToCsv(fields, data);
    const lines = csv.trim().split("\n");
    // json2csv quotes headers by default
    expect(lines[0]).toBe('"name","age"');
    expect(lines[1]).toBe('"Alice",30');
    expect(lines[2]).toBe('"Bob",25');
  });

  test("should log an error and throw when conversion fails", async () => {
    const parseSpy = vi.spyOn(AsyncParser.prototype, "parse").mockImplementation(
      () =>
        ({
          promise: () => Promise.reject(new Error("Test parse error")),
        }) as any
    );

    await expect(convertToCsv(fields, data)).rejects.toThrow("Failed to convert to CSV");
    expect(logger.error).toHaveBeenCalledWith(expect.any(Error), "Failed to convert to CSV");

    parseSpy.mockRestore();
  });
});

describe("convertToXlsxBuffer", () => {
  const fields = ["name", "age"];
  const data = [
    { name: "Alice", age: 30 },
    { name: "Bob", age: 25 },
  ];

  test("should convert JSON array to XLSX buffer and preserve data", () => {
    const buffer = convertToXlsxBuffer(fields, data);
    const wb = xlsx.read(buffer, { type: "buffer" });
    const sheet = wb.Sheets["Sheet1"];
    // Skip header row (range:1) and remove internal row metadata
    const raw = xlsx.utils.sheet_to_json<Record<string, string | number>>(sheet, {
      header: fields,
      defval: "",
      range: 1,
    });
    const cleaned = raw.map(({ __rowNum__, ...rest }) => rest);
    expect(cleaned).toEqual(data);
  });
});

describe("convertToJson", () => {
  test("should return valid JSON that can be parsed back", () => {
    const fields = ["name", "age"];
    const data = [
      { name: "Alice", age: 30 },
      { name: "Bob", age: 25 },
    ];

    const result = convertToJson(fields, data);

    // Result must be a string
    expect(typeof result).toBe("string");

    // Parsed output must equal the original data
    const parsed = JSON.parse(result);
    expect(parsed).toEqual(data);

    // Output must use 2-space indentation (pretty-printed)
    expect(result).toBe(JSON.stringify(data, null, 2));
  });

  test("should preserve all fields from input data", () => {
    const fields = ["name", "age", "email"];
    const data = [{ name: "Alice", age: 30, email: "alice@test.com" }];

    const result = convertToJson(fields, data);
    const parsed = JSON.parse(result);

    // All keys from the input must be present in the output
    expect(Object.keys(parsed[0])).toEqual(expect.arrayContaining(["name", "age", "email"]));
    expect(parsed[0].name).toBe("Alice");
    expect(parsed[0].age).toBe(30);
    expect(parsed[0].email).toBe("alice@test.com");
  });

  test("should preserve exact values and types without truncation or rounding", () => {
    const fields = ["name", "score", "count"];
    const data = [{ name: "Test", score: 99.999, count: 0 }];

    const result = convertToJson(fields, data);
    const parsed = JSON.parse(result);

    // Numbers must remain as numbers, strings as strings
    expect(typeof parsed[0].name).toBe("string");
    expect(typeof parsed[0].score).toBe("number");
    expect(typeof parsed[0].count).toBe("number");

    // No truncation or rounding of decimal values
    expect(parsed[0].score).toBe(99.999);
    expect(parsed[0].count).toBe(0);
  });

  test("should preserve unicode characters including emojis and CJK", () => {
    const fields = ["name", "notes"];
    const data = [{ name: "Héllo 🌍", notes: "日本語テスト" }];

    const result = convertToJson(fields, data);
    const parsed = JSON.parse(result);

    // Unicode characters must survive without corruption
    expect(parsed[0].name).toBe("Héllo 🌍");
    expect(parsed[0].notes).toBe("日本語テスト");
  });

  test("should handle empty arrays", () => {
    const result = convertToJson([], []);

    // Empty array serialized as pretty-printed JSON
    expect(result).toBe(JSON.stringify([], null, 2));
    expect(JSON.parse(result)).toEqual([]);
  });

  test("should handle records with various value types", () => {
    const fields = ["name", "value", "label"];
    const data = [{ name: "Test", value: 0, label: "" }];

    const result = convertToJson(fields, data);
    const parsed = JSON.parse(result);

    // Falsy values must be preserved exactly (0 stays 0, empty string stays "")
    expect(parsed[0].value).toBe(0);
    expect(parsed[0].label).toBe("");
    expect(parsed[0].name).toBe("Test");
  });

  test("should handle large arrays without truncation", () => {
    const largeData = Array.from({ length: 1000 }, (_, i) => ({ id: i, name: "item" + i }));
    const fields = ["id", "name"];

    const result = convertToJson(fields, largeData);
    const parsed = JSON.parse(result);

    // All 1000 records must be present
    expect(parsed.length).toBe(1000);

    // First and last elements must match
    expect(parsed[0]).toEqual({ id: 0, name: "item0" });
    expect(parsed[999]).toEqual({ id: 999, name: "item999" });
  });
});
