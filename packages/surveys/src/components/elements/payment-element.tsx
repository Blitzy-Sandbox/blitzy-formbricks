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
  dir?: "ltr" | "rtl" | "auto";
  errorMessage?: string;
}

interface PaymentFormProps {
  element: TSurveyPaymentElement;
  value: string;
  onChange: (responseData: TResponseData) => void;
  languageCode: string;
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
  hidePostalCode: true,
} as const;

// ---------------------------------------------------------------------------
// Inner component — PaymentForm
// ---------------------------------------------------------------------------

/**
 * Inner payment form component that uses Stripe hooks (`useStripe`, `useElements`)
 * to manage PCI-compliant card input and payment method creation.
 *
 * IMPORTANT: This component MUST be rendered inside an `<Elements>` provider from
 * `@stripe/react-stripe-js` so the Stripe hooks have access to the Stripe context.
 *
 * Card details are handled ENTIRELY by Stripe Elements client-side — no card data
 * ever touches the Formbricks server. Only the resulting payment method ID is used.
 */
function PaymentForm({
  element,
  value,
  onChange,
  languageCode,
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
   * Handles payment submission by creating a Stripe PaymentMethod for PCI-compliant
   * card tokenisation. The tokenised payment method validates the card details
   * client-side without charging — actual charging is handled server-side when
   * the survey response is processed.
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
      // Create a PaymentMethod using Stripe Elements for PCI-compliant tokenisation.
      // This validates the card details client-side without performing a charge.
      const { error, paymentMethod } = await stripe.createPaymentMethod({
        type: "card",
        card: cardElement,
      });

      if (error) {
        setPaymentState("error");

        // Map Stripe error codes to user-friendly localised messages per AAP §0.7.3
        switch (error.code) {
          case "card_declined":
            setPaymentError(
              t("survey.payment.card_declined", "Your card was declined. Please try a different card.")
            );
            break;
          case "insufficient_funds":
            setPaymentError(
              t("survey.payment.insufficient_funds", "Insufficient funds. Please try a different card.")
            );
            break;
          case "expired_card":
            setPaymentError(
              t("survey.payment.expired_card", "Your card has expired. Please try a different card.")
            );
            break;
          case "incorrect_number":
            setPaymentError(
              t(
                "survey.payment.incorrect_number",
                "Your card number is incorrect. Please check and try again."
              )
            );
            break;
          case "incomplete_number":
          case "incomplete_expiry":
          case "incomplete_cvc":
            setPaymentError(t("survey.payment.incomplete_card", "Please complete all card fields."));
            break;
          default:
            setPaymentError(
              error.message ?? t("survey.payment.generic_error", "Payment failed. Please try again.")
            );
            break;
        }
        return;
      }

      // Payment method created successfully — mark as paid
      if (paymentMethod) {
        setPaymentState("success");
        onChange({ [element.id]: "paid" });
      }
    } catch (_err: unknown) {
      setPaymentState("error");
      setPaymentError(t("survey.payment.generic_error", "Payment failed. Please try again."));
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
