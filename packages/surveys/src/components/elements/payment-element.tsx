import { CardElement, Elements, useElements, useStripe } from "@stripe/react-stripe-js";
import { loadStripe } from "@stripe/stripe-js";
import { useMemo, useState } from "preact/hooks";
import { useTranslation } from "react-i18next";
import { Payment } from "@formbricks/survey-ui";
import { type TResponseData, type TResponseTtc } from "@formbricks/types/responses";
import type { TSurveyPaymentElement } from "@formbricks/types/surveys/elements";
import { getLocalizedValue } from "@/lib/i18n";
import { getUpdatedTtc, useTtc } from "@/lib/ttc";

// ---------------------------------------------------------------------------
// Props interfaces
// ---------------------------------------------------------------------------

interface PaymentElementProps {
  element: TSurveyPaymentElement;
  value: string;
  onChange: (responseData: TResponseData) => void;
  languageCode: string;
  ttc: TResponseTtc;
  setTtc: (ttc: TResponseTtc) => void;
  currentElementId: string;
  surveyId: string;
  dir?: "ltr" | "rtl" | "auto";
  errorMessage?: string;
}

interface PaymentFormProps {
  element: TSurveyPaymentElement;
  value: string;
  onChange: (responseData: TResponseData) => void;
  languageCode: string;
  surveyId: string;
  dir?: "ltr" | "rtl" | "auto";
  errorMessage?: string;
}

// ---------------------------------------------------------------------------
// Stripe CardElement styling options
// ---------------------------------------------------------------------------

/** Consistent styling for the Stripe CardElement matching the survey design system. */
const CARD_ELEMENT_OPTIONS = {
  style: {
    base: {
      fontSize: "16px",
      color: "#374151",
      "::placeholder": {
        color: "#9CA3AF",
      },
    },
    invalid: {
      color: "#EF4444",
    },
  },
};

// ---------------------------------------------------------------------------
// Helper: Create a PaymentIntent via the Formbricks client API
// ---------------------------------------------------------------------------

/**
 * Calls the Formbricks payment intent API endpoint to create a Stripe PaymentIntent.
 *
 * This uses the client API route (`/api/v1/client/payment-intent`) which is
 * unauthenticated — supporting both logged-in users and anonymous respondents
 * on public link surveys.
 *
 * @param surveyId - The survey ID containing the Payment element
 * @param amount - Positive integer in smallest currency unit (cents/pence)
 * @param currency - ISO 4217 lowercase currency code ("usd" | "eur" | "gbp")
 * @returns The clientSecret for client-side payment confirmation
 * @throws Error if the API call fails
 */
async function fetchPaymentIntent(surveyId: string, amount: number, currency: string): Promise<string> {
  // Use relative URL — works for link surveys on the same domain.
  // For embedded surveys, the Formbricks script is loaded from the app domain,
  // and the fetch will be made relative to that domain's origin.
  const response = await fetch("/api/v1/client/payment-intent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ surveyId, amount, currency }),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => null);
    const message =
      (errorData as { message?: string } | null)?.message ??
      "Failed to initialize payment. Please try again.";
    throw new Error(message);
  }

  const json = (await response.json()) as { data: { clientSecret: string } };
  if (!json.data?.clientSecret) {
    throw new Error("Invalid response from payment server");
  }

  return json.data.clientSecret;
}

// ---------------------------------------------------------------------------
// Inner component — PaymentForm (uses Stripe hooks)
// ---------------------------------------------------------------------------

/**
 * Inner form component that accesses Stripe hooks (`useStripe`, `useElements`).
 * Must be rendered inside an `<Elements>` provider.
 *
 * Payment flow (Issue 1 fix — Refine PR):
 * 1. Call the Formbricks API to create a Stripe PaymentIntent → get clientSecret
 * 2. Call stripe.confirmCardPayment(clientSecret, { payment_method: { card } })
 * 3. Only call onChange({ [element.id]: "paid" }) on successful payment confirmation
 *
 * This ensures the card is actually charged, not just tokenised.
 */
function PaymentForm({
  element,
  value,
  onChange,
  languageCode,
  surveyId,
  dir = "auto",
  errorMessage,
}: Readonly<PaymentFormProps>) {
  const stripe = useStripe();
  const elements = useElements();
  const { t } = useTranslation();

  // Payment state machine: idle → processing → success | error
  // Initialise from value prop so back-navigation restores the completed state
  const [paymentState, setPaymentState] = useState<"idle" | "processing" | "success" | "error">(
    value === "paid" ? "success" : "idle"
  );
  const [paymentError, setPaymentError] = useState<string | null>(null);

  /**
   * Maps a Stripe error code to a user-friendly localised error message.
   * Covers all common card error scenarios per AAP §0.7.3.
   */
  const getStripeErrorMessage = (code: string | undefined, fallbackMessage: string | undefined): string => {
    switch (code) {
      case "card_declined":
        return t("survey.payment.card_declined", "Your card was declined. Please try a different card.");
      case "insufficient_funds":
        return t("survey.payment.insufficient_funds", "Insufficient funds. Please try a different card.");
      case "expired_card":
        return t("survey.payment.expired_card", "Your card has expired. Please try a different card.");
      case "incorrect_number":
        return t(
          "survey.payment.incorrect_number",
          "Your card number is incorrect. Please check and try again."
        );
      case "incomplete_number":
      case "incomplete_expiry":
      case "incomplete_cvc":
        return t("survey.payment.incomplete_card", "Please complete all card fields.");
      default:
        return fallbackMessage ?? t("survey.payment.generic_error", "Payment failed. Please try again.");
    }
  };

  /**
   * Handles the full payment submission flow:
   * 1. Create a PaymentIntent via the Formbricks API (server creates it with Stripe)
   * 2. Confirm the payment client-side using stripe.confirmCardPayment()
   * 3. Mark the response as "paid" only on successful confirmation
   */
  const handleSubmit = async (): Promise<void> => {
    // Guard: Stripe must be fully initialised before we can proceed
    if (!stripe || !elements) return;

    setPaymentState("processing");
    setPaymentError(null);

    const cardElement = elements.getElement(CardElement);
    if (!cardElement) {
      setPaymentState("error");
      setPaymentError(t("survey.payment.generic_error", "Payment failed. Please try again."));
      return;
    }

    try {
      // Step 1: Create a PaymentIntent via the Formbricks API
      // The server validates the survey exists and has a matching Payment element,
      // then calls Stripe to create the PaymentIntent.
      const clientSecret = await fetchPaymentIntent(surveyId, element.amount, element.currency);

      // Step 2: Confirm the payment client-side using the card details
      // This actually charges the card via Stripe's PCI-compliant flow.
      const { error: confirmError, paymentIntent } = await stripe.confirmCardPayment(clientSecret, {
        payment_method: {
          card: cardElement,
        },
      });

      if (confirmError) {
        setPaymentState("error");
        setPaymentError(getStripeErrorMessage(confirmError.code, confirmError.message));
        return;
      }

      // Step 3: Only mark as paid on successful confirmation
      if (paymentIntent && paymentIntent.status === "succeeded") {
        setPaymentState("success");
        onChange({ [element.id]: "paid" });
      } else {
        // Payment requires additional action or is still processing
        setPaymentState("error");
        setPaymentError(
          t("survey.payment.processing", "Payment is still processing. Please wait or try again.")
        );
      }
    } catch (err: unknown) {
      setPaymentState("error");
      const message =
        err instanceof Error
          ? err.message
          : t("survey.payment.generic_error", "Payment failed. Please try again.");
      setPaymentError(message);
    }
  };

  // Resolve localised labels with fallbacks
  const headline = getLocalizedValue(element.headline, languageCode);
  const description = element.subheader ? getLocalizedValue(element.subheader, languageCode) : undefined;
  const buttonLabel = getLocalizedValue(element.buttonLabel, languageCode) || t("survey.payment.pay", "Pay");

  // Stripe CardElement renders inside the Payment component's children slot.
  // All card data is handled exclusively by Stripe — PCI compliance is maintained.
  // Cast Preact VNode to satisfy React.ReactNode expected by the Payment/Elements children props.
  // At runtime preact/compat aliases React, so the VNode is fully compatible.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const cardInputSlot = (<CardElement options={CARD_ELEMENT_OPTIONS} />) as any;

  return (
    <Payment
      elementId={element.id}
      inputId={element.id}
      headline={headline}
      description={description}
      currency={element.currency}
      amount={element.amount}
      buttonLabel={buttonLabel}
      onSubmit={handleSubmit}
      isProcessing={paymentState === "processing"}
      isSuccess={paymentState === "success"}
      errorMessage={paymentError ?? errorMessage}
      required={element.required}
      requiredLabel={t("common.required")}
      dir={dir}
      imageUrl={element.imageUrl}
      videoUrl={element.videoUrl}>
      {cardInputSlot}
    </Payment>
  );
}

// ---------------------------------------------------------------------------
// Outer component — PaymentElement (exported)
// ---------------------------------------------------------------------------

/**
 * Preact respondent-facing Payment element that wraps the presentational `Payment`
 * UI primitive from `@formbricks/survey-ui` with:
 *
 * - **Stripe Elements integration** — `<Elements>` provider initialised with the
 *   element's publishable key for PCI-compliant card input
 * - **TTC tracking** — Time-to-completion tracking identical to other survey elements
 *   (rating, consent, CTA) using `useTtc` and `getUpdatedTtc`
 * - **Localisation** — All user-facing labels resolved via `getLocalizedValue`
 * - **Full payment flow** — Creates a PaymentIntent server-side, then confirms the
 *   payment client-side using stripe.confirmCardPayment() (Refine PR Issue 1 fix)
 *
 * Architecture note: Two components are required because the Stripe hooks
 * (`useStripe`, `useElements`) can only be called inside an `<Elements>` provider.
 * The outer component provides the Stripe context; the inner `PaymentForm`
 * accesses it through hooks.
 */
export function PaymentElement({
  element,
  value,
  onChange,
  languageCode,
  ttc,
  setTtc,
  currentElementId,
  surveyId,
  dir = "auto",
  errorMessage,
}: Readonly<PaymentElementProps>) {
  const [startTime, setStartTime] = useState(performance.now());
  const isCurrent = element.id === currentElementId;

  // TTC tracking — identical to rating-element.tsx, consent-element.tsx patterns
  useTtc(element.id, ttc, setTtc, startTime, setStartTime, isCurrent);

  // Initialise Stripe with the element's publishable key (never the secret key).
  // Memoised to prevent recreating the Stripe object on every render, which would
  // cause the <Elements> provider to remount and reset the CardElement input.
  const stripePromise = useMemo(
    () => loadStripe(element.stripeIntegration.publicKey),
    [element.stripeIntegration.publicKey]
  );

  /**
   * Form-level submit handler for TTC collection.
   * The actual payment submission is handled by the inner PaymentForm component.
   */
  const handleSubmit = (e: Event): void => {
    e.preventDefault();
    const updatedTtcObj = getUpdatedTtc(ttc, element.id, performance.now() - startTime);
    setTtc(updatedTtcObj);
  };

  // Cast Preact VNode to satisfy React.ReactNode expected by the Elements children prop.
  // At runtime preact/compat aliases React, so the VNode is fully compatible.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const paymentFormNode = (
    <PaymentForm
      element={element}
      value={value}
      onChange={onChange}
      languageCode={languageCode}
      surveyId={surveyId}
      dir={dir}
      errorMessage={errorMessage}
    />
  ) as any;

  return (
    <form key={element.id} onSubmit={handleSubmit} className="w-full">
      <Elements stripe={stripePromise}>{paymentFormNode}</Elements>
    </form>
  );
}
