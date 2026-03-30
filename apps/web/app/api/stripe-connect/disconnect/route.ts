import { getServerSession } from "next-auth";
import { NextResponse } from "next/server";
import { logger } from "@formbricks/logger";
import { authOptions } from "@/modules/auth/lib/authOptions";
import { disconnectStripeConnectAccount } from "@/modules/ee/stripe-connect/lib/stripe-connect";

/**
 * POST /api/stripe-connect/disconnect
 *
 * Disconnects a Stripe Connect account from an organization by clearing the stored
 * credentials in the database. This does NOT revoke the OAuth authorization on
 * Stripe's side — the organization admin should also deauthorize the application
 * in their Stripe Dashboard.
 *
 * Request body (JSON):
 * - `organizationId`: string — The CUID of the organization to disconnect
 *
 * Responses:
 * - 200 OK with updated organization record
 * - 400 Bad Request if organizationId is missing or invalid
 * - 401 Unauthorized if no session
 * - 500 Internal Server Error on failure
 */
export const POST = async (request: Request): Promise<Response> => {
  try {
    // Verify authentication
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    let body: { organizationId?: string };
    try {
      body = await request.json();
    } catch {
      return NextResponse.json({ error: "Malformed JSON input" }, { status: 400 });
    }

    const { organizationId } = body;
    if (!organizationId || typeof organizationId !== "string") {
      return NextResponse.json({ error: "organizationId is required and must be a string" }, { status: 400 });
    }

    const result = await disconnectStripeConnectAccount(organizationId);

    logger.info({ organizationId }, "Disconnected Stripe Connect account from organization");

    return NextResponse.json({ data: result }, { status: 200 });
  } catch (err) {
    logger.error(err, "Error in Stripe Connect disconnect route");
    return NextResponse.json({ error: "Failed to disconnect Stripe account" }, { status: 500 });
  }
};
