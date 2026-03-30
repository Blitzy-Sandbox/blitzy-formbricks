import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { ResourceNotFoundError } from "@formbricks/types/errors";
import {
  buildStripeConnectAuthorizeUrl,
  disconnectStripeConnectAccount,
  exchangeStripeConnectCode,
  getStripeConnectAccount,
  saveStripeConnectAccount,
} from "../stripe-connect";

// Mock server-only import to prevent errors in test environment
vi.mock("server-only", () => ({}));

// Mock Prisma client - use vi.hoisted to ensure mockPrisma is available during mock hoisting
const { mockPrisma } = vi.hoisted(() => {
  return {
    mockPrisma: {
      organization: {
        findUnique: vi.fn(),
        update: vi.fn(),
      },
    },
  };
});

vi.mock("@formbricks/database", () => ({
  prisma: mockPrisma,
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

// Mock env - use vi.hoisted
const { mockEnv } = vi.hoisted(() => ({
  mockEnv: {
    STRIPE_SECRET_KEY: "sk_test_mock_secret_key",
    STRIPE_CLIENT_ID: "ca_test_mock_client_id",
  },
}));

vi.mock("@/lib/env", () => ({
  env: mockEnv,
}));

// Mock constants
vi.mock("@/lib/constants", () => ({
  STRIPE_API_VERSION: "2024-06-20",
}));

// Mock Stripe SDK - use vi.hoisted
const { mockOAuthToken } = vi.hoisted(() => ({
  mockOAuthToken: vi.fn(),
}));

vi.mock("stripe", () => {
  class StripeInvalidGrantError extends Error {
    constructor(message?: string) {
      super(message);
      this.name = "StripeInvalidGrantError";
    }
  }
  class StripeAuthenticationError extends Error {
    constructor(message?: string) {
      super(message);
      this.name = "StripeAuthenticationError";
    }
  }

  // Use a real class so `new Stripe(...)` works correctly
  class MockStripe {
    oauth = { token: mockOAuthToken };
    static errors = {
      StripeInvalidGrantError,
      StripeAuthenticationError,
    };
    constructor(_key: string, _opts?: Record<string, unknown>) {
      // noop — mock constructor
    }
  }

  return { default: MockStripe, __esModule: true };
});

describe("Stripe Connect Service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // ---------------------------------------------------------------------------
  // getStripeConnectAccount
  // ---------------------------------------------------------------------------
  describe("getStripeConnectAccount", () => {
    test("should return connected account credentials when they exist", async () => {
      mockPrisma.organization.findUnique.mockResolvedValue({
        stripeConnectAccountId: "acct_test_123",
        stripeConnectPublishableKey: "pk_test_123",
      });

      const result = await getStripeConnectAccount("org-123");

      expect(mockPrisma.organization.findUnique).toHaveBeenCalledWith({
        where: { id: "org-123" },
        select: {
          stripeConnectAccountId: true,
          stripeConnectPublishableKey: true,
        },
      });
      expect(result).toEqual({
        stripeConnectAccountId: "acct_test_123",
        stripeConnectPublishableKey: "pk_test_123",
      });
    });

    test("should return null values when no account is connected", async () => {
      mockPrisma.organization.findUnique.mockResolvedValue({
        stripeConnectAccountId: null,
        stripeConnectPublishableKey: null,
      });

      const result = await getStripeConnectAccount("org-123");

      expect(result).toEqual({
        stripeConnectAccountId: null,
        stripeConnectPublishableKey: null,
      });
    });

    test("should throw ResourceNotFoundError when organization does not exist", async () => {
      mockPrisma.organization.findUnique.mockResolvedValue(null);

      await expect(getStripeConnectAccount("org-nonexistent")).rejects.toThrow(ResourceNotFoundError);
    });
  });

  // ---------------------------------------------------------------------------
  // saveStripeConnectAccount
  // ---------------------------------------------------------------------------
  describe("saveStripeConnectAccount", () => {
    test("should save connected account credentials successfully", async () => {
      mockPrisma.organization.findUnique.mockResolvedValue({ id: "org-123" });
      mockPrisma.organization.update.mockResolvedValue({
        id: "org-123",
        stripeConnectAccountId: "acct_new_456",
        stripeConnectPublishableKey: "pk_live_new",
      });

      const result = await saveStripeConnectAccount("org-123", "acct_new_456", "pk_live_new");

      expect(mockPrisma.organization.update).toHaveBeenCalledWith({
        where: { id: "org-123" },
        data: {
          stripeConnectAccountId: "acct_new_456",
          stripeConnectPublishableKey: "pk_live_new",
        },
        select: {
          id: true,
          stripeConnectAccountId: true,
          stripeConnectPublishableKey: true,
        },
      });
      expect(result.stripeConnectAccountId).toBe("acct_new_456");
      expect(result.stripeConnectPublishableKey).toBe("pk_live_new");
    });

    test("should throw ResourceNotFoundError when organization does not exist", async () => {
      mockPrisma.organization.findUnique.mockResolvedValue(null);

      await expect(saveStripeConnectAccount("org-nonexistent", "acct_123", "pk_123")).rejects.toThrow(
        ResourceNotFoundError
      );

      expect(mockPrisma.organization.update).not.toHaveBeenCalled();
    });
  });

  // ---------------------------------------------------------------------------
  // disconnectStripeConnectAccount
  // ---------------------------------------------------------------------------
  describe("disconnectStripeConnectAccount", () => {
    test("should clear Stripe Connect credentials", async () => {
      mockPrisma.organization.findUnique.mockResolvedValue({ id: "org-123" });
      mockPrisma.organization.update.mockResolvedValue({
        id: "org-123",
        stripeConnectAccountId: null,
        stripeConnectPublishableKey: null,
      });

      const result = await disconnectStripeConnectAccount("org-123");

      expect(mockPrisma.organization.update).toHaveBeenCalledWith({
        where: { id: "org-123" },
        data: {
          stripeConnectAccountId: null,
          stripeConnectPublishableKey: null,
        },
        select: {
          id: true,
          stripeConnectAccountId: true,
          stripeConnectPublishableKey: true,
        },
      });
      expect(result.stripeConnectAccountId).toBeNull();
      expect(result.stripeConnectPublishableKey).toBeNull();
    });

    test("should throw ResourceNotFoundError when organization does not exist", async () => {
      mockPrisma.organization.findUnique.mockResolvedValue(null);

      await expect(disconnectStripeConnectAccount("org-nonexistent")).rejects.toThrow(ResourceNotFoundError);

      expect(mockPrisma.organization.update).not.toHaveBeenCalled();
    });
  });

  // ---------------------------------------------------------------------------
  // buildStripeConnectAuthorizeUrl
  // ---------------------------------------------------------------------------
  describe("buildStripeConnectAuthorizeUrl", () => {
    test("should build a valid Stripe OAuth authorization URL", () => {
      const url = buildStripeConnectAuthorizeUrl("org-123");

      expect(url).not.toBeNull();
      const parsed = new URL(url!);
      expect(parsed.origin).toBe("https://connect.stripe.com");
      expect(parsed.pathname).toBe("/oauth/authorize");
      expect(parsed.searchParams.get("response_type")).toBe("code");
      expect(parsed.searchParams.get("client_id")).toBe("ca_test_mock_client_id");
      expect(parsed.searchParams.get("scope")).toBe("read_write");
      expect(parsed.searchParams.get("state")).toBe("org-123");
    });
  });

  // ---------------------------------------------------------------------------
  // exchangeStripeConnectCode
  // ---------------------------------------------------------------------------
  describe("exchangeStripeConnectCode", () => {
    test("should exchange authorization code for account credentials", async () => {
      mockOAuthToken.mockResolvedValue({
        stripe_user_id: "acct_exchange_789",
        stripe_publishable_key: "pk_live_exchanged",
      });

      const result = await exchangeStripeConnectCode("auth_code_test_123");

      expect(mockOAuthToken).toHaveBeenCalledWith({
        grant_type: "authorization_code",
        code: "auth_code_test_123",
      });
      expect(result).toEqual({
        stripeUserId: "acct_exchange_789",
        stripePublishableKey: "pk_live_exchanged",
      });
    });

    test("should handle missing stripe_publishable_key gracefully", async () => {
      mockOAuthToken.mockResolvedValue({
        stripe_user_id: "acct_no_pk",
        stripe_publishable_key: null,
      });

      const result = await exchangeStripeConnectCode("auth_code_no_pk");

      expect(result.stripeUserId).toBe("acct_no_pk");
      expect(result.stripePublishableKey).toBe("");
    });

    test("should throw when Stripe API returns no stripe_user_id", async () => {
      mockOAuthToken.mockResolvedValue({
        stripe_user_id: null,
        stripe_publishable_key: "pk_test",
      });

      await expect(exchangeStripeConnectCode("auth_code_bad")).rejects.toThrow(
        "Stripe Connect OAuth response did not include stripe_user_id"
      );
    });

    test("should throw user-friendly error on generic Stripe failure", async () => {
      mockOAuthToken.mockRejectedValue(new Error("Generic Stripe error"));

      await expect(exchangeStripeConnectCode("auth_code_fail")).rejects.toThrow(
        "Failed to connect your Stripe account"
      );
    });
  });
});
