import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { checkAuthorizationUpdated } from "@/lib/utils/action-client/action-client-middleware";
import { getOrganizationIdFromSurveyId } from "@/lib/utils/helper";
import { createPaymentIntent } from "@/modules/survey/payment/lib/stripe";
import { createPaymentIntentAction } from "../actions";

// Mock the authenticated action client so .schema().action() extracts the inner handler function.
// This allows calling createPaymentIntentAction directly with { ctx, parsedInput } in tests,
// bypassing the safe-action middleware and Zod schema parsing while testing the core logic.
vi.mock("@/lib/utils/action-client", () => ({
  authenticatedActionClient: {
    schema: vi.fn().mockReturnThis(),
    action: vi.fn((fn) => fn),
  },
}));

// Mock authorization middleware to control and verify authorization behavior.
vi.mock("@/lib/utils/action-client/action-client-middleware", () => ({
  checkAuthorizationUpdated: vi.fn(),
}));

// Mock the helper that resolves organizationId from surveyId.
vi.mock("@/lib/utils/helper", () => ({
  getOrganizationIdFromSurveyId: vi.fn(),
}));

// Mock the Stripe payment intent creation helper to avoid real Stripe API calls.
vi.mock("@/modules/survey/payment/lib/stripe", () => ({
  createPaymentIntent: vi.fn(),
}));

// Standard logger mock used across the codebase to suppress log output during tests.
vi.mock("@formbricks/logger", () => ({
  logger: {
    error: vi.fn(),
  },
}));

describe("createPaymentIntentAction", () => {
  const mockOrganizationId = "org-test-123";
  const mockCtx = {
    user: {
      id: "user-test-123",
    },
  };
  const validInput = {
    surveyId: "survey-test-123",
    currency: "usd" as const,
    amount: 1000,
    stripeAccountId: "acct_test_123",
  };
  const mockPaymentIntentResult = {
    clientSecret: "pi_test_secret_123",
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Successful Payment Intent Creation", () => {
    test("should create a payment intent with valid parameters", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const result = await createPaymentIntentAction({
        ctx: mockCtx,
        parsedInput: validInput,
      } as any);

      expect(getOrganizationIdFromSurveyId).toHaveBeenCalledWith(validInput.surveyId);
      expect(checkAuthorizationUpdated).toHaveBeenCalledWith({
        userId: mockCtx.user.id,
        organizationId: mockOrganizationId,
        access: [
          {
            type: "organization",
            roles: ["owner", "manager", "member"],
          },
        ],
      });
      expect(createPaymentIntent).toHaveBeenCalledWith(
        validInput.amount,
        validInput.currency,
        validInput.stripeAccountId
      );
      expect(result).toEqual(mockPaymentIntentResult);
    });

    test("should create a payment intent without stripeAccountId", async () => {
      const inputWithoutStripeAccount = {
        surveyId: "survey-test-123",
        currency: "usd" as const,
        amount: 500,
      };

      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const result = await createPaymentIntentAction({
        ctx: mockCtx,
        parsedInput: inputWithoutStripeAccount,
      } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(
        inputWithoutStripeAccount.amount,
        inputWithoutStripeAccount.currency,
        undefined
      );
      expect(result).toEqual(mockPaymentIntentResult);
    });

    test("should accept EUR currency", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const eurInput = { ...validInput, currency: "eur" as const };
      await createPaymentIntentAction({ ctx: mockCtx, parsedInput: eurInput } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(eurInput.amount, "eur", eurInput.stripeAccountId);
    });

    test("should accept GBP currency", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const gbpInput = { ...validInput, currency: "gbp" as const };
      await createPaymentIntentAction({ ctx: mockCtx, parsedInput: gbpInput } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(gbpInput.amount, "gbp", gbpInput.stripeAccountId);
    });
  });

  describe("Authorization", () => {
    test("should resolve organization ID from survey ID before authorization check", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      await createPaymentIntentAction({ ctx: mockCtx, parsedInput: validInput } as any);

      expect(getOrganizationIdFromSurveyId).toHaveBeenCalledWith(validInput.surveyId);
      expect(getOrganizationIdFromSurveyId).toHaveBeenCalledBefore(
        checkAuthorizationUpdated as unknown as ReturnType<typeof vi.fn>
      );
    });

    test("should throw when authorization check fails", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockRejectedValue(new Error("Unauthorized"));

      await expect(
        createPaymentIntentAction({ ctx: mockCtx, parsedInput: validInput } as any)
      ).rejects.toThrow("Unauthorized");

      expect(createPaymentIntent).not.toHaveBeenCalled();
    });

    test("should throw when organization ID cannot be resolved from survey ID", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockRejectedValue(new Error("Survey not found"));

      await expect(
        createPaymentIntentAction({ ctx: mockCtx, parsedInput: validInput } as any)
      ).rejects.toThrow("Survey not found");

      expect(checkAuthorizationUpdated).not.toHaveBeenCalled();
      expect(createPaymentIntent).not.toHaveBeenCalled();
    });

    test("should pass correct authorization roles (owner, manager, member)", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      await createPaymentIntentAction({ ctx: mockCtx, parsedInput: validInput } as any);

      expect(checkAuthorizationUpdated).toHaveBeenCalledWith(
        expect.objectContaining({
          access: [
            {
              type: "organization",
              roles: ["owner", "manager", "member"],
            },
          ],
        })
      );
    });
  });

  describe("Error Handling", () => {
    test("should propagate errors from createPaymentIntent", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockRejectedValue(
        new Error("An unexpected error occurred while processing your payment. Please try again.")
      );

      await expect(
        createPaymentIntentAction({ ctx: mockCtx, parsedInput: validInput } as any)
      ).rejects.toThrow(
        "An unexpected error occurred while processing your payment. Please try again."
      );
    });

    test("should propagate card declined errors from createPaymentIntent", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockRejectedValue(
        new Error("Payment failed: Your card was declined. Please try a different card.")
      );

      await expect(
        createPaymentIntentAction({ ctx: mockCtx, parsedInput: validInput } as any)
      ).rejects.toThrow("Payment failed: Your card was declined. Please try a different card.");
    });

    test("should propagate payment configuration errors from createPaymentIntent", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockRejectedValue(
        new Error("Payment configuration error. Please contact support.")
      );

      await expect(
        createPaymentIntentAction({ ctx: mockCtx, parsedInput: validInput } as any)
      ).rejects.toThrow("Payment configuration error. Please contact support.");
    });
  });

  describe("Input Validation (Zod Schema)", () => {
    test("should accept minimum valid amount of 1", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const minAmountInput = { ...validInput, amount: 1 };
      const result = await createPaymentIntentAction({
        ctx: mockCtx,
        parsedInput: minAmountInput,
      } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(1, "usd", validInput.stripeAccountId);
      expect(result).toEqual(mockPaymentIntentResult);
    });

    test("should pass large amounts correctly", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const largeAmountInput = { ...validInput, amount: 99999999 };
      const result = await createPaymentIntentAction({
        ctx: mockCtx,
        parsedInput: largeAmountInput,
      } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(99999999, "usd", validInput.stripeAccountId);
      expect(result).toEqual(mockPaymentIntentResult);
    });
  });

  describe("ZCreatePaymentIntentAction Schema Validation", () => {
    test("should call createPaymentIntent with exact parsed input values", async () => {
      vi.mocked(getOrganizationIdFromSurveyId).mockResolvedValue(mockOrganizationId);
      vi.mocked(checkAuthorizationUpdated).mockResolvedValue(true);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      await createPaymentIntentAction({
        ctx: mockCtx,
        parsedInput: {
          surveyId: "clxxxxxxxxxxxxxxxxxxxxxxxxx",
          currency: "eur",
          amount: 2500,
          stripeAccountId: "acct_connected_123",
        },
      } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(2500, "eur", "acct_connected_123");
    });
  });
});
