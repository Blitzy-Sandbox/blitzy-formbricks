/**
 * Unit tests for GET /api/stripe-connect/authorize
 *
 * Tests the Stripe Connect OAuth authorization initiation route.
 *
 * Coverage:
 * 1. Success: Authenticated user with valid organizationId → 302 redirect to Stripe
 * 2. Success with returnUrl: Passes returnUrl through to buildStripeConnectAuthorizeUrl
 * 3. Missing session → 401 Unauthorized
 * 4. Missing organizationId → 400 Bad Request
 * 5. Missing STRIPE_CLIENT_ID → 500 Internal Server Error
 * 6. Success without returnUrl: Uses undefined for returnUrl
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { GET } from "./route";

// Use vi.hoisted to prevent mock hoisting errors
const { mockGetServerSession, mockBuildStripeConnectAuthorizeUrl } = vi.hoisted(() => ({
  mockGetServerSession: vi.fn(),
  mockBuildStripeConnectAuthorizeUrl: vi.fn(),
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

// Mock Stripe Connect service
vi.mock("@/modules/ee/stripe-connect/lib/stripe-connect", () => ({
  buildStripeConnectAuthorizeUrl: mockBuildStripeConnectAuthorizeUrl,
}));

describe("GET /api/stripe-connect/authorize", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const makeRequest = (params: Record<string, string> = {}) => {
    const url = new URL("http://localhost:3000/api/stripe-connect/authorize");
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    return new Request(url.toString(), { method: "GET" });
  };

  test("should redirect to Stripe OAuth URL on success", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockBuildStripeConnectAuthorizeUrl.mockReturnValue(
      "https://connect.stripe.com/oauth/authorize?client_id=ca_test&state=encoded"
    );

    const response = await GET(makeRequest({ organizationId: "org-1" }));

    expect(response.status).toBe(307); // NextResponse.redirect uses 307
    expect(response.headers.get("location")).toContain("connect.stripe.com");
    expect(mockBuildStripeConnectAuthorizeUrl).toHaveBeenCalledWith("org-1", undefined);
  });

  test("should pass returnUrl to buildStripeConnectAuthorizeUrl when provided", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockBuildStripeConnectAuthorizeUrl.mockReturnValue(
      "https://connect.stripe.com/oauth/authorize?client_id=ca_test&state=encoded"
    );

    const returnUrl = "http://localhost:3000/environments/env-1/surveys/survey-1/edit";
    const response = await GET(makeRequest({ organizationId: "org-1", returnUrl }));

    expect(response.status).toBe(307);
    expect(mockBuildStripeConnectAuthorizeUrl).toHaveBeenCalledWith("org-1", returnUrl);
  });

  test("should return 401 when user is not authenticated", async () => {
    mockGetServerSession.mockResolvedValue(null);

    const response = await GET(makeRequest({ organizationId: "org-1" }));
    const body = await response.json();

    expect(response.status).toBe(401);
    expect(body.error).toBe("Unauthorized");
  });

  test("should return 400 when organizationId is missing", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });

    const response = await GET(makeRequest());
    const body = await response.json();

    expect(response.status).toBe(400);
    expect(body.error).toContain("organizationId");
  });

  test("should return 500 when STRIPE_CLIENT_ID is not configured", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockBuildStripeConnectAuthorizeUrl.mockReturnValue(null);

    const response = await GET(makeRequest({ organizationId: "org-1" }));
    const body = await response.json();

    expect(response.status).toBe(500);
    expect(body.error).toContain("STRIPE_CLIENT_ID");
  });

  test("should use undefined for returnUrl when not provided", async () => {
    mockGetServerSession.mockResolvedValue({ user: { id: "user-1" } });
    mockBuildStripeConnectAuthorizeUrl.mockReturnValue(
      "https://connect.stripe.com/oauth/authorize?client_id=ca_test&state=encoded"
    );

    await GET(makeRequest({ organizationId: "org-1" }));

    // returnUrl should be undefined when not provided in query params
    expect(mockBuildStripeConnectAuthorizeUrl).toHaveBeenCalledWith("org-1", undefined);
  });
});
