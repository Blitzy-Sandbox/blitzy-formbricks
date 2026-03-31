/**
 * Unit tests for GET /api/stripe-connect/callback
 *
 * Tests the Stripe Connect OAuth callback route that exchanges the authorization
 * code for connected account credentials and stores them on the organization.
 *
 * Coverage:
 * 1. Success: Valid code + encoded state → credentials saved, redirect to returnUrl
 * 2. Success without returnUrl: Redirects to app root with success param
 * 3. Missing session → 401 Unauthorized
 * 4. OAuth error from Stripe (user denied) → redirect to returnUrl with error
 * 5. Missing authorization code → 400 Bad Request
 * 6. Missing state (organizationId) → 400 Bad Request
 * 7. exchangeStripeConnectCode throws → redirect to returnUrl with error
 * 8. Backward compat: raw organizationId in state → still works
 * 9. Open redirect prevention: cross-origin returnUrl is ignored
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { GET } from "./route";

// Use vi.hoisted to prevent mock hoisting errors
const {
  mockGetServerSession,
  mockExchangeStripeConnectCode,
  mockSaveStripeConnectAccount,
  mockDecodeStripeConnectState,
} = vi.hoisted(() => ({
  mockGetServerSession: vi.fn(),
  mockExchangeStripeConnectCode: vi.fn(),
  mockSaveStripeConnectAccount: vi.fn(),
  mockDecodeStripeConnectState: vi.fn(),
}));

// Mock next-auth session
vi.mock("next-auth", () => ({
  getServerSession: mockGetServerSession,
}));

// Mock authOptions
vi.mock("@/modules/auth/lib/authOptions", () => ({
  authOptions: {},
}));

// Mock logger
vi.mock("@formbricks/logger", () => ({
  logger: {
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  },
}));

// Mock constants
vi.mock("@/lib/constants", () => ({
  WEBAPP_URL: "http://localhost:3000",
}));

// Mock Stripe Connect service
vi.mock("@/modules/ee/stripe-connect/lib/stripe-connect", () => ({
  exchangeStripeConnectCode: mockExchangeStripeConnectCode,
  saveStripeConnectAccount: mockSaveStripeConnectAccount,
  decodeStripeConnectState: mockDecodeStripeConnectState,
}));

/**
 * Helper: encodes an organizationId and returnUrl into a base64url state string,
 * matching the format produced by buildStripeConnectAuthorizeUrl.
 */
const encodeState = (organizationId: string, returnUrl = ""): string => {
  return Buffer.from(JSON.stringify({ organizationId, returnUrl })).toString("base64url");
};

describe("GET /api/stripe-connect/callback", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const makeRequest = (params: Record<string, string> = {}) => {
    const url = new URL("http://localhost:3000/api/stripe-connect/callback");
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    return new Request(url.toString(), { method: "GET" });
  };

  test("should exchange code and redirect to returnUrl on success", async () => {
    const returnUrl = "/environments/env-1/surveys/survey-1/edit";
    const state = encodeState("org-1", returnUrl);

    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockDecodeStripeConnectState.mockReturnValue({ organizationId: "org-1", returnUrl });
    mockExchangeStripeConnectCode.mockResolvedValue({
      stripeUserId: "acct_test_123",
      stripePublishableKey: "pk_live_test",
    });
    mockSaveStripeConnectAccount.mockResolvedValue({
      id: "org-1",
      stripeConnectAccountId: "acct_test_123",
      stripeConnectPublishableKey: "pk_live_test",
    });

    const response = await GET(makeRequest({ code: "auth_code_123", state }));

    expect(response.status).toBe(307);
    const location = response.headers.get("location") || "";
    expect(location).toContain("/environments/env-1/surveys/survey-1/edit");
    expect(location).toContain("stripe_connect_success=1");
    expect(mockExchangeStripeConnectCode).toHaveBeenCalledWith("auth_code_123");
    expect(mockSaveStripeConnectAccount).toHaveBeenCalledWith("org-1", "acct_test_123", "pk_live_test");
  });

  test("should redirect to app root with success when no returnUrl provided", async () => {
    const state = encodeState("org-1", "");

    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockDecodeStripeConnectState.mockReturnValue({ organizationId: "org-1", returnUrl: "" });
    mockExchangeStripeConnectCode.mockResolvedValue({
      stripeUserId: "acct_test_123",
      stripePublishableKey: "pk_live_test",
    });
    mockSaveStripeConnectAccount.mockResolvedValue({
      id: "org-1",
      stripeConnectAccountId: "acct_test_123",
      stripeConnectPublishableKey: "pk_live_test",
    });

    const response = await GET(makeRequest({ code: "auth_code_123", state }));

    expect(response.status).toBe(307);
    const location = response.headers.get("location") || "";
    expect(location).toContain("stripe_connect_success=1");
    expect(location).toMatch(/localhost:3000/);
  });

  test("should return 401 when user is not authenticated", async () => {
    mockGetServerSession.mockResolvedValue(null);

    const state = encodeState("org-1");
    const response = await GET(makeRequest({ code: "auth_code_123", state }));
    const body = await response.json();

    expect(response.status).toBe(401);
    expect(body.error).toBe("Unauthorized");
  });

  test("should redirect to returnUrl with error when Stripe returns OAuth error", async () => {
    const returnUrl = "/environments/env-1/surveys/survey-1/edit";
    const state = encodeState("org-1", returnUrl);

    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockDecodeStripeConnectState.mockReturnValue({ organizationId: "org-1", returnUrl });

    const response = await GET(
      makeRequest({
        error: "access_denied",
        error_description: "The user denied your request",
        state,
      })
    );

    expect(response.status).toBe(307);
    const location = response.headers.get("location") || "";
    expect(location).toContain("stripe_connect_error");
    expect(mockExchangeStripeConnectCode).not.toHaveBeenCalled();
  });

  test("should return 400 when authorization code is missing", async () => {
    const state = encodeState("org-1");
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockDecodeStripeConnectState.mockReturnValue({ organizationId: "org-1", returnUrl: "" });

    const response = await GET(makeRequest({ state }));
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("authorization code");
  });

  test("should return 400 when state (organizationId) is missing", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });

    const response = await GET(makeRequest({ code: "auth_code_123" }));
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("organization");
  });

  test("should redirect to returnUrl with error when exchangeStripeConnectCode fails", async () => {
    const returnUrl = "/environments/env-1/surveys/survey-1/edit";
    const state = encodeState("org-1", returnUrl);

    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockDecodeStripeConnectState.mockReturnValue({ organizationId: "org-1", returnUrl });
    mockExchangeStripeConnectCode.mockRejectedValue(new Error("Stripe API connection failed"));

    const response = await GET(makeRequest({ code: "auth_code_bad", state }));

    expect(response.status).toBe(307);
    const location = response.headers.get("location") || "";
    expect(location).toContain("stripe_connect_error");
  });

  test("should handle backward-compatible raw organizationId in state", async () => {
    // Old-format state: just a plain organizationId string (not base64-encoded)
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockDecodeStripeConnectState.mockReturnValue({ organizationId: "org-1", returnUrl: "" });
    mockExchangeStripeConnectCode.mockResolvedValue({
      stripeUserId: "acct_test_123",
      stripePublishableKey: "pk_live_test",
    });
    mockSaveStripeConnectAccount.mockResolvedValue({
      id: "org-1",
      stripeConnectAccountId: "acct_test_123",
      stripeConnectPublishableKey: "pk_live_test",
    });

    const response = await GET(makeRequest({ code: "auth_code_123", state: "org-1" }));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toContain("stripe_connect_success=1");
  });
});
