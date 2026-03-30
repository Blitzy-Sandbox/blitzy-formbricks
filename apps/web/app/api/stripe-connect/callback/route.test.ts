/**
 * Unit tests for GET /api/stripe-connect/callback
 *
 * Tests the Stripe Connect OAuth callback route that exchanges the authorization
 * code for connected account credentials and stores them on the organization.
 *
 * Coverage:
 * 1. Success: Valid code + state → credentials saved, redirect to success URL
 * 2. Missing session → 401 Unauthorized
 * 3. OAuth error from Stripe (user denied) → redirect with error parameter
 * 4. Missing authorization code → 400 Bad Request
 * 5. Missing state (organizationId) → 400 Bad Request
 * 6. exchangeStripeConnectCode throws → redirect with error parameter
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { GET } from "./route";

// Use vi.hoisted to prevent mock hoisting errors
const { mockGetServerSession, mockExchangeStripeConnectCode, mockSaveStripeConnectAccount } = vi.hoisted(
  () => ({
    mockGetServerSession: vi.fn(),
    mockExchangeStripeConnectCode: vi.fn(),
    mockSaveStripeConnectAccount: vi.fn(),
  })
);

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
}));

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

  test("should exchange code and save credentials on success", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
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

    expect(response.status).toBe(307); // NextResponse.redirect
    expect(response.headers.get("location")).toContain("stripe_connect_success=1");
    expect(mockExchangeStripeConnectCode).toHaveBeenCalledWith("auth_code_123");
    expect(mockSaveStripeConnectAccount).toHaveBeenCalledWith("org-1", "acct_test_123", "pk_live_test");
  });

  test("should return 401 when user is not authenticated", async () => {
    mockGetServerSession.mockResolvedValue(null);

    const response = await GET(makeRequest({ code: "auth_code_123", state: "org-1" }));
    const body = await response.json();

    expect(response.status).toBe(401);
    expect(body.error).toBe("Unauthorized");
  });

  test("should redirect with error when Stripe returns OAuth error", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });

    const response = await GET(
      makeRequest({
        error: "access_denied",
        error_description: "The user denied your request",
        state: "org-1",
      })
    );

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toContain("stripe_connect_error");
    expect(mockExchangeStripeConnectCode).not.toHaveBeenCalled();
  });

  test("should return 400 when authorization code is missing", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });

    const response = await GET(makeRequest({ state: "org-1" }));
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

  test("should redirect with error when exchangeStripeConnectCode fails", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockExchangeStripeConnectCode.mockRejectedValue(new Error("Stripe API connection failed"));

    const response = await GET(makeRequest({ code: "auth_code_bad", state: "org-1" }));

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toContain("stripe_connect_error");
  });
});
