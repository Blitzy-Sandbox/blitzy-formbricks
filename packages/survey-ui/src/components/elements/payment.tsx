import * as React from "react";
import { ElementError } from "@/components/general/element-error";
import { ElementHeader } from "@/components/general/element-header";
import { cn } from "@/lib/utils";

/**
 * Format a currency amount (in smallest unit) for display
 */
const formatCurrency = (amount: number, currency: string): string => {
  const symbols: Record<string, string> = {
    usd: "$",
    eur: "€",
    gbp: "£",
  };
  const symbol = symbols[currency] ?? currency.toUpperCase();
  return `${symbol}${(amount / 100).toFixed(2)}`;
};

interface PaymentElementProps {
  elementId: string;
  headline: string;
  description?: string;
  currency: string;
  amount: number;
  buttonLabel?: string;
  value?: string;
  onChange: (value: string) => void;
  dir?: "ltr" | "rtl" | "auto";
  required?: boolean;
  errorMessage?: string;
  languageCode: string;
}

export const PaymentElement = React.forwardRef<HTMLDivElement, PaymentElementProps>(
  (
    {
      elementId,
      headline,
      description,
      currency,
      amount,
      buttonLabel,
      value,
      onChange,
      dir = "ltr",
      required = false,
      errorMessage,
      languageCode,
    },
    ref
  ) => {
    const handlePaymentClick = () => {
      // In a real Stripe integration this would open the Stripe checkout.
      // For now we mark the payment as "completed" so the survey can proceed.
      onChange("completed");
    };

    return (
      <div ref={ref} dir={dir}>
        <ElementHeader headline={headline} description={description ?? ""} required={required} />
        <div className="fb-mt-4 fb-flex fb-flex-col fb-items-center fb-gap-3">
          <p className="fb-text-lg fb-font-semibold">{formatCurrency(amount, currency)}</p>
          <button
            type="button"
            className={cn(
              "fb-rounded-custom fb-bg-brand fb-px-6 fb-py-3 fb-text-on-brand fb-font-medium",
              "hover:fb-opacity-90 focus:fb-outline-none focus:fb-ring-2 focus:fb-ring-brand focus:fb-ring-offset-2",
              "disabled:fb-cursor-not-allowed disabled:fb-opacity-50"
            )}
            disabled={value === "completed"}
            onClick={handlePaymentClick}>
            {value === "completed" ? "✓ Paid" : buttonLabel || "Pay now"}
          </button>
        </div>
        {errorMessage && <ElementError errorMessage={errorMessage} />}
      </div>
    );
  }
);

PaymentElement.displayName = "PaymentElement";
