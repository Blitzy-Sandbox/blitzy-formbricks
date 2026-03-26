/**
 * Unit tests for POST /api/v1/client/payment-intent
 *
 * Tests the unauthenticated payment-intent creation endpoint that creates
 * Stripe PaymentIntents for survey Payment elements. This route is used by
 * embedded link surveys where respondents are anonymous, so security is
 * enforced by validating that the requested amount and currency match a
 * Payment element actually configured in the survey.
 *
 * Coverage:
 *  1. OPTIONS handler returns 200 with CORS headers
 *  2. Valid POST → returns { data: { clientSecret: string } }
 *  3. Missing surveyId → 400
 *  4. amount < 1 or non-integer → 400
 *  5. Invalid currency → 400
 *  6. Malformed JSON body → 400
 *  7. Survey not found (getSurvey returns null) → 404
 *  8. No matching Payment element in survey blocks → 404
 *  9. createPaymentIntent throws → 500
 */
import { afterEach, describe, expect, test, vi } from "vitest";
import { getSurvey } from "@/lib/survey/service";
import { createPaymentIntent } from "@/modules/survey/payment/lib/stripe";
// Import the route handlers AFTER setting up mocks
import { OPTIONS, POST } from "./route";

// ---------------------------------------------------------------------------
// Mocks — set up before importing the route module
// ---------------------------------------------------------------------------

// Mock @formbricks/logger to suppress log output during tests
vi.mock("@formbricks/logger", () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

// Mock getSurvey from @/lib/survey/service
vi.mock("@/lib/survey/service", () => ({
  getSurvey: vi.fn(),
}));

// Mock createPaymentIntent from @/modules/survey/payment/lib/stripe
vi.mock("@/modules/survey/payment/lib/stripe", () => ({
  createPaymentIntent: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Creates a mock Request object with JSON body for POST handler testing.
 * Uses the Web API Request constructor available in Node.js 18+.
 */
const makeJsonRequest = (body: unknown): Request => {
  return new Request("http://localhost:3000/api/v1/client/payment-intent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
};

/**
 * Creates a mock Request with an invalid (non-JSON) body to test
 * malformed JSON error handling.
 */
const makeMalformedRequest = (): Request => {
  return new Request("http://localhost:3000/api/v1/client/payment-intent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "not valid json {{{",
  });
};

/**
 * Builds a minimal mock survey object that contains a Payment element
 * in its blocks. The structure mirrors the real TSurvey shape for
 * the fields the route handler accesses.
 */
const buildMockSurveyWithPaymentBlock = (
  amount: number = 1000,
  currency: string = "usd"
): Record<string, unknown> => ({
  id: "survey-test-001",
  name: "Payment Survey",
  blocks: [
    {
      id: "block-1",
      elements: [
        {
          id: "el-opentext-1",
          type: "openText",
          headline: { default: "What is your name?" },
        },
        {
          id: "el-payment-1",
          type: "payment",
          headline: { default: "Complete payment" },
          amount,
          currency,
        },
      ],
    },
  ],
});

/**
 * Builds a mock survey without any Payment elements.
 */
const buildMockSurveyWithoutPayment = (): Record<string, unknown> => ({
  id: "survey-test-002",
  name: "Non-Payment Survey",
  blocks: [
    {
      id: "block-1",
      elements: [
        {
          id: "el-opentext-1",
          type: "openText",
          headline: { default: "What is your name?" },
        },
      ],
    },
  ],
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("POST /api/v1/client/payment-intent", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  // -------------------------------------------------------------------------
  // Test 1: OPTIONS handler returns 200 with CORS headers
  // -------------------------------------------------------------------------
  test("OPTIONS handler returns 200 with CORS headers", async () => {
    const response = await OPTIONS();

    expect(response.status).toBe(200);

    // The responses.successResponse with cors=true sets CORS headers
    expect(response.headers.get("Access-Control-Allow-Origin")).toBe("*");
    expect(response.headers.get("Access-Control-Allow-Methods")).toContain("GET");
    expect(response.headers.get("Access-Control-Allow-Methods")).toContain("POST");
    expect(response.headers.get("Access-Control-Allow-Headers")).toContain("Content-Type");

    // Verify cache header is set
    expect(response.headers.get("Cache-Control")).toBe("public, s-maxage=3600, max-age=3600");
  });

  // -------------------------------------------------------------------------
  // Test 2: Valid POST → returns { data: { clientSecret: string } }
  // -------------------------------------------------------------------------
  test("valid POST returns 200 with clientSecret", async () => {
    const mockSurvey = buildMockSurveyWithPaymentBlock(1000, "usd");
    vi.mocked(getSurvey).mockResolvedValue(mockSurvey as any);
    vi.mocked(createPaymentIntent).mockResolvedValue({
      clientSecret: "pi_test_secret_abc123",
    });

    const request = makeJsonRequest({
      surveyId: "survey-test-001",
      amount: 1000,
      currency: "usd",
    });

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.data).toEqual({ clientSecret: "pi_test_secret_abc123" });

    // Verify getSurvey was called with the correct surveyId
    expect(getSurvey).toHaveBeenCalledWith("survey-test-001");

    // Verify createPaymentIntent was called with correct parameters
    expect(createPaymentIntent).toHaveBeenCalledWith(1000, "usd", undefined, "survey-test-001");
  });

  // -------------------------------------------------------------------------
  // Test 3: Missing surveyId → 400
  // -------------------------------------------------------------------------
  test("missing surveyId returns 400 bad request", async () => {
    const request = makeJsonRequest({
      amount: 1000,
      currency: "usd",
    });

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.code).toBe("bad_request");
    expect(body.message).toContain("surveyId");
  });

  // -------------------------------------------------------------------------
  // Test 4a: amount less than 1 → 400
  // -------------------------------------------------------------------------
  test("amount less than 1 returns 400 bad request", async () => {
    const request = makeJsonRequest({
      surveyId: "survey-test-001",
      amount: 0,
      currency: "usd",
    });

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.code).toBe("bad_request");
    expect(body.message).toContain("amount");
  });

  // -------------------------------------------------------------------------
  // Test 4b: non-integer amount → 400
  // -------------------------------------------------------------------------
  test("non-integer amount returns 400 bad request", async () => {
    const request = makeJsonRequest({
      surveyId: "survey-test-001",
      amount: 10.5,
      currency: "usd",
    });

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.code).toBe("bad_request");
    expect(body.message).toContain("amount");
  });

  // -------------------------------------------------------------------------
  // Test 5: Invalid currency (not usd/eur/gbp) → 400
  // -------------------------------------------------------------------------
  test("invalid currency returns 400 bad request", async () => {
    const request = makeJsonRequest({
      surveyId: "survey-test-001",
      amount: 1000,
      currency: "jpy",
    });

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.code).toBe("bad_request");
    expect(body.message).toContain("currency");
  });

  // -------------------------------------------------------------------------
  // Test 6: Malformed JSON body → 400
  // -------------------------------------------------------------------------
  test("malformed JSON body returns 400 bad request", async () => {
    const request = makeMalformedRequest();

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.code).toBe("bad_request");
    expect(body.message).toContain("Malformed JSON");
  });

  // -------------------------------------------------------------------------
  // Test 7: Survey not found (getSurvey returns null) → 404
  // -------------------------------------------------------------------------
  test("survey not found returns 404", async () => {
    vi.mocked(getSurvey).mockResolvedValue(null as any);

    const request = makeJsonRequest({
      surveyId: "nonexistent-survey",
      amount: 1000,
      currency: "usd",
    });

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(404);
    expect(body.code).toBe("not_found");
    expect(body.message).toContain("Survey");
  });

  // -------------------------------------------------------------------------
  // Test 8: No matching Payment element in survey blocks → 404
  // -------------------------------------------------------------------------
  test("no matching Payment element returns 404", async () => {
    const mockSurvey = buildMockSurveyWithoutPayment();
    vi.mocked(getSurvey).mockResolvedValue(mockSurvey as any);

    const request = makeJsonRequest({
      surveyId: "survey-test-002",
      amount: 1000,
      currency: "usd",
    });

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(404);
    expect(body.code).toBe("not_found");
    expect(body.message).toContain("Payment element");
  });

  // -------------------------------------------------------------------------
  // Test 9: createPaymentIntent throws → 500
  // -------------------------------------------------------------------------
  test("createPaymentIntent failure returns 500 internal server error", async () => {
    const mockSurvey = buildMockSurveyWithPaymentBlock(1000, "usd");
    vi.mocked(getSurvey).mockResolvedValue(mockSurvey as any);
    vi.mocked(createPaymentIntent).mockRejectedValue(new Error("Stripe API connection failed"));

    const request = makeJsonRequest({
      surveyId: "survey-test-001",
      amount: 1000,
      currency: "usd",
    });

    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(500);
    expect(body.code).toBe("internal_server_error");
    expect(body.message).toContain("payment intent");
  });
});
