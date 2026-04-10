import { logger } from "@formbricks/logger";
import { type TSurveyBlock } from "@formbricks/types/surveys/blocks";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/constants";
import { responses } from "@/app/lib/api/response";
import { getOrganizationByEnvironmentId } from "@/lib/organization/service";
import { getSurvey } from "@/lib/survey/service";
import { createPaymentIntent } from "@/modules/survey/payment/lib/stripe";

/**
 * CORS preflight handler.
 * Payment intent creation must support cross-origin requests for embedded surveys
 * that run on external domains.
 */
export const OPTIONS = async (): Promise<Response> => {
  return responses.successResponse({}, true, "public, s-maxage=3600, max-age=3600");
};

/**
 * POST /api/v1/client/payment-intent
 *
 * Creates a Stripe PaymentIntent for a survey Payment element.
 *
 * This endpoint is UNAUTHENTICATED because Formbricks supports public link surveys
 * where respondents are anonymous. Security is enforced by validating that the
 * requested amount and currency match a Payment element configured in the survey.
 *
 * The connected Stripe account ID is looked up server-side from the organization's
 * stored Stripe Connect credentials. The client does NOT need to pass stripeAccountId.
 * If the organization has not connected a Stripe account, the route returns a 400 error.
 *
 * Request body:
 *   - surveyId: string (CUID2) — the survey containing the Payment element
 *   - amount: number — positive integer in smallest currency unit (cents/pence)
 *   - currency: "usd" | "eur" | "gbp"
 *
 * Response (200):
 *   - { data: { clientSecret: string } }
 *
 * Error responses:
 *   - 400 Bad Request — missing/invalid parameters or no connected Stripe account
 *   - 404 Not Found — survey doesn't exist or no matching Payment element
 *   - 500 Internal Server Error — Stripe API failure
 */
export const POST = async (request: Request): Promise<Response> => {
  let body: {
    surveyId?: string;
    amount?: number;
    currency?: string;
  };

  try {
    body = await request.json();
  } catch {
    return responses.badRequestResponse("Malformed JSON input");
  }

  const { surveyId, amount, currency } = body;

  // Validate required parameters
  if (!surveyId || typeof surveyId !== "string") {
    return responses.badRequestResponse("surveyId is required and must be a string");
  }

  if (!amount || typeof amount !== "number" || !Number.isInteger(amount) || amount < 1) {
    return responses.badRequestResponse("amount is required and must be a positive integer >= 1");
  }

  if (!currency || !["usd", "eur", "gbp"].includes(currency)) {
    return responses.badRequestResponse('currency is required and must be one of "usd", "eur", "gbp"');
  }

  try {
    // Verify the survey exists
    const survey = await getSurvey(surveyId);
    if (!survey) {
      return responses.notFoundResponse("Survey", surveyId);
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
      return responses.notFoundResponse(
        "Payment element",
        `No matching Payment element in survey ${surveyId}`
      );
    }

    // Look up the organization's connected Stripe account server-side.
    // The stripeAccountId MUST come from the database, never from the client request.
    const organization = await getOrganizationByEnvironmentId(survey.environmentId);
    if (!organization) {
      return responses.internalServerErrorResponse("Unable to resolve organization for this survey.");
    }

    const stripeAccountId = organization.stripeConnectAccountId ?? undefined;
    if (!stripeAccountId) {
      return responses.badRequestResponse(
        "No Stripe account is connected for this organization. Please connect a Stripe account in the survey editor."
      );
    }

    // Create the PaymentIntent via Stripe, passing surveyId for idempotency and metadata
    const result = await createPaymentIntent(amount, currency, stripeAccountId, surveyId);

    return responses.successResponse(result, true);
  } catch (err) {
    logger.error(err, "Error creating payment intent via client API");
    return responses.internalServerErrorResponse("Failed to create payment intent. Please try again.");
  }
};
