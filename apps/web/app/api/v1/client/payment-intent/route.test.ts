/**
 * Unit tests for POST /api/v1/client/payment-intent
 *
 * Tests the unauthenticated payment-intent creation endpoint that creates
 * Stripe PaymentIntents for survey Payment elements. This route is used by
 * embedded link surveys where respondents are anonymous, so security is
 * enforced by validating that the requested amount and currency match a
 * Payment element actually configured in the survey.
 *
 * The connected Stripe account is resolved server-side from the organization's
 * stored Stripe Connect credentials — the client does NOT provide stripeAccountId.
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
 * 10. Organization has no connected Stripe account → 400
 * 11. Organization not found → 500
 */
import { afterEach, describe, expect, test, vi } from "vitest";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/constants";
import { getOrganizationByEnvironmentId } from "@/lib/organization/service";
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

// Mock getOrganizationByEnvironmentId from @/lib/organization/service
vi.mock("@/lib/organization/service", () => ({
  getOrganizationByEnvironmentId: vi.fn(),
}));

// Mock createPaymentIntent from @/modules/survey/payment/lib/stripe
vi.mock("@/modules/survey/payment/lib/stripe", () => ({
  createPaymentIntent: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/** Builds a mock survey with a Payment element in its blocks array. */
const buildMockSurveyWithPaymentBlock = (amount: number, currency: string) => ({
  id: "survey-test-001",
  environmentId: "env-test-001",
  blocks: [
    {
      id: "block-1",
      elements: [
        {
          id: "el-payment-1",
          type: TSurveyElementTypeEnum.Payment,
          amount,
          currency,
          stripeIntegration: { publicKey: "pk_test_123" },
        },
      ],
    },
  ],
});

/** Builds a mock survey without any Payment elements. */
const buildMockSurveyWithoutPayment = () => ({
  id: "survey-test-002",
  environmentId: "env-test-002",
  blocks: [
    {
      id: "block-1",
      elements: [{ id: "el-open-1", type: TSurveyElementTypeEnum.OpenText }],
    },
  ],
});

/** Builds a mock organization with a connected Stripe account. */
const buildMockOrganizationWithStripe = () => ({
  id: "org-test-001",
  stripeConnectAccountId: "acct_test_connected",
  stripeConnectPublishableKey: "pk_live_connected",
});

/** Builds a mock organization without a connected Stripe account. */
const buildMockOrganizationWithoutStripe = () => ({
  id: "org-test-002",
  stripeConnectAccountId: null,
  stripeConnectPublishableKey: null,
});

/** Creates a JSON Request with the given body. */
const makeJsonRequest = (body: Record<string, unknown>) =>
  new Request("http://localhost/api/v1/client/payment-intent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

/** Creates a malformed (non-JSON) Request. */
const makeMalformedRequest = () =>
  new Request("http://localhost/api/v1/client/payment-intent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "this is not valid json{{{",
  });

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe("POST /api/v1/client/payment-intent", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Test 1: OPTIONS returns 200 (CORS preflight)
  // -------------------------------------------------------------------------
  test("OPTIONS returns 200 for CORS preflight", async () => {
    const response = await OPTIONS();
    expect(response.status).toBe(200);
  });

  // -------------------------------------------------------------------------
  // Test 2: Valid POST with connected Stripe account → 200
  // -------------------------------------------------------------------------
  test("valid POST returns 200 with clientSecret", async () => {
    const mockSurvey = buildMockSurveyWithPaymentBlock(1000, "usd");
    vi.mocked(getSurvey).mockResolvedValue(mockSurvey as any);
    vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(buildMockOrganizationWithStripe() as any);
    vi.mocked(createPaymentIntent).mockResolvedValue({ clientSecret: "pi_test_secret_001" });

    const request = makeJsonRequest({ surveyId: "survey-test-001", amount: 1000, currency: "usd" });
    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(200);
    expect(body.data.clientSecret).toBe("pi_test_secret_001");
    expect(createPaymentIntent).toHaveBeenCalledWith(1000, "usd", "acct_test_connected", "survey-test-001");
  });

  // -------------------------------------------------------------------------
  // Test 3: Missing surveyId → 400
  // -------------------------------------------------------------------------
  test("missing surveyId returns 400 bad request", async () => {
    const request = makeJsonRequest({ amount: 1000, currency: "usd" });
    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.code).toBe("bad_request");
    expect(body.message).toContain("surveyId");
  });

  // -------------------------------------------------------------------------
  // Test 4: Invalid amount → 400
  // -------------------------------------------------------------------------
  test("invalid amount returns 400 bad request", async () => {
    const request = makeJsonRequest({ surveyId: "survey-test-001", amount: -5, currency: "usd" });
    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.code).toBe("bad_request");
    expect(body.message).toContain("amount");
  });

  // -------------------------------------------------------------------------
  // Test 5: Invalid currency → 400
  // -------------------------------------------------------------------------
  test("invalid currency returns 400 bad request", async () => {
    const request = makeJsonRequest({ surveyId: "survey-test-001", amount: 1000, currency: "jpy" });
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
  // Test 7: Survey not found → 404
  // -------------------------------------------------------------------------
  test("survey not found returns 404", async () => {
    vi.mocked(getSurvey).mockResolvedValue(null as any);

    const request = makeJsonRequest({ surveyId: "nonexistent-survey", amount: 1000, currency: "usd" });
    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(404);
    expect(body.code).toBe("not_found");
    expect(body.message).toContain("Survey");
  });

  // -------------------------------------------------------------------------
  // Test 8: No matching Payment element → 404
  // -------------------------------------------------------------------------
  test("no matching Payment element returns 404", async () => {
    const mockSurvey = buildMockSurveyWithoutPayment();
    vi.mocked(getSurvey).mockResolvedValue(mockSurvey as any);

    const request = makeJsonRequest({ surveyId: "survey-test-002", amount: 1000, currency: "usd" });
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
    vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(buildMockOrganizationWithStripe() as any);
    vi.mocked(createPaymentIntent).mockRejectedValue(new Error("Stripe API connection failed"));

    const request = makeJsonRequest({ surveyId: "survey-test-001", amount: 1000, currency: "usd" });
    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(500);
    expect(body.code).toBe("internal_server_error");
    expect(body.message).toContain("payment intent");
  });

  // -------------------------------------------------------------------------
  // Test 10: Organization has no connected Stripe account → 400
  // -------------------------------------------------------------------------
  test("no connected Stripe account returns 400 bad request", async () => {
    const mockSurvey = buildMockSurveyWithPaymentBlock(1000, "usd");
    vi.mocked(getSurvey).mockResolvedValue(mockSurvey as any);
    vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(buildMockOrganizationWithoutStripe() as any);

    const request = makeJsonRequest({ surveyId: "survey-test-001", amount: 1000, currency: "usd" });
    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.code).toBe("bad_request");
    expect(body.message).toContain("No Stripe account");
  });

  // -------------------------------------------------------------------------
  // Test 11: Organization not found → 500
  // -------------------------------------------------------------------------
  test("organization not found returns 500 internal server error", async () => {
    const mockSurvey = buildMockSurveyWithPaymentBlock(1000, "usd");
    vi.mocked(getSurvey).mockResolvedValue(mockSurvey as any);
    vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(null as any);

    const request = makeJsonRequest({ surveyId: "survey-test-001", amount: 1000, currency: "usd" });
    const response = await POST(request);
    const body = await response.json();

    expect(response.status).toBe(500);
    expect(body.code).toBe("internal_server_error");
    expect(body.message).toContain("organization");
  });
});
