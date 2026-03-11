import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/constants";
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
    stripeAccountId: "acct_test_123",
  };

  const mockPaymentIntentResult = {
    clientSecret: "pi_test_secret_abc123",
  };

  // Create a mock survey that has a matching Payment element in blocks.
  // The action uses survey.blocks.flatMap(block => block.elements) to find Payment elements.
  const mockSurveyWithPayment = {
    id: "survey-test-123",
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

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Payment Intent Creation", () => {
    test("should create a payment intent with valid input", async () => {
      vi.mocked(getSurvey).mockResolvedValue(mockSurveyWithPayment as any);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const result = await createPaymentIntentAction({
        parsedInput: validInput,
      } as any);

      expect(getSurvey).toHaveBeenCalledWith(validInput.surveyId);
      expect(createPaymentIntent).toHaveBeenCalledWith(
        validInput.amount,
        validInput.currency,
        validInput.stripeAccountId,
        validInput.surveyId
      );
      expect(result).toEqual(mockPaymentIntentResult);
    });

    test("should create a payment intent without stripeAccountId", async () => {
      const inputWithoutStripeAccount = {
        surveyId: "survey-test-123",
        currency: "usd" as const,
        amount: 1000,
      };

      vi.mocked(getSurvey).mockResolvedValue(mockSurveyWithPayment as any);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const result = await createPaymentIntentAction({
        parsedInput: inputWithoutStripeAccount,
      } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(
        inputWithoutStripeAccount.amount,
        inputWithoutStripeAccount.currency,
        undefined,
        inputWithoutStripeAccount.surveyId
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
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const eurInput = { ...validInput, currency: "eur" as const };
      await createPaymentIntentAction({ parsedInput: eurInput } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(
        eurInput.amount,
        "eur",
        eurInput.stripeAccountId,
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
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const gbpInput = { ...validInput, currency: "gbp" as const };
      await createPaymentIntentAction({ parsedInput: gbpInput } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(
        gbpInput.amount,
        "gbp",
        gbpInput.stripeAccountId,
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

  describe("Error Handling", () => {
    test("should propagate errors from createPaymentIntent", async () => {
      vi.mocked(getSurvey).mockResolvedValue(mockSurveyWithPayment as any);
      vi.mocked(createPaymentIntent).mockRejectedValue(
        new Error("An unexpected error occurred while processing your payment. Please try again.")
      );

      await expect(createPaymentIntentAction({ parsedInput: validInput } as any)).rejects.toThrow(
        "An unexpected error occurred while processing your payment. Please try again."
      );
    });

    test("should propagate card declined errors from createPaymentIntent", async () => {
      vi.mocked(getSurvey).mockResolvedValue(mockSurveyWithPayment as any);
      vi.mocked(createPaymentIntent).mockRejectedValue(
        new Error("Payment failed: Your card was declined. Please try a different card.")
      );

      await expect(createPaymentIntentAction({ parsedInput: validInput } as any)).rejects.toThrow(
        "Payment failed: Your card was declined. Please try a different card."
      );
    });

    test("should propagate payment configuration errors from createPaymentIntent", async () => {
      vi.mocked(getSurvey).mockResolvedValue(mockSurveyWithPayment as any);
      vi.mocked(createPaymentIntent).mockRejectedValue(
        new Error("Payment configuration error. Please contact support.")
      );

      await expect(createPaymentIntentAction({ parsedInput: validInput } as any)).rejects.toThrow(
        "Payment configuration error. Please contact support."
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
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const minAmountInput = { ...validInput, amount: 1 };
      const result = await createPaymentIntentAction({
        parsedInput: minAmountInput,
      } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(
        1,
        "usd",
        validInput.stripeAccountId,
        validInput.surveyId
      );
      expect(result).toEqual(mockPaymentIntentResult);
    });

    test("should pass large amounts correctly", async () => {
      const largeAmountSurvey = {
        ...mockSurveyWithPayment,
        blocks: [
          { id: "block1", elements: [{ ...mockSurveyWithPayment.blocks[0].elements[0], amount: 99999999 }] },
        ],
      };
      vi.mocked(getSurvey).mockResolvedValue(largeAmountSurvey as any);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      const largeAmountInput = { ...validInput, amount: 99999999 };
      const result = await createPaymentIntentAction({
        parsedInput: largeAmountInput,
      } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(
        99999999,
        "usd",
        validInput.stripeAccountId,
        validInput.surveyId
      );
      expect(result).toEqual(mockPaymentIntentResult);
    });
  });

  describe("Exact Input Passing", () => {
    test("should call createPaymentIntent with exact parsed input values", async () => {
      const exactSurvey = {
        id: "clxxxxxxxxxxxxxxxxxxxxxxxxx",
        blocks: [
          {
            id: "block1",
            elements: [
              {
                id: "q1",
                type: TSurveyElementTypeEnum.Payment,
                amount: 2500,
                currency: "eur",
                stripeIntegration: { publicKey: "pk_test_123" },
              },
            ],
          },
        ],
      };
      vi.mocked(getSurvey).mockResolvedValue(exactSurvey as any);
      vi.mocked(createPaymentIntent).mockResolvedValue(mockPaymentIntentResult);

      await createPaymentIntentAction({
        parsedInput: {
          surveyId: "clxxxxxxxxxxxxxxxxxxxxxxxxx",
          currency: "eur",
          amount: 2500,
          stripeAccountId: "acct_connected_123",
        },
      } as any);

      expect(createPaymentIntent).toHaveBeenCalledWith(
        2500,
        "eur",
        "acct_connected_123",
        "clxxxxxxxxxxxxxxxxxxxxxxxxx"
      );
    });
  });
});
