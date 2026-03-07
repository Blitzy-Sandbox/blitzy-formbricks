import * as React from "react";
import { Button } from "@/components/general/button";
import { ElementError } from "@/components/general/element-error";
import { ElementHeader } from "@/components/general/element-header";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Currency formatting utility
// ---------------------------------------------------------------------------

/** Currency symbol lookup keyed by ISO 4217 lowercase code */
const CURRENCY_SYMBOLS: Record<string, string> = {
  usd: "$",
  eur: "€",
  gbp: "£",
};

/**
 * Formats a payment amount from its smallest currency unit (cents / pence) to
 * a human-readable string with the appropriate currency symbol.
 *
 * @param amount   - Amount in the smallest currency unit (e.g. 1000 = $10.00)
 * @param currency - Three-letter currency code (`"usd"`, `"eur"`, or `"gbp"`)
 * @returns A formatted string such as `"$10.00"`, `"€25.50"`, or `"£7.99"`
 */
function formatPaymentAmount(amount: number, currency: "usd" | "eur" | "gbp"): string {
  const symbol = CURRENCY_SYMBOLS[currency] ?? "$";
  const formattedAmount = (amount / 100).toFixed(2);
  return `${symbol}${formattedAmount}`;
}

// ---------------------------------------------------------------------------
// Props interface
// ---------------------------------------------------------------------------

/**
 * Props for the Payment element component.
 *
 * This is a **presentational** component — it does **not** import Stripe.
 * The card-input UI (e.g. Stripe `<CardElement>`) is injected via the
 * `children` slot by the consuming renderer layer (`packages/surveys/`).
 */
interface PaymentProps {
  /** Unique identifier for the element container */
  elementId: string;
  /** The main element or prompt text displayed as the headline */
  headline: string;
  /** Optional descriptive text displayed below the headline */
  description?: string;
  /** Unique identifier for the payment input / submit button */
  inputId: string;
  /** Payment currency */
  currency: "usd" | "eur" | "gbp";
  /** Amount in the smallest currency unit (cents / pence) */
  amount: number;
  /** Label text for the submit button */
  buttonLabel: string;
  /** Callback invoked when the user submits the payment */
  onSubmit: () => void;
  /** Whether payment is currently being processed */
  isProcessing?: boolean;
  /** Whether payment completed successfully */
  isSuccess?: boolean;
  /** Error message to display (validation or payment failure) */
  errorMessage?: string;
  /** Whether the field is required (shows the required indicator) */
  required?: boolean;
  /** Custom label for the required indicator */
  requiredLabel?: string;
  /** Text direction */
  dir?: "ltr" | "rtl" | "auto";
  /** Whether the entire component is disabled */
  disabled?: boolean;
  /** Label displayed while payment is being processed (defaults to "Processing…") */
  processingLabel?: string;
  /** Label displayed when payment succeeds (defaults to "Payment Successful") */
  successLabel?: string;
  /** Image URL displayed above the headline */
  imageUrl?: string;
  /** Video URL displayed above the headline */
  videoUrl?: string;
  /**
   * Slot for the card-input element.
   * The renderer layer injects Stripe's `<CardElement>` (or equivalent) here
   * so that `packages/survey-ui` stays Stripe-independent.
   */
  children?: React.ReactNode;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * Presentational Payment element for the survey-ui design system.
 *
 * Renders an amount display, an optional card-input slot (`children`), and a
 * submit button with processing / success / error states. The Stripe
 * integration lives in the `packages/surveys/` renderer layer — this
 * component is intentionally Stripe-free.
 */
function Payment({
  elementId,
  headline,
  description,
  inputId,
  currency,
  amount,
  buttonLabel,
  onSubmit,
  isProcessing = false,
  isSuccess = false,
  errorMessage,
  required = false,
  requiredLabel,
  dir = "auto",
  disabled = false,
  processingLabel = "Processing\u2026",
  successLabel = "Payment Successful",
  imageUrl,
  videoUrl,
  children,
}: Readonly<PaymentProps>): React.JSX.Element {
  /** Guard against redundant submissions while processing or after success. */
  const handleSubmit = (): void => {
    if (disabled || isProcessing || isSuccess) return;
    onSubmit();
  };

  return (
    <div className="w-full space-y-4" id={elementId} dir={dir}>
      {/* Headline & description */}
      <ElementHeader
        headline={headline}
        description={description}
        required={required}
        requiredLabel={requiredLabel}
        htmlFor={inputId}
        imageUrl={imageUrl}
        videoUrl={videoUrl}
      />

      {/* Payment body */}
      <div className="relative space-y-4">
        <ElementError errorMessage={errorMessage} dir={dir} />

        {/* Formatted amount display */}
        <div className="text-center">
          <span className="text-2xl font-semibold">{formatPaymentAmount(amount, currency)}</span>
        </div>

        {/* Card-input slot (children) — e.g. Stripe <CardElement> */}
        {children ? (
          <div
            className={cn(
              "bg-input-bg border-input-border rounded-input border p-3",
              disabled && "pointer-events-none opacity-50"
            )}>
            {children}
          </div>
        ) : null}

        {/* Submit / processing / success button */}
        <div className="flex w-full justify-center">
          <Button
            id={inputId}
            type="button"
            onClick={handleSubmit}
            disabled={disabled || isProcessing || isSuccess}
            className={cn("w-full", isSuccess && "bg-emerald-500 hover:bg-emerald-500")}>
            {isProcessing ? (
              <>
                {/* Spinning loader */}
                <svg
                  className="h-5 w-5 animate-spin"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  aria-hidden="true">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                {processingLabel}
              </>
            ) : isSuccess ? (
              <>
                {/* Checkmark */}
                <svg
                  className="h-5 w-5"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth="2"
                  aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                {successLabel}
              </>
            ) : (
              buttonLabel
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export { Payment, formatPaymentAmount };
export type { PaymentProps };
