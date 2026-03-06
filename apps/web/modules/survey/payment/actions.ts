"use server";

import { z } from "zod";
import { ZId } from "@formbricks/types/common";
import { authenticatedActionClient } from "@/lib/utils/action-client";
import { checkAuthorizationUpdated } from "@/lib/utils/action-client/action-client-middleware";
import { AuthenticatedActionClientCtx } from "@/lib/utils/action-client/types/context";
import { getOrganizationIdFromSurveyId } from "@/lib/utils/helper";
import { createPaymentIntent } from "@/modules/survey/payment/lib/stripe";

// Zod input schema for the createPaymentIntentAction server action.
// Validates all required parameters before the handler executes.
const ZCreatePaymentIntentAction = z.object({
  // CUID2-validated survey identifier used to resolve the organization for authorization.
  surveyId: ZId,
  // ISO 4217 lowercase currency code. Matches ZSurveyPaymentElement.currency enum values.
  currency: z.enum(["usd", "eur", "gbp"]),
  // Positive integer in the smallest currency unit (cents for USD/EUR, pence for GBP).
  // Must be >= 1 to prevent zero-amount payment intents.
  amount: z.number().int().positive().min(1),
  // Optional connected Stripe account ID for multi-tenant payment routing via Stripe Connect.
  // When provided, the PaymentIntent is created on the connected account.
  stripeAccountId: z.string().optional(),
});

/**
 * Server action for creating a Stripe PaymentIntent for the survey Payment element.
 *
 * This action:
 * 1. Validates the input via the ZCreatePaymentIntentAction Zod schema
 * 2. Authenticates the user session via authenticatedActionClient middleware
 * 3. Resolves the organization from the surveyId and checks authorization
 * 4. Delegates to createPaymentIntent() in ./lib/stripe.ts for the Stripe API call
 * 5. Returns { clientSecret: string } for client-side payment confirmation via Stripe Elements
 *
 * Authorization: User must have organization-level access with role owner, manager, or member.
 * Members are authorized because respondents submitting surveys with payment elements need
 * to trigger PaymentIntent creation.
 *
 * Error handling: Stripe API errors are caught and wrapped with user-friendly messages in
 * the createPaymentIntent helper. Unexpected errors are handled by the safe action client's
 * handleServerError middleware.
 *
 * IMPORTANT: This module is COMPLETELY SEPARATE from the billing module at
 * apps/web/modules/ee/billing/. The billing module handles platform subscription management.
 * This module handles per-survey payment collection via connected Stripe accounts.
 */
export const createPaymentIntentAction = authenticatedActionClient
  .schema(ZCreatePaymentIntentAction)
  .action(
    async ({
      ctx,
      parsedInput,
    }: {
      ctx: AuthenticatedActionClientCtx;
      parsedInput: z.infer<typeof ZCreatePaymentIntentAction>;
    }) => {
      // Resolve the organization ID from the survey to perform authorization checks.
      // Throws ResourceNotFoundError if the survey does not exist.
      const organizationId = await getOrganizationIdFromSurveyId(parsedInput.surveyId);

      // Verify the authenticated user has sufficient organization-level access.
      // Roles: owner, manager, or member — members are included because survey respondents
      // who are authenticated users may trigger payment collection during survey submission.
      await checkAuthorizationUpdated({
        userId: ctx.user.id,
        organizationId,
        access: [
          {
            type: "organization",
            roles: ["owner", "manager", "member"],
          },
        ],
      });

      // Delegate to the Stripe helper which wraps stripe.paymentIntents.create().
      // Returns { clientSecret: string } on success.
      // Stripe errors are caught in the helper and re-thrown with user-friendly messages.
      return await createPaymentIntent(parsedInput.amount, parsedInput.currency, parsedInput.stripeAccountId);
    }
  );
