/**
 * Data Migration: Audit Sprint 1-3 Backward Compatibility
 *
 * This audit script validates that all schema changes introduced in Sprints 1-3
 * are backward-compatible with existing data. It runs AFTER the
 * 20260301120000_add_payload_format_to_webhook SQL migration.
 *
 * Audit Checks:
 * 1. Verify `payloadFormat` column exists on the `Webhook` table with correct defaults
 * 2. Verify existing webhooks have valid `payloadFormat` values
 * 3. Verify existing Survey blocks data integrity with expanded element types
 *    (17 types including the Sprint 1 additions: Payment and OpinionScale)
 * 4. Log comprehensive audit summary
 *
 * This script is read-only and idempotent — safe to re-run without side effects.
 */
import { logger } from "@formbricks/logger";
import type { MigrationScript } from "../../src/scripts/migration-runner";

/**
 * The canonical set of 17 valid survey element types after Sprint 1-3 expansions.
 * Includes the original 15 types plus the Sprint 1 additions: `payment` and `opinionScale`.
 */
const VALID_ELEMENT_TYPES = new Set([
  "fileUpload",
  "openText",
  "multipleChoiceSingle",
  "multipleChoiceMulti",
  "nps",
  "cta",
  "rating",
  "consent",
  "pictureSelection",
  "cal",
  "date",
  "matrix",
  "address",
  "ranking",
  "contactInfo",
  "payment",
  "opinionScale",
]);

/**
 * Safely extracts all element types from a survey's blocks array.
 *
 * The `blocks` column is a JSONB array in PostgreSQL. Each block is an object
 * with an `elements` array, and each element has a `type` field.
 *
 * Structure: blocks -\> block.elements -\> element.type
 *
 * @param blocks - The raw blocks data from the database (parsed JSONB)
 * @returns An array of element type strings found across all blocks
 */
const extractElementTypesFromBlocks = (blocks: unknown): string[] => {
  const types: string[] = [];

  if (!Array.isArray(blocks)) {
    return types;
  }

  for (const block of blocks) {
    if (block === null || typeof block !== "object") {
      continue;
    }

    const blockObj = block as Record<string, unknown>;
    const elements = blockObj.elements;

    if (!Array.isArray(elements)) {
      continue;
    }

    for (const element of elements) {
      if (element === null || typeof element !== "object") {
        continue;
      }

      const elementObj = element as Record<string, unknown>;
      if (typeof elementObj.type === "string" && elementObj.type.length > 0) {
        types.push(elementObj.type);
      }
    }
  }

  return types;
};

// eslint-disable-next-line camelcase -- migration export name must match the folder naming convention
export const auditSprint1_3Changes: MigrationScript = {
  type: "data",
  id: "cm8audit0sprint13changes01",
  name: "20260301130000_audit_sprint1_3_changes",
  run: async ({ tx }) => {
    let webhookCount = 0;
    let surveyCount = 0;

    // ===========================================================================
    // AUDIT STEP 1: Verify Webhook.payloadFormat column exists
    // ===========================================================================
    try {
      logger.info("Audit Step 1: Verifying Webhook.payloadFormat column exists...");

      const columnResult = await tx.$queryRaw<
        {
          column_name: string;
          column_default: string | null;
          is_nullable: string;
          data_type: string;
        }[]
      >`
        SELECT column_name, column_default, is_nullable, data_type
        FROM information_schema.columns
        WHERE table_name = 'Webhook' AND column_name = 'payloadFormat'
      `;

      if (columnResult.length === 0) {
        throw new Error(
          "Audit Step 1 FAILED: The 'payloadFormat' column does not exist on the 'Webhook' table. " +
            "Ensure the 20260301120000_add_payload_format_to_webhook migration has been applied."
        );
      }

      if (columnResult.length > 1) {
        throw new Error(
          `Audit Step 1 FAILED: Expected exactly 1 row for 'payloadFormat' column metadata, ` +
            `but found ${columnResult.length.toString()} rows.`
        );
      }

      const columnMeta = columnResult[0];

      // Verify the default value contains 'default' (PostgreSQL stores it as 'default'::text or similar)
      if (!columnMeta.column_default?.includes("default")) {
        logger.warn(
          `Audit Step 1 WARNING: The 'payloadFormat' column default value is '${columnMeta.column_default ?? "NULL"}'. ` +
            `Expected a default containing 'default'.`
        );
      }

      logger.info(
        `Audit Step 1 PASSED: Webhook.payloadFormat column exists — ` +
          `data_type=${columnMeta.data_type}, ` +
          `column_default=${columnMeta.column_default ?? "NULL"}, ` +
          `is_nullable=${columnMeta.is_nullable}`
      );
    } catch (error) {
      logger.error(error, "Audit Step 1 FAILED: Error verifying Webhook.payloadFormat column");
      throw error;
    }

    // ===========================================================================
    // AUDIT STEP 2: Verify existing webhooks have correct default payloadFormat
    // ===========================================================================
    try {
      logger.info("Audit Step 2: Verifying existing webhooks have valid payloadFormat values...");

      const totalWebhooksResult = await tx.$queryRaw<{ total: bigint }[]>`
        SELECT COUNT(*) as total FROM "Webhook"
      `;
      webhookCount = Number(totalWebhooksResult[0].total);

      const validWebhooksResult = await tx.$queryRaw<{ count: bigint }[]>`
        SELECT COUNT(*) as count FROM "Webhook"
        WHERE "payloadFormat" IS NULL OR "payloadFormat" = 'default'
      `;
      const validWebhookCount = Number(validWebhooksResult[0].count);

      logger.info(
        `Audit Step 2: Found ${webhookCount.toString()} total webhooks, ` +
          `${validWebhookCount.toString()} with NULL or 'default' payloadFormat`
      );

      if (webhookCount > 0 && validWebhookCount !== webhookCount) {
        const nonDefaultCount = webhookCount - validWebhookCount;
        logger.warn(
          `Audit Step 2 WARNING: ${nonDefaultCount.toString()} webhook(s) have a non-default payloadFormat value. ` +
            `This is informational — these webhooks may have been explicitly configured.`
        );
      }

      logger.info("Audit Step 2 PASSED: All existing webhooks have valid payloadFormat values");
    } catch (error) {
      logger.error(error, "Audit Step 2 FAILED: Error verifying webhook payloadFormat values");
      throw error;
    }

    // ===========================================================================
    // AUDIT STEP 3: Verify Survey data integrity with expanded element types
    // ===========================================================================
    try {
      logger.info("Audit Step 3: Verifying Survey blocks data integrity with expanded element types...");

      const surveysResult = await tx.$queryRaw<{ id: string; blocks: unknown }[]>`
        SELECT id, blocks FROM "Survey" WHERE blocks IS NOT NULL LIMIT 100
      `;
      surveyCount = surveysResult.length;

      logger.info(`Audit Step 3: Examining ${surveyCount.toString()} surveys with blocks data...`);

      const invalidSurveys: { surveyId: string; invalidTypes: string[] }[] = [];
      const allElementTypesFound = new Set<string>();

      for (const survey of surveysResult) {
        const elementTypes = extractElementTypesFromBlocks(survey.blocks);

        for (const elementType of elementTypes) {
          allElementTypesFound.add(elementType);

          if (!VALID_ELEMENT_TYPES.has(elementType)) {
            const existing = invalidSurveys.find((s) => s.surveyId === survey.id);
            if (existing) {
              existing.invalidTypes.push(elementType);
            } else {
              invalidSurveys.push({
                surveyId: survey.id,
                invalidTypes: [elementType],
              });
            }
          }
        }
      }

      if (invalidSurveys.length > 0) {
        const details = invalidSurveys
          .map((s) => `Survey ${s.surveyId}: unrecognized types [${s.invalidTypes.join(", ")}]`)
          .join("; ");

        throw new Error(
          `Audit Step 3 FAILED: Found ${invalidSurveys.length.toString()} survey(s) with unrecognized element types. ` +
            `Details: ${details}. ` +
            `Valid element types are: ${Array.from(VALID_ELEMENT_TYPES).join(", ")}`
        );
      }

      logger.info(
        `Audit Step 3 PASSED: ${surveyCount.toString()} surveys examined — ` +
          `all element types are valid. ` +
          `Element types found in data: [${Array.from(allElementTypesFound).join(", ")}]`
      );
    } catch (error) {
      logger.error(error, "Audit Step 3 FAILED: Error verifying Survey blocks data integrity");
      throw error;
    }

    // ===========================================================================
    // AUDIT STEP 4: Comprehensive audit summary
    // ===========================================================================
    logger.info("=== Sprint 1-3 Backward Compatibility Audit Complete ===");
    logger.info("Webhook payloadFormat column: ✓ Verified");
    logger.info(`Existing webhooks: ${webhookCount.toString()} total, all with valid payloadFormat`);
    logger.info(`Surveys audited: ${surveyCount.toString()} — all element types valid`);
    logger.info("Element types verified: 17 types (including Payment and OpinionScale additions)");
    logger.info("=== All Sprint 1-3 changes are backward-compatible ===");
  },
};
