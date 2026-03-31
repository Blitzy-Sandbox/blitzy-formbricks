import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { logger } from "@formbricks/logger";
import { WEBAPP_URL } from "@/lib/constants";
import { authOptions } from "@/modules/auth/lib/authOptions";
import {
  decodeStripeConnectState,
  exchangeStripeConnectCode,
  saveStripeConnectAccount,
} from "@/modules/ee/stripe-connect/lib/stripe-connect";

/**
 * GET /api/stripe-connect/callback?code=<authorization_code>&state=<encoded_state>
 *
 * Stripe redirects here after the user approves the OAuth consent page.
 * This route:
 * 1. Verifies the user is authenticated
 * 2. Decodes the `state` parameter to extract organizationId and returnUrl
 * 3. Exchanges the authorization code for connected account credentials
 * 4. Stores the connected account ID and publishable key on the organization
 * 5. Redirects the user back to the originating page (returnUrl) with a success indicator
 *
 * On error (user denied, Stripe error, exchange failure):
 * - Redirects back to the originating page (or app root) with a visible error message
 * - Logs error details server-side for developer diagnosis
 *
 * Query parameters (from Stripe):
 * - `code`: The authorization code to exchange for account credentials
 * - `state`: Base64url-encoded JSON containing organizationId and returnUrl
 * - `error`: Present if the user denied the connection or an error occurred
 * - `error_description`: Human-readable error description from Stripe
 *
 * Responses:
 * - 302 Redirect to originating page on success
 * - 302 Redirect to originating page (or app root) with error on failure
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
    const stateRaw = url.searchParams.get("state");
    const error = url.searchParams.get("error");
    const errorDescription = url.searchParams.get("error_description");

    // Decode state to extract organizationId and returnUrl
    let organizationId: string | null = null;
    let returnUrl = "";

    if (stateRaw) {
      const decoded = decodeStripeConnectState(stateRaw);
      organizationId = decoded.organizationId;
      returnUrl = decoded.returnUrl;
    }

    /**
     * Builds the redirect URL, preferring the returnUrl from state.
     * Falls back to the WEBAPP_URL root if no returnUrl was provided.
     */
    const buildRedirectUrl = (basePath?: string): URL => {
      if (returnUrl) {
        // Ensure the returnUrl is a same-origin path to prevent open redirect
        try {
          const target = new URL(returnUrl, WEBAPP_URL);
          if (target.origin === new URL(WEBAPP_URL).origin) {
            return target;
          }
        } catch {
          // Invalid URL — fall through to default
        }
      }
      return new URL(basePath || "/", WEBAPP_URL);
    };

    // Handle OAuth error (e.g., user denied the connection)
    if (error) {
      logger.warn({ error, errorDescription, organizationId }, "Stripe Connect OAuth error returned");
      const redirectUrl = buildRedirectUrl();
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

    // Redirect back to the originating page with success indicator
    const successUrl = buildRedirectUrl();
    successUrl.searchParams.set("stripe_connect_success", "1");
    return NextResponse.redirect(successUrl.toString());
  } catch (err) {
    logger.error(err, "Error in Stripe Connect callback route");

    // Attempt to extract returnUrl from state for error redirect
    let errorRedirectPath = "/";
    try {
      const stateParam = new URL(request.url).searchParams.get("state");
      if (stateParam) {
        const decoded = decodeStripeConnectState(stateParam);
        if (decoded.returnUrl) {
          const target = new URL(decoded.returnUrl, WEBAPP_URL);
          if (target.origin === new URL(WEBAPP_URL).origin) {
            errorRedirectPath = target.pathname + target.search;
          }
        }
      }
    } catch {
      // Ignore decode errors — use default path
    }

    const errorUrl = new URL(errorRedirectPath, WEBAPP_URL);
    errorUrl.searchParams.set("stripe_connect_error", "Failed to connect Stripe account");
    return NextResponse.redirect(errorUrl.toString());
  }
};
