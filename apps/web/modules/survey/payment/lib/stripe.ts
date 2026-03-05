import Stripe from "stripe";
import { logger } from "@formbricks/logger";
import { STRIPE_API_VERSION } from "@/lib/constants";
import { env } from "@/lib/env";

// Module-level Stripe client for survey payment operations.
// This is SEPARATE from the billing module (apps/web/modules/ee/billing/).
// The billing module handles platform subscription management.
// This module handles per-survey payment collection via connected Stripe accounts.
const stripe = new Stripe(env.STRIPE_SECRET_KEY!, {
  apiVersion: STRIPE_API_VERSION,
});

/**
 * Creates a Stripe Payment Intent for client-side card collection in a survey Payment element.
 *
 * The returned `clientSecret` is passed to the client where `@stripe/react-stripe-js`
 * `<CardElement>` uses it for PCI-compliant card tokenization. Card details never touch
 * the Formbricks server.
 *
 * @param amount - Positive integer in the smallest currency unit (e.g. cents for USD/EUR, pence for GBP).
 *                 Already validated upstream by the Zod schema as `z.number().int().positive().min(1)`.
 * @param currency - ISO 4217 lowercase currency code. One of "usd", "eur", "gbp".
 *                   Already validated upstream by the Zod schema as `z.enum(["usd", "eur", "gbp"])`.
 * @param stripeAccountId - Optional connected Stripe account ID for multi-tenant payment routing.
 *                          When provided, the PaymentIntent is created on the connected account
 *                          via the `stripe_account` header (Stripe Connect pattern).
 * @returns An object containing the `clientSecret` required for client-side payment confirmation.
 * @throws Error with a user-friendly message if the Stripe API call fails.
 */
export const createPaymentIntent = async (
  amount: number,
  currency: string,
  stripeAccountId?: string
): Promise<{ clientSecret: string }> => {
  try {
    const paymentIntentParams: Stripe.PaymentIntentCreateParams = {
      amount,
      currency,
      payment_method_types: ["card"],
    };

    const options: Stripe.RequestOptions = stripeAccountId ? { stripeAccount: stripeAccountId } : {};

    const paymentIntent = await stripe.paymentIntents.create(paymentIntentParams, options);

    if (!paymentIntent.client_secret) {
      throw new Error("Failed to create payment intent: no client secret returned");
    }

    return { clientSecret: paymentIntent.client_secret };
  } catch (err) {
    logger.error(err, "Error creating payment intent for survey payment element");

    if (err instanceof Stripe.errors.StripeCardError) {
      throw new Error("Payment failed: Your card was declined. Please try a different card.");
    }

    if (err instanceof Stripe.errors.StripeInvalidRequestError) {
      throw new Error("Payment configuration error. Please contact support.");
    }

    throw new Error("An unexpected error occurred while processing your payment. Please try again.");
  }
};

/**
 * Retrieves the current status of a Stripe Payment Intent.
 *
 * Used to verify the outcome of a payment after the client-side confirmation flow completes.
 * Common statuses include "succeeded", "requires_payment_method", "requires_confirmation",
 * "processing", and "canceled".
 *
 * @param paymentIntentId - The PaymentIntent ID (prefixed with `pi_`) to check.
 * @param stripeAccountId - Optional connected Stripe account ID (same routing pattern
 *                          as `createPaymentIntent`).
 * @returns An object with the payment status, amount (in smallest currency unit), and currency code.
 * @throws Error with a user-friendly message if the retrieval fails.
 */
export const confirmPaymentStatus = async (
  paymentIntentId: string,
  stripeAccountId?: string
): Promise<{ status: string; amount: number; currency: string }> => {
  try {
    const options: Stripe.RequestOptions = stripeAccountId ? { stripeAccount: stripeAccountId } : {};

    const paymentIntent = await stripe.paymentIntents.retrieve(paymentIntentId, options);

    return {
      status: paymentIntent.status,
      amount: paymentIntent.amount,
      currency: paymentIntent.currency,
    };
  } catch (err) {
    logger.error(err, "Error confirming payment status for survey payment element");
    throw new Error("Unable to verify payment status. Please try again.");
  }
};
