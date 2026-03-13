import { AsyncParser } from "@json2csv/node";
import * as xlsx from "xlsx";
import { logger } from "@formbricks/logger";

export const convertToCsv = async (fields: string[], jsonData: Record<string, string | number>[]) => {
  let csv: string = "";

  const parser = new AsyncParser({
    fields,
  });

  try {
    csv = await parser.parse(jsonData).promise();
  } catch (err) {
    logger.error(err, "Failed to convert to CSV");
    throw new Error("Failed to convert to CSV");
  }

  return csv;
};

export const convertToXlsxBuffer = (
  fields: string[],
  jsonData: Record<string, string | number>[]
): Buffer => {
  const wb = xlsx.utils.book_new();
  const ws = xlsx.utils.json_to_sheet(jsonData, { header: fields });
  xlsx.utils.book_append_sheet(wb, ws, "Sheet1");
  return xlsx.write(wb, { type: "buffer", bookType: "xlsx" });
};

export const convertToJson = (fields: string[], jsonData: Record<string, string | number>[]): string => {
  // Normalize each record to include all expected fields (matching CSV/XLSX field completeness).
  // Fields not present in a record default to an empty string, ensuring lossless field parity
  // across all export formats.
  const normalizedData = jsonData.map((record) => {
    const normalized: Record<string, string | number> = {};
    for (const field of fields) {
      normalized[field] = record[field] ?? "";
    }
    return normalized;
  });
  return JSON.stringify(normalizedData, null, 2);
};
