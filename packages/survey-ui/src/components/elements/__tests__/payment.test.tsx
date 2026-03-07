// @vitest-environment happy-dom
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { Payment, formatPaymentAmount } from "../payment";

// ---------------------------------------------------------------------------
// Shared default props — `onSubmit` is cleared before every component test
// ---------------------------------------------------------------------------

const defaultProps = {
  elementId: "test-payment",
  headline: "Complete your payment",
  inputId: "test-payment-input",
  currency: "usd" as const,
  amount: 1000,
  buttonLabel: "Pay $10.00",
  onSubmit: vi.fn(),
};

// ===========================================================================
// formatPaymentAmount — pure function tests (no DOM rendering needed)
// ===========================================================================

describe("formatPaymentAmount", () => {
  test("formats USD amount correctly", () => {
    expect(formatPaymentAmount(1000, "usd")).toBe("$10.00");
  });

  test("formats EUR amount correctly", () => {
    expect(formatPaymentAmount(2500, "eur")).toBe("€25.00");
  });

  test("formats GBP amount correctly", () => {
    expect(formatPaymentAmount(1500, "gbp")).toBe("£15.00");
  });

  test("formats zero amount", () => {
    expect(formatPaymentAmount(0, "usd")).toBe("$0.00");
  });

  test("formats small amounts correctly", () => {
    expect(formatPaymentAmount(1, "usd")).toBe("$0.01");
  });

  test("formats large amounts correctly", () => {
    expect(formatPaymentAmount(100000, "usd")).toBe("$1000.00");
  });

  test("always shows two decimal places", () => {
    expect(formatPaymentAmount(500, "eur")).toBe("€5.00");
  });
});

// ===========================================================================
// Payment component tests
// ===========================================================================

describe("Payment", () => {
  beforeEach(() => {
    defaultProps.onSubmit.mockClear();
  });

  // -------------------------------------------------------------------------
  // Basic rendering
  // -------------------------------------------------------------------------

  test("renders headline text", () => {
    render(<Payment {...defaultProps} />);
    expect(screen.getByText("Complete your payment")).toBeInTheDocument();
  });

  test("renders description when provided", () => {
    render(<Payment {...defaultProps} description="Enter your card details" />);
    expect(screen.getByText("Enter your card details")).toBeInTheDocument();
  });

  test("renders formatted amount display", () => {
    render(<Payment {...defaultProps} amount={1000} currency="usd" />);
    expect(screen.getByText("$10.00")).toBeInTheDocument();
  });

  test("renders button with label", () => {
    render(<Payment {...defaultProps} buttonLabel="Pay $10.00" />);
    const button = screen.getByRole("button");
    expect(button).toHaveTextContent("Pay $10.00");
  });

  // -------------------------------------------------------------------------
  // Amount formatting (in component context)
  // -------------------------------------------------------------------------

  test("displays USD amount with dollar sign", () => {
    render(<Payment {...defaultProps} currency="usd" amount={2000} />);
    expect(screen.getByText("$20.00")).toBeInTheDocument();
  });

  test("displays EUR amount with euro sign", () => {
    render(<Payment {...defaultProps} currency="eur" amount={2500} />);
    expect(screen.getByText("€25.00")).toBeInTheDocument();
  });

  test("displays GBP amount with pound sign", () => {
    render(<Payment {...defaultProps} currency="gbp" amount={1500} />);
    expect(screen.getByText("£15.00")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Button label
  // -------------------------------------------------------------------------

  test("renders custom button label", () => {
    render(<Payment {...defaultProps} buttonLabel="Submit Payment" />);
    const button = screen.getByRole("button");
    expect(button).toHaveTextContent("Submit Payment");
  });

  test("button is clickable by default", () => {
    render(<Payment {...defaultProps} />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    expect(defaultProps.onSubmit).toHaveBeenCalledTimes(1);
  });

  // -------------------------------------------------------------------------
  // Processing state
  // -------------------------------------------------------------------------

  test("shows processing state", () => {
    render(<Payment {...defaultProps} isProcessing={true} />);
    // The default processingLabel uses the unicode ellipsis character U+2026
    expect(screen.getByText("Processing\u2026")).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  test("does not call onSubmit when processing", () => {
    render(<Payment {...defaultProps} isProcessing={true} />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    expect(defaultProps.onSubmit).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Success state
  // -------------------------------------------------------------------------

  test("shows success state", () => {
    render(<Payment {...defaultProps} isSuccess={true} />);
    expect(screen.getByText("Payment Successful")).toBeInTheDocument();
    expect(screen.getByRole("button")).toBeDisabled();
  });

  test("does not call onSubmit when in success state", () => {
    render(<Payment {...defaultProps} isSuccess={true} />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    expect(defaultProps.onSubmit).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Error message
  // -------------------------------------------------------------------------

  test("renders error message when provided", () => {
    render(<Payment {...defaultProps} errorMessage="Your card was declined" />);
    expect(screen.getByText("Your card was declined")).toBeInTheDocument();
  });

  test("does not render error when no error message", () => {
    render(<Payment {...defaultProps} />);
    expect(screen.queryByText("Your card was declined")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // Disabled state
  // -------------------------------------------------------------------------

  test("does not call onSubmit when disabled", () => {
    render(<Payment {...defaultProps} disabled={true} />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    expect(defaultProps.onSubmit).not.toHaveBeenCalled();
  });

  test("button is disabled when disabled prop is true", () => {
    render(<Payment {...defaultProps} disabled={true} />);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  // -------------------------------------------------------------------------
  // Children slot (card input injection)
  // -------------------------------------------------------------------------

  test("renders children in card input slot", () => {
    render(
      <Payment {...defaultProps}>
        <div data-testid="mock-card-input">Mock Card Input</div>
      </Payment>
    );
    expect(screen.getByTestId("mock-card-input")).toBeInTheDocument();
  });

  test("renders without children when no children provided", () => {
    render(<Payment {...defaultProps} />);
    expect(screen.queryByTestId("mock-card-input")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // onSubmit callback
  // -------------------------------------------------------------------------

  test("calls onSubmit when button is clicked", () => {
    const onSubmit = vi.fn();
    render(<Payment {...defaultProps} onSubmit={onSubmit} />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  test("calls onSubmit only once per click", () => {
    render(<Payment {...defaultProps} />);
    const button = screen.getByRole("button");
    fireEvent.click(button);
    expect(defaultProps.onSubmit).toHaveBeenCalledTimes(1);
  });

  // -------------------------------------------------------------------------
  // RTL support
  // -------------------------------------------------------------------------

  test("applies RTL direction when dir is rtl", () => {
    const { container } = render(<Payment {...defaultProps} dir="rtl" />);
    const rootDiv = container.firstChild as HTMLElement;
    expect(rootDiv).toHaveAttribute("dir", "rtl");
  });

  // -------------------------------------------------------------------------
  // Required indicator
  // -------------------------------------------------------------------------

  test("shows required indicator when required is true", () => {
    render(<Payment {...defaultProps} required={true} />);
    // ElementHeader renders the default requiredLabel "Required" when required is true
    expect(screen.getByText("Required")).toBeInTheDocument();
  });
});
