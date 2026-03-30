"use server";

import { z } from "zod";
import { ZId } from "@formbricks/types/common";
import { ResourceNotFoundError } from "@formbricks/types/errors";
import { type TSurveyBlock } from "@formbricks/types/surveys/blocks";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/constants";
import { getOrganizationByEnvironmentId } from "@/lib/organization/service";
import { getSurvey } from "@/lib/survey/service";
import { actionClient } from "@/lib/utils/action-client";
import { createPaymentIntent } from "@/modules/survey/payment/lib/stripe";

// Zod input schema for the createPaymentIntentAction server action.
// Validates all required parameters before the handler executes.
// Note: stripeAccountId is NO LONGER accepted from the client. It is resolved
// server-side from the organization's stored Stripe Connect credentials.
const ZCreatePaymentIntentAction = z.object({
  // CUID2-validated survey identifier used to verify the survey exists and has a matching Payment element.
  surveyId: ZId,
  // ISO 4217 lowercase currency code. Matches ZSurveyPaymentElement.currency enum values.
  currency: z.enum(["usd", "eur", "gbp"]),
  // Positive integer in the smallest currency unit (cents for USD/EUR, pence for GBP).
  // Must be >= 1 to prevent zero-amount payment intents.
  amount: z.number().int().positive().min(1),
});

/**
 * Server action for creating a Stripe PaymentIntent for the survey Payment element.
 *
 * This action is UNAUTHENTICATED because Formbricks supports public link surveys
 * where respondents are anonymous. Unauthenticated respondents must still be able
 * to submit payments during survey flows.
 *
 * Security: Instead of requiring a logged-in session, this action validates that:
 * 1. The referenced survey exists
 * 2. The survey contains at least one Payment element
 * 3. The requested amount and currency match a Payment element in the survey
 *
 * The connected Stripe account is resolved server-side from the organization's
 * stored Stripe Connect credentials. The client NEVER provides the stripeAccountId.
 *
 * This module is COMPLETELY SEPARATE from the billing module at
 * apps/web/modules/ee/billing/. The billing module handles platform subscription management.
 * This module handles per-survey payment collection via connected Stripe accounts.
 */
export const createPaymentIntentAction = actionClient
  .schema(ZCreatePaymentIntentAction)
  .action(async ({ parsedInput }) => {
    const { surveyId, amount, currency } = parsedInput;

    // Verify the survey exists — throws ResourceNotFoundError if not found
    const survey = await getSurvey(surveyId);
    if (!survey) {
      throw new ResourceNotFoundError("Survey", surveyId);
    }

    // Verify the survey contains a Payment element with matching amount and currency.
    // This prevents creating arbitrary PaymentIntents for non-existent payment configurations.
    // Payment elements are stored in survey.blocks (the new block/element model),
    // not in the deprecated survey.questions array.
    const allElements = survey.blocks.flatMap((block: TSurveyBlock) => block.elements);
    const paymentElement = allElements.find(
      (el) => el.type === TSurveyElementTypeEnum.Payment && el.amount === amount && el.currency === currency
    );

    if (!paymentElement) {
      throw new ResourceNotFoundError(
        "Payment element",
        `No Payment element found in survey ${surveyId} with amount=${String(amount)} and currency=${currency}`
      );
    }

    // Resolve the connected Stripe account from the organization's stored credentials.
    // The stripeAccountId MUST come from the database, never from the client.
    const organization = await getOrganizationByEnvironmentId(survey.environmentId);
    if (!organization) {
      throw new ResourceNotFoundError("Organization", `for environment ${survey.environmentId}`);
    }

    const stripeAccountId = organization.stripeConnectAccountId ?? undefined;
    if (!stripeAccountId) {
      throw new Error(
        "No Stripe account is connected for this organization. Please connect a Stripe account in the survey editor."
      );
    }

    // Delegate to the Stripe helper which wraps stripe.paymentIntents.create().
    // Returns { clientSecret: string } on success.
    // Stripe errors are caught in the helper and re-thrown with user-friendly messages.
    // Pass surveyId for idempotency key derivation and PaymentIntent metadata.
    return await createPaymentIntent(amount, currency, stripeAccountId, surveyId);
  });
