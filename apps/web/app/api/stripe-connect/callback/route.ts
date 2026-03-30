import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { logger } from "@formbricks/logger";
import { WEBAPP_URL } from "@/lib/constants";
import { authOptions } from "@/modules/auth/lib/authOptions";
import {
  exchangeStripeConnectCode,
  saveStripeConnectAccount,
} from "@/modules/ee/stripe-connect/lib/stripe-connect";

/**
 * GET /api/stripe-connect/callback?code=<authorization_code>&state=<organizationId>
 *
 * Stripe redirects here after the user approves the OAuth consent page.
 * This route:
 * 1. Verifies the user is authenticated
 * 2. Exchanges the authorization code for connected account credentials
 * 3. Stores the connected account ID and publishable key on the organization
 * 4. Redirects to the survey editor (or a suitable page indicating success)
 *
 * Query parameters (from Stripe):
 * - `code`: The authorization code to exchange for account credentials
 * - `state`: The organizationId passed during the authorize step (CSRF protection)
 * - `error`: Present if the user denied the connection or an error occurred
 * - `error_description`: Human-readable error description from Stripe
 *
 * Responses:
 * - 302 Redirect to success page on success
 * - 302 Redirect to error page if the user denied or an error occurred
 * - 401 Unauthorized if no session
 */
export const GET = async (request: Request): Promise<Response> => {
  try {
    // Verify authentication — only logged-in users can complete Stripe Connect
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const url = new URL(request.url);
    const code = url.searchParams.get("code");
    const organizationId = url.searchParams.get("state");
    const error = url.searchParams.get("error");
    const errorDescription = url.searchParams.get("error_description");

    // Handle OAuth error (e.g., user denied the connection)
    if (error) {
      logger.warn({ error, errorDescription }, "Stripe Connect OAuth error returned");
      const redirectUrl = new URL(`${WEBAPP_URL}/`);
      redirectUrl.searchParams.set("stripe_connect_error", errorDescription || error);
      return NextResponse.redirect(redirectUrl.toString());
    }

    // Validate required parameters
    if (!code) {
      return NextResponse.json({ error: "Missing authorization code from Stripe" }, { status: 400 });
    }

    if (!organizationId) {
      return NextResponse.json({ error: "Missing organization state parameter" }, { status: 400 });
    }

    // Exchange the authorization code for connected account credentials
    const { stripeUserId, stripePublishableKey } = await exchangeStripeConnectCode(code);

    // Persist the connected account credentials on the organization
    await saveStripeConnectAccount(organizationId, stripeUserId, stripePublishableKey);

    logger.info({ organizationId, stripeUserId }, "Successfully connected Stripe account via Stripe Connect");

    // Redirect to the organization's settings page or home page indicating success
    const successUrl = new URL(`${WEBAPP_URL}/`);
    successUrl.searchParams.set("stripe_connect_success", "1");
    return NextResponse.redirect(successUrl.toString());
  } catch (err) {
    logger.error(err, "Error in Stripe Connect callback route");
    const errorUrl = new URL(`${WEBAPP_URL}/`);
    errorUrl.searchParams.set("stripe_connect_error", "Failed to connect Stripe account");
    return NextResponse.redirect(errorUrl.toString());
  }
};
