import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import type { TResponseTtc } from "@formbricks/types/responses";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/elements";
import type { TSurveyPaymentElement } from "@formbricks/types/surveys/elements";
import { PaymentElement } from "../payment-element";

// ---------------------------------------------------------------------------
// Mock Stripe instance — shared between loadStripe and useStripe mocks.
// The real component uses `stripe.createPaymentMethod()` for PCI-compliant
// card tokenisation, so the mock must expose `createPaymentMethod`.
// ---------------------------------------------------------------------------

const mockStripeInstance = {
  createPaymentMethod: vi.fn(),
  elements: vi.fn(),
};

// Mock @stripe/stripe-js — `loadStripe` is async and returns Promise<Stripe>
vi.mock("@stripe/stripe-js", () => ({
  loadStripe: vi.fn(() => Promise.resolve(mockStripeInstance)),
}));

// ---------------------------------------------------------------------------
// Mock @stripe/react-stripe-js — Elements provider, CardElement, and hooks
// ---------------------------------------------------------------------------

const mockUseStripe = vi.fn(() => mockStripeInstance);
const mockUseElements = vi.fn(() => ({
  getElement: vi.fn(() => ({})),
}));

vi.mock("@stripe/react-stripe-js", () => ({
  Elements: vi.fn(({ children }: { children: any }) => <div data-testid="stripe-elements">{children}</div>),
  CardElement: vi.fn(() => <div data-testid="stripe-card-element" />),
  useStripe: () => mockUseStripe(),
  useElements: () => mockUseElements(),
}));

// ---------------------------------------------------------------------------
// Mock @formbricks/survey-ui Payment component — renders all key props as
// testable DOM elements, wires onSubmit to a button click, and conditionally
// renders processing / success / error indicators.
// ---------------------------------------------------------------------------

vi.mock("@formbricks/survey-ui", () => ({
  Payment: vi.fn(
    ({
      elementId,
      headline,
      currency,
      amount,
      buttonLabel,
      onSubmit,
      isProcessing,
      isSuccess,
      errorMessage,
      children,
    }: any) => {
      return (
        <div data-testid={`payment-${elementId}`}>
          <span data-testid="headline">{headline}</span>
          <span data-testid="currency">{currency}</span>
          <span data-testid="amount">{amount}</span>
          <span data-testid="button-label">{buttonLabel}</span>
          {isProcessing && <span data-testid="processing-state">Processing</span>}
          {isSuccess && <span data-testid="success-state">Success</span>}
          {errorMessage && <span data-testid="error-message">{errorMessage}</span>}
          {children}
          <button data-testid="pay-button" onClick={onSubmit} disabled={isProcessing}>
            {buttonLabel}
          </button>
        </div>
      );
    }
  ),
}));

// ---------------------------------------------------------------------------
// Mock TTC tracking utilities
// ---------------------------------------------------------------------------

const mockGetUpdatedTtc = vi.fn((...args: unknown[]) => {
  const [ttc, id, time] = args as [Record<string, number>, string, number];
  return { ...ttc, [id]: (ttc[id] || 0) + time };
});
const mockUseTtc = vi.fn();

vi.mock("@/lib/ttc", () => ({
  getUpdatedTtc: mockGetUpdatedTtc,
  useTtc: mockUseTtc,
}));

// ---------------------------------------------------------------------------
// Mock i18n — getLocalizedValue resolves i18n objects to plain strings
// ---------------------------------------------------------------------------

vi.mock("@/lib/i18n", () => ({
  getLocalizedValue: vi.fn((localizedString: Record<string, string> | undefined, languageCode: string) => {
    if (!localizedString) return undefined;
    return localizedString[languageCode] || localizedString["default"] || "";
  }),
}));

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

/**
 * Creates a mock TSurveyPaymentElement-like object for use in tests.
 *
 * - Uses `TSurveyElementTypeEnum.Payment` for proper type compatibility
 * - `amount: 1000` represents $10.00 in smallest currency unit (cents)
 * - `stripeIntegration.publicKey` is a PUBLISHABLE key (PCI compliance — never secret key)
 */
function createMockPaymentElement(overrides: Partial<TSurveyPaymentElement> = {}): TSurveyPaymentElement {
  return {
    id: "pay1",
    type: TSurveyElementTypeEnum.Payment,
    headline: { default: "Complete your payment" },
    subheader: { default: "Enter your card details" },
    required: true,
    currency: "usd",
    amount: 1000,
    buttonLabel: { default: "Pay now" },
    stripeIntegration: {
      publicKey: "pk_test_abc123",
      priceId: "price_abc123",
    },
    imageUrl: undefined,
    videoUrl: undefined,
    ...overrides,
  } as TSurveyPaymentElement;
}

// ---------------------------------------------------------------------------
// Test suites
// ---------------------------------------------------------------------------

describe("PaymentElement", () => {
  const defaultProps = {
    element: createMockPaymentElement(),
    value: "" as string,
    onChange: vi.fn(),
    languageCode: "default",
    ttc: {} as TResponseTtc,
    setTtc: vi.fn(),
    currentElementId: "pay1",
    dir: "auto" as const,
    errorMessage: undefined as string | undefined,
  };

  beforeEach(() => {
    // Ensure deterministic TTC calculations across tests
    vi.spyOn(performance, "now").mockReturnValue(1000);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  // -----------------------------------------------------------------------
  // Suite 1: Basic Rendering
  // -----------------------------------------------------------------------

  test("renders payment component", () => {
    render(<PaymentElement {...defaultProps} />);
    expect(screen.getByTestId("payment-pay1")).toBeTruthy();
  });

  test("renders headline correctly", () => {
    render(<PaymentElement {...defaultProps} />);
    expect(screen.getByTestId("headline").textContent).toBe("Complete your payment");
  });

  test("renders currency and amount", () => {
    render(<PaymentElement {...defaultProps} />);
    expect(screen.getByTestId("currency").textContent).toBe("usd");
    expect(screen.getByTestId("amount").textContent).toBe("1000");
  });

  test("renders button label", () => {
    render(<PaymentElement {...defaultProps} />);
    expect(screen.getByTestId("button-label").textContent).toBe("Pay now");
  });

  test("renders Stripe Elements provider", () => {
    render(<PaymentElement {...defaultProps} />);
    expect(screen.getByTestId("stripe-elements")).toBeTruthy();
  });

  test("renders Stripe CardElement", () => {
    render(<PaymentElement {...defaultProps} />);
    expect(screen.getByTestId("stripe-card-element")).toBeTruthy();
  });

  // -----------------------------------------------------------------------
  // Suite 2: Stripe Initialization
  // -----------------------------------------------------------------------

  describe("Stripe initialization", () => {
    test("loadStripe is called with publishable key from element config", async () => {
      const { loadStripe } = await import("@stripe/stripe-js");
      render(<PaymentElement {...defaultProps} />);
      expect(loadStripe).toHaveBeenCalledWith("pk_test_abc123");
    });

    test("loadStripe is called with different publishable key", async () => {
      const { loadStripe } = await import("@stripe/stripe-js");
      const element = createMockPaymentElement({
        stripeIntegration: { publicKey: "pk_test_different", priceId: "price_xyz" },
      });
      render(<PaymentElement {...defaultProps} element={element} />);
      expect(loadStripe).toHaveBeenCalledWith("pk_test_different");
    });
  });

  // -----------------------------------------------------------------------
  // Suite 3: Payment State Management
  // -----------------------------------------------------------------------

  describe("payment states", () => {
    test("renders in idle state initially (no processing or success indicators)", () => {
      render(<PaymentElement {...defaultProps} />);
      expect(screen.queryByTestId("processing-state")).toBeNull();
      expect(screen.queryByTestId("success-state")).toBeNull();
    });

    test("calls onChange with paid status on successful payment", async () => {
      mockStripeInstance.createPaymentMethod.mockResolvedValueOnce({
        error: null,
        paymentMethod: { id: "pm_test_123", type: "card" },
      });

      const onChange = vi.fn();
      render(<PaymentElement {...defaultProps} onChange={onChange} />);

      fireEvent.click(screen.getByTestId("pay-button"));

      await waitFor(() => {
        expect(onChange).toHaveBeenCalledWith({ pay1: "paid" });
      });
    });

    test("shows success state after successful payment", async () => {
      mockStripeInstance.createPaymentMethod.mockResolvedValueOnce({
        error: null,
        paymentMethod: { id: "pm_test_456", type: "card" },
      });

      render(<PaymentElement {...defaultProps} />);
      fireEvent.click(screen.getByTestId("pay-button"));

      await waitFor(() => {
        expect(screen.getByTestId("success-state")).toBeTruthy();
      });
    });

    test("initializes in success state when value is 'paid' (back-navigation)", () => {
      render(<PaymentElement {...defaultProps} value="paid" />);
      expect(screen.getByTestId("success-state")).toBeTruthy();
    });
  });

  // -----------------------------------------------------------------------
  // Suite 4: Error Handling (per AAP §0.7.3)
  // -----------------------------------------------------------------------

  describe("error handling", () => {
    test("handles card_declined error with user-friendly message", async () => {
      mockStripeInstance.createPaymentMethod.mockResolvedValueOnce({
        error: { code: "card_declined", message: "Your card was declined." },
      });

      render(<PaymentElement {...defaultProps} />);
      fireEvent.click(screen.getByTestId("pay-button"));

      await waitFor(() => {
        const errorEl = screen.getByTestId("error-message");
        expect(errorEl).toBeTruthy();
      });
    });

    test("handles insufficient_funds error", async () => {
      mockStripeInstance.createPaymentMethod.mockResolvedValueOnce({
        error: { code: "insufficient_funds", message: "Insufficient funds." },
      });

      render(<PaymentElement {...defaultProps} />);
      fireEvent.click(screen.getByTestId("pay-button"));

      await waitFor(() => {
        const errorEl = screen.getByTestId("error-message");
        expect(errorEl).toBeTruthy();
      });
    });

    test("handles expired_card error", async () => {
      mockStripeInstance.createPaymentMethod.mockResolvedValueOnce({
        error: { code: "expired_card", message: "Your card has expired." },
      });

      render(<PaymentElement {...defaultProps} />);
      fireEvent.click(screen.getByTestId("pay-button"));

      await waitFor(() => {
        const errorEl = screen.getByTestId("error-message");
        expect(errorEl).toBeTruthy();
      });
    });

    test("handles generic/unknown error", async () => {
      mockStripeInstance.createPaymentMethod.mockResolvedValueOnce({
        error: { code: "processing_error", message: "An error occurred." },
      });

      render(<PaymentElement {...defaultProps} />);
      fireEvent.click(screen.getByTestId("pay-button"));

      await waitFor(() => {
        const errorEl = screen.getByTestId("error-message");
        expect(errorEl).toBeTruthy();
      });
    });

    test("handles createPaymentMethod promise rejection", async () => {
      mockStripeInstance.createPaymentMethod.mockRejectedValueOnce(new Error("Network error"));

      render(<PaymentElement {...defaultProps} />);
      fireEvent.click(screen.getByTestId("pay-button"));

      await waitFor(() => {
        const errorEl = screen.getByTestId("error-message");
        expect(errorEl).toBeTruthy();
      });
    });

    test("does not expose Stripe API internals in error messages", async () => {
      mockStripeInstance.createPaymentMethod.mockResolvedValueOnce({
        error: {
          code: "card_declined",
          message: "Your card was declined.",
          decline_code: "stolen_card",
          charge: "ch_xxx",
        },
      });

      render(<PaymentElement {...defaultProps} />);
      fireEvent.click(screen.getByTestId("pay-button"));

      await waitFor(() => {
        const errorEl = screen.getByTestId("error-message");
        expect(errorEl.textContent).not.toContain("ch_xxx");
        expect(errorEl.textContent).not.toContain("stolen_card");
      });
    });
  });

  // -----------------------------------------------------------------------
  // Suite 5: TTC Tracking
  // -----------------------------------------------------------------------

  describe("TTC tracking", () => {
    test("useTtc hook is called with element id", () => {
      render(<PaymentElement {...defaultProps} />);
      expect(mockUseTtc).toHaveBeenCalled();
      expect(mockUseTtc.mock.calls[0][0]).toBe("pay1");
    });

    test("setTtc is called on form submission", () => {
      const setTtc = vi.fn();
      const { container } = render(<PaymentElement {...defaultProps} setTtc={setTtc} />);
      const form = container.querySelector("form");
      fireEvent.submit(form!);
      expect(mockGetUpdatedTtc).toHaveBeenCalled();
      expect(setTtc).toHaveBeenCalled();
    });

    test("getUpdatedTtc receives correct element id on form submit", () => {
      const { container } = render(<PaymentElement {...defaultProps} />);
      const form = container.querySelector("form");
      fireEvent.submit(form!);
      expect(mockGetUpdatedTtc.mock.calls[0][1]).toBe("pay1");
    });
  });

  // -----------------------------------------------------------------------
  // Suite 6: Form Submission
  // -----------------------------------------------------------------------

  describe("form submission", () => {
    test("prevents default form submission", () => {
      const { container } = render(<PaymentElement {...defaultProps} />);
      const form = container.querySelector("form");
      expect(form).toBeTruthy();
      const submitEvent = new Event("submit", { bubbles: true, cancelable: true });
      const preventDefault = vi.spyOn(submitEvent, "preventDefault");
      form?.dispatchEvent(submitEvent);
      expect(preventDefault).toHaveBeenCalled();
    });
  });

  // -----------------------------------------------------------------------
  // Suite 7: Prop Variations — currency, amount, element ID, error message
  // -----------------------------------------------------------------------

  describe("prop variations", () => {
    test("renders with EUR currency", () => {
      const element = createMockPaymentElement({ currency: "eur" });
      render(<PaymentElement {...defaultProps} element={element} />);
      expect(screen.getByTestId("currency").textContent).toBe("eur");
    });

    test("renders with GBP currency", () => {
      const element = createMockPaymentElement({ currency: "gbp" });
      render(<PaymentElement {...defaultProps} element={element} />);
      expect(screen.getByTestId("currency").textContent).toBe("gbp");
    });

    test("renders with different amount", () => {
      const element = createMockPaymentElement({ amount: 5000 });
      render(<PaymentElement {...defaultProps} element={element} />);
      expect(screen.getByTestId("amount").textContent).toBe("5000");
    });

    test("renders with different element ID", () => {
      const element = createMockPaymentElement({ id: "custom-pay" });
      render(<PaymentElement {...defaultProps} element={element} currentElementId="custom-pay" />);
      expect(screen.getByTestId("payment-custom-pay")).toBeTruthy();
    });

    test("renders with external error message", () => {
      render(<PaymentElement {...defaultProps} errorMessage="Validation error" />);
      expect(screen.getByTestId("error-message").textContent).toBe("Validation error");
    });
  });
});
