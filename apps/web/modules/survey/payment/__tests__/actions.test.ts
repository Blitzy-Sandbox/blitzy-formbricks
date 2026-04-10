import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/constants";
import { getOrganizationByEnvironmentId } from "@/lib/organization/service";
import { getSurvey } from "@/lib/survey/service";
import { createPaymentIntent } from "@/modules/survey/payment/lib/stripe";
import { createPaymentIntentAction } from "../actions";

// Mock the unauthenticated action client so .schema().action() extracts the inner handler function.
// This allows calling createPaymentIntentAction directly with { parsedInput } in tests,
// bypassing the safe-action middleware and Zod schema parsing while testing the core logic.
vi.mock("@/lib/utils/action-client", () => ({
  actionClient: {
    schema: vi.fn().mockReturnThis(),
    action: vi.fn((fn: Function) => fn),
  },
}));

// Mock getSurvey to control survey lookup behavior without hitting the database.
vi.mock("@/lib/survey/service", () => ({
  getSurvey: vi.fn(),
}));

// Mock getOrganizationByEnvironmentId to control organization lookup without hitting the database.
vi.mock("@/lib/organization/service", () => ({
  getOrganizationByEnvironmentId: vi.fn(),
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
  const validInput = {
    surveyId: "survey-test-123",
    currency: "usd" as const,
    amount: 1000,
  };

  const mockPaymentIntentResult = {
    clientSecret: "pi_test_secret_abc123",
  };

  // Create a mock survey that has a matching Payment element in blocks.
  // The action uses survey.blocks.flatMap(block => block.elements) to find Payment elements.
  const mockSurveyWithPayment = {
    id: "survey-test-123",
    environmentId: "env-test-123",
    blocks: [
      {
        id: "block1",
        elements: [
          {
            id: "q1",
            type: TSurveyElementTypeEnum.Payment,
            amount: 1000,
            currency: "usd",
            stripeIntegration: { publicKey: "pk_test_123" },
          },
        ],
      },
    ],
  };

  // Mock organization with connected Stripe account
  const mockOrganizationWithStripe = {
    id: "org-test-123",
    stripeConnectAccountId: "acct_test_connected",
    stripeConnectPublishableKey: "pk_live_connected",
  };

  // Mock organization without connected Stripe account
  const mockOrganizationWithoutStripe = {
    id: "org-test-456",
    stripeConnectAccountId: null,
    stripeConnectPublishableKey: null,
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Payment Intent Creation with Stripe Connect", () => {
    test("should create a payment intent with server-side org Stripe account lookup", async () => {
      vi.mocked(getSurvey).mockResolvedValue(mockSurveyWithPayment as any);
      vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(mockOrganizationWithStripe as any);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const result = await createPaymentIntentAction({
        parsedInput: validInput,
      } as any);

      expect(getSurvey).toHaveBeenCalledWith(validInput.surveyId);
      expect(getOrganizationByEnvironmentId).toHaveBeenCalledWith("env-test-123");
      expect(createPaymentIntent).toHaveBeenCalledWith(
        validInput.amount,
        validInput.currency,
        "acct_test_connected",
        validInput.surveyId
      );
      expect(result).toEqual(mockPaymentIntentResult);
    });

    test("should accept EUR currency", async () => {
      const eurSurvey = {
        ...mockSurveyWithPayment,
        blocks: [
          { id: "block1", elements: [{ ...mockSurveyWithPayment.blocks[0].elements[0], currency: "eur" }] },
        ],
      };
      vi.mocked(getSurvey).mockResolvedValue(eurSurvey as any);
      vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(mockOrganizationWithStripe as any);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const eurInput = { ...validInput, currency: "eur" as const };
      await createPaymentIntentAction({ parsedInput: eurInput } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(
        eurInput.amount,
        "eur",
        "acct_test_connected",
        eurInput.surveyId
      );
    });

    test("should accept GBP currency", async () => {
      const gbpSurvey = {
        ...mockSurveyWithPayment,
        blocks: [
          { id: "block1", elements: [{ ...mockSurveyWithPayment.blocks[0].elements[0], currency: "gbp" }] },
        ],
      };
      vi.mocked(getSurvey).mockResolvedValue(gbpSurvey as any);
      vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(mockOrganizationWithStripe as any);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const gbpInput = { ...validInput, currency: "gbp" as const };
      await createPaymentIntentAction({ parsedInput: gbpInput } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(
        gbpInput.amount,
        "gbp",
        "acct_test_connected",
        gbpInput.surveyId
      );
    });
  });

  describe("Survey Validation (Unauthenticated)", () => {
    test("should throw when survey does not exist", async () => {
      vi.mocked(getSurvey).mockResolvedValue(null);

      await expect(createPaymentIntentAction({ parsedInput: validInput } as any)).rejects.toThrow();

      expect(createPaymentIntent).not.toHaveBeenCalled();
    });

    test("should throw when survey has no matching Payment element", async () => {
      const surveyWithoutPayment = {
        id: "survey-test-123",
        environmentId: "env-test-123",
        blocks: [{ id: "block1", elements: [{ id: "q1", type: TSurveyElementTypeEnum.OpenText }] }],
      };
      vi.mocked(getSurvey).mockResolvedValue(surveyWithoutPayment as any);

      await expect(createPaymentIntentAction({ parsedInput: validInput } as any)).rejects.toThrow();

      expect(createPaymentIntent).not.toHaveBeenCalled();
    });

    test("should throw when Payment element amount does not match", async () => {
      const surveyWithDifferentAmount = {
        ...mockSurveyWithPayment,
        blocks: [
          { id: "block1", elements: [{ ...mockSurveyWithPayment.blocks[0].elements[0], amount: 2000 }] },
        ],
      };
      vi.mocked(getSurvey).mockResolvedValue(surveyWithDifferentAmount as any);

      await expect(createPaymentIntentAction({ parsedInput: validInput } as any)).rejects.toThrow();

      expect(createPaymentIntent).not.toHaveBeenCalled();
    });

    test("should throw when Payment element currency does not match", async () => {
      const surveyWithDifferentCurrency = {
        ...mockSurveyWithPayment,
        blocks: [
          { id: "block1", elements: [{ ...mockSurveyWithPayment.blocks[0].elements[0], currency: "eur" }] },
        ],
      };
      vi.mocked(getSurvey).mockResolvedValue(surveyWithDifferentCurrency as any);

      await expect(createPaymentIntentAction({ parsedInput: validInput } as any)).rejects.toThrow();

      expect(createPaymentIntent).not.toHaveBeenCalled();
    });
  });

  describe("Stripe Connect Organization Lookup", () => {
    test("should throw when organization is not found", async () => {
      vi.mocked(getSurvey).mockResolvedValue(mockSurveyWithPayment as any);
      vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(null);

      await expect(createPaymentIntentAction({ parsedInput: validInput } as any)).rejects.toThrow();

      expect(createPaymentIntent).not.toHaveBeenCalled();
    });

    test("should throw when organization has no connected Stripe account", async () => {
      vi.mocked(getSurvey).mockResolvedValue(mockSurveyWithPayment as any);
      vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(mockOrganizationWithoutStripe as any);

      await expect(createPaymentIntentAction({ parsedInput: validInput } as any)).rejects.toThrow(
        "No Stripe account is connected"
      );

      expect(createPaymentIntent).not.toHaveBeenCalled();
    });
  });

  describe("Error Handling", () => {
    test("should propagate errors from createPaymentIntent", async () => {
      vi.mocked(getSurvey).mockResolvedValue(mockSurveyWithPayment as any);
      vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(mockOrganizationWithStripe as any);
      vi.mocked(createPaymentIntent).mockRejectedValue(
        new Error("An unexpected error occurred while processing your payment. Please try again.")
      );

      await expect(createPaymentIntentAction({ parsedInput: validInput } as any)).rejects.toThrow(
        "An unexpected error occurred while processing your payment. Please try again."
      );
    });
  });

  describe("Input Validation (Zod Schema)", () => {
    test("should accept minimum valid amount of 1", async () => {
      const minAmountSurvey = {
        ...mockSurveyWithPayment,
        blocks: [{ id: "block1", elements: [{ ...mockSurveyWithPayment.blocks[0].elements[0], amount: 1 }] }],
      };
      vi.mocked(getSurvey).mockResolvedValue(minAmountSurvey as any);
      vi.mocked(getOrganizationByEnvironmentId).mockResolvedValue(mockOrganizationWithStripe as any);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const minAmountInput = { ...validInput, amount: 1 };
      const result = await createPaymentIntentAction({
        parsedInput: minAmountInput,
      } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(1, "usd", "acct_test_connected", validInput.surveyId);
      expect(result).toEqual(mockPaymentIntentResult);
    });
  });
});
