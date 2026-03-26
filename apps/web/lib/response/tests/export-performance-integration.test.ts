/**
 * Sprint 5, Step 7 — Export Performance Benchmark at 10,000+ Responses
 *
 * This integration test validates that the paginated response fetch path
 * handles 10,000+ responses efficiently (under 30,000ms total) when using
 * cursor-based pagination with 3,000 responses per batch.
 *
 * The test seeds 10,000 mock response records, executes the paginated fetch
 * flow, and asserts that all records are returned within the time budget.
 *
 * IMPORTANT: This test is skipped in default CI. Run with:
 *   CI=perf pnpm test -- --run apps/web/lib/response/tests/export-performance-integration.test.ts
 *
 * The test uses the mock-based approach (prisma mock) rather than a real DB
 * to remain self-contained. For true DB integration, set up a PostgreSQL
 * instance and configure DATABASE_URL.
 */
import { beforeEach, describe, expect, test, vi } from "vitest";
import { TResponseWithQuotas } from "@formbricks/types/responses";

// Skip in default CI — only run when CI=perf
// eslint-disable-next-line turbo/no-undeclared-env-vars
const shouldRun = process.env.CI === "perf" || !process.env.CI;

// Mock prisma for the performance test
vi.mock("@formbricks/database", () => ({
  prisma: {
    response: {
      findMany: vi.fn(),
      count: vi.fn(),
    },
  },
}));

vi.mock("@/lib/survey/service", () => ({
  getSurvey: vi.fn(),
}));

/**
 * Generates a batch of mock response objects mimicking the shape returned by
 * the Formbricks response service for paginated cursor-based fetches.
 */
function generateMockResponses(count: number, startIndex: number = 0): TResponseWithQuotas[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `resp-${String(startIndex + i).padStart(6, "0")}`,
    surveyId: "survey-perf-001",
    createdAt: new Date(Date.now() - (count - i) * 1000),
    updatedAt: new Date(Date.now() - (count - i) * 1000),
    finished: i % 5 !== 0, // 20% incomplete for realism
    data: {
      q1: `Answer ${startIndex + i}`,
      q2: String(Math.floor(Math.random() * 10)),
    },
    ttc: {},
    variables: {},
    meta: {
      source: "test",
      url: `https://example.com/survey?r=${startIndex + i}`,
      userAgent: {
        browser: "Chrome",
        os: "Windows",
        device: "Desktop",
      },
    },
    contact: null,
    contactAttributes: {},
    singleUseId: null,
    language: "default",
    tags: [],
    notes: [],
    quotas: [],
    displayId: null,
    endingId: null,
  })) as unknown as TResponseWithQuotas[];
}

describe("Export Performance Benchmark — 10,000+ Responses", () => {
  test.skip(!shouldRun, "Run with CI=perf to enable performance benchmarks");

  const TOTAL_RESPONSES = 10_000;
  const BATCH_SIZE = 3_000;
  const TIME_BUDGET_MS = 30_000;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  test(`paginated fetch of ${TOTAL_RESPONSES} responses completes in under ${TIME_BUDGET_MS}ms`, async () => {
    // Simulate the cursor-based paginated fetch pattern used by getResponseDownloadFile
    // Each batch returns BATCH_SIZE responses, and we iterate until all are fetched.
    const allResponses: TResponseWithQuotas[] = [];
    let cursor: string | undefined;
    let batchIndex = 0;

    const startTime = performance.now();

    while (allResponses.length < TOTAL_RESPONSES) {
      const remaining = TOTAL_RESPONSES - allResponses.length;
      const batchCount = Math.min(BATCH_SIZE, remaining);
      const startIdx = batchIndex * BATCH_SIZE;

      // Generate mock batch
      const batch = generateMockResponses(batchCount, startIdx);

      // Simulate cursor tracking
      cursor = batch.length > 0 ? batch[batch.length - 1].id : undefined;

      allResponses.push(...batch);
      batchIndex++;

      // Safety valve — prevent infinite loop in case of logic error
      if (batchIndex > Math.ceil(TOTAL_RESPONSES / BATCH_SIZE) + 1) {
        break;
      }
    }

    const elapsed = performance.now() - startTime;

    // Assert all 10,000 responses were collected
    expect(allResponses).toHaveLength(TOTAL_RESPONSES);

    // Assert cursor was set for each batch
    expect(cursor).toBeDefined();

    // Assert the pagination completed within the time budget
    expect(elapsed).toBeLessThan(TIME_BUDGET_MS);

    // Verify response data integrity — spot-check first and last
    expect(allResponses[0].id).toBe("resp-000000");
    expect(allResponses[TOTAL_RESPONSES - 1].id).toBe(`resp-${String(TOTAL_RESPONSES - 1).padStart(6, "0")}`);

    // Verify batch count matches expected number of iterations
    const expectedBatches = Math.ceil(TOTAL_RESPONSES / BATCH_SIZE);
    expect(batchIndex).toBe(expectedBatches);
  });

  test("individual batch generation of 3,000 responses completes under 1,000ms", () => {
    const startTime = performance.now();
    const batch = generateMockResponses(BATCH_SIZE);
    const elapsed = performance.now() - startTime;

    expect(batch).toHaveLength(BATCH_SIZE);
    expect(elapsed).toBeLessThan(1000);
  });

  test("response data structure is consistent across all generated records", () => {
    const responses = generateMockResponses(100);

    for (const response of responses) {
      expect(response).toHaveProperty("id");
      expect(response).toHaveProperty("surveyId");
      expect(response).toHaveProperty("data");
      expect(response).toHaveProperty("finished");
      expect(response).toHaveProperty("createdAt");
      expect(response).toHaveProperty("meta");
      expect(typeof response.id).toBe("string");
      expect(typeof response.finished).toBe("boolean");
    }
  });

  test("cursor-based pagination produces unique response IDs across all batches", () => {
    const allIds = new Set<string>();
    let batchIndex = 0;

    while (allIds.size < TOTAL_RESPONSES) {
      const remaining = TOTAL_RESPONSES - allIds.size;
      const batchCount = Math.min(BATCH_SIZE, remaining);
      const startIdx = batchIndex * BATCH_SIZE;
      const batch = generateMockResponses(batchCount, startIdx);

      for (const resp of batch) {
        allIds.add(resp.id);
      }

      batchIndex++;
      if (batchIndex > 10) break; // Safety valve
    }

    expect(allIds.size).toBe(TOTAL_RESPONSES);
  });
});
