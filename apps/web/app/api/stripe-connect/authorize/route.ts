import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { logger } from "@formbricks/logger";
import { authOptions } from "@/modules/auth/lib/authOptions";
import { buildStripeConnectAuthorizeUrl } from "@/modules/ee/stripe-connect/lib/stripe-connect";

/**
 * GET /api/stripe-connect/authorize?organizationId=<id>
 *
 * Redirects the authenticated user to Stripe's OAuth consent page to connect
 * their Stripe account via Stripe Connect Standard. The `organizationId` is
 * passed as the OAuth `state` parameter for CSRF protection and to identify
 * which organization to update during the callback.
 *
 * Requirements:
 * - User must be authenticated (server session required)
 * - `organizationId` query parameter must be provided
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

    // Extract organizationId from query parameters
    const url = new URL(request.url);
    const organizationId = url.searchParams.get("organizationId");
    if (!organizationId) {
      return NextResponse.json({ error: "organizationId query parameter is required" }, { status: 400 });
    }

    // Build the Stripe OAuth authorization URL
    const authorizeUrl = buildStripeConnectAuthorizeUrl(organizationId);
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
