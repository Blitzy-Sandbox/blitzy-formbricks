import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { logger } from "@formbricks/logger";
import { authOptions } from "@/modules/auth/lib/authOptions";
import { buildStripeConnectAuthorizeUrl } from "@/modules/ee/stripe-connect/lib/stripe-connect";

/**
 * GET /api/stripe-connect/authorize?organizationId=<id>&returnUrl=<url>
 *
 * Redirects the authenticated user to Stripe's OAuth consent page to connect
 * their Stripe account via Stripe Connect Standard. The `organizationId` and
 * `returnUrl` are encoded together in the OAuth `state` parameter so the
 * callback route can redirect the user back to the originating page.
 *
 * Requirements:
 * - User must be authenticated (server session required)
 * - `organizationId` query parameter must be provided
 * - `returnUrl` query parameter is optional (defaults to app root)
 * - `STRIPE_CLIENT_ID` environment variable must be configured
 *
 * Responses:
 * - 302 Redirect to Stripe's OAuth authorize URL on success
 * - 401 Unauthorized if no session
 * - 400 Bad Request if organizationId is missing
 * - 500 Internal Server Error if STRIPE_CLIENT_ID is not configured
 */
export const GET = async (request: Request): Promise<Response> => {
  try {
    // Verify authentication — only logged-in users can initiate Stripe Connect
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // Extract organizationId and returnUrl from query parameters
    const url = new URL(request.url);
    const organizationId = url.searchParams.get("organizationId");
    if (!organizationId) {
      return NextResponse.json({ error: "organizationId query parameter is required" }, { status: 400 });
    }

    // The returnUrl is the page the user should return to after the OAuth flow
    const returnUrl = url.searchParams.get("returnUrl") || undefined;

    // Build the Stripe OAuth authorization URL with both organizationId and returnUrl in state
    const authorizeUrl = buildStripeConnectAuthorizeUrl(organizationId, returnUrl);
    if (!authorizeUrl) {
      return NextResponse.json(
        { error: "Stripe Connect is not configured. STRIPE_CLIENT_ID is missing." },
        { status: 500 }
      );
    }

    // Redirect the user to Stripe's OAuth consent page
    return NextResponse.redirect(authorizeUrl);
  } catch (err) {
    logger.error(err, "Error in Stripe Connect authorize route");
    return NextResponse.json({ error: "Failed to initiate Stripe Connect authorization" }, { status: 500 });
  }
};
