import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { logger } from "@formbricks/logger";
import { authOptions } from "@/modules/auth/lib/authOptions";
import { getStripeConnectAccount } from "@/modules/ee/stripe-connect/lib/stripe-connect";

/**
 * GET /api/stripe-connect/status?organizationId=<id>
 *
 * Returns the Stripe Connect status for an organization. Used by the
 * Payment element editor to determine whether to show "Connect Stripe"
 * or "Stripe Connected" UI.
 *
 * Responses:
 * - 200 OK with { data: { stripeConnectAccountId, stripeConnectPublishableKey } }
 * - 400 Bad Request if organizationId is missing
 * - 401 Unauthorized if no session
 * - 500 Internal Server Error on failure
 */
export const GET = async (request: Request): Promise<Response> => {
  try {
    // Verify authentication
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const url = new URL(request.url);
    const organizationId = url.searchParams.get("organizationId");

    if (!organizationId) {
      return NextResponse.json({ error: "organizationId query parameter is required" }, { status: 400 });
    }

    const result = await getStripeConnectAccount(organizationId);

    return NextResponse.json({ data: result }, { status: 200 });
  } catch (err) {
    logger.error(err, "Error fetching Stripe Connect status");
    return NextResponse.json({ error: "Failed to fetch Stripe Connect status" }, { status: 500 });
  }
};
