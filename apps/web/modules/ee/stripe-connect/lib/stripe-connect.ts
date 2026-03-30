import "server-only";
import Stripe from "stripe";
import { prisma } from "@formbricks/database";
import { logger } from "@formbricks/logger";
import { ResourceNotFoundError } from "@formbricks/types/errors";
import { STRIPE_API_VERSION } from "@/lib/constants";
import { env } from "@/lib/env";

/**
 * Retrieves the Stripe Connect credentials for an organization.
 *
 * @param organizationId - The CUID of the organization to look up.
 * @returns An object with the connected Stripe account ID and publishable key,
 *          or null values if no Stripe account is connected.
 * @throws ResourceNotFoundError if the organization does not exist.
 */
export const getStripeConnectAccount = async (
  organizationId: string
): Promise<{
  stripeConnectAccountId: string | null;
  stripeConnectPublishableKey: string | null;
}> => {
  const organization = await prisma.organization.findUnique({
    where: { id: organizationId },
    select: {
      stripeConnectAccountId: true,
      stripeConnectPublishableKey: true,
    },
  });

  if (!organization) {
    throw new ResourceNotFoundError("Organization", organizationId);
  }

  return {
    stripeConnectAccountId: organization.stripeConnectAccountId,
    stripeConnectPublishableKey: organization.stripeConnectPublishableKey,
  };
};

/**
 * Saves the Stripe Connect credentials for an organization after a successful OAuth flow.
 *
 * @param organizationId - The CUID of the organization to update.
 * @param stripeConnectAccountId - The connected Stripe account ID (e.g., "acct_...").
 * @param stripeConnectPublishableKey - The connected account's publishable key (e.g., "pk_live_...").
 * @returns The updated organization record (id, stripeConnectAccountId, stripeConnectPublishableKey).
 * @throws ResourceNotFoundError if the organization does not exist.
 */
export const saveStripeConnectAccount = async (
  organizationId: string,
  stripeConnectAccountId: string,
  stripeConnectPublishableKey: string
): Promise<{
  id: string;
  stripeConnectAccountId: string | null;
  stripeConnectPublishableKey: string | null;
}> => {
  // Verify the organization exists before updating
  const existingOrg = await prisma.organization.findUnique({
    where: { id: organizationId },
    select: { id: true },
  });

  if (!existingOrg) {
    throw new ResourceNotFoundError("Organization", organizationId);
  }

  const updated = await prisma.organization.update({
    where: { id: organizationId },
    data: {
      stripeConnectAccountId,
      stripeConnectPublishableKey,
    },
    select: {
      id: true,
      stripeConnectAccountId: true,
      stripeConnectPublishableKey: true,
    },
  });

  return updated;
};

/**
 * Disconnects a Stripe Connect account from an organization by clearing the stored credentials.
 * This does NOT revoke the OAuth authorization on Stripe's side — it only removes the
 * stored account reference from the Formbricks database.
 *
 * @param organizationId - The CUID of the organization to disconnect.
 * @returns The updated organization record with null Stripe Connect fields.
 * @throws ResourceNotFoundError if the organization does not exist.
 */
export const disconnectStripeConnectAccount = async (
  organizationId: string
): Promise<{
  id: string;
  stripeConnectAccountId: string | null;
  stripeConnectPublishableKey: string | null;
}> => {
  const existingOrg = await prisma.organization.findUnique({
    where: { id: organizationId },
    select: { id: true },
  });

  if (!existingOrg) {
    throw new ResourceNotFoundError("Organization", organizationId);
  }

  const updated = await prisma.organization.update({
    where: { id: organizationId },
    data: {
      stripeConnectAccountId: null,
      stripeConnectPublishableKey: null,
    },
    select: {
      id: true,
      stripeConnectAccountId: true,
      stripeConnectPublishableKey: true,
    },
  });

  return updated;
};

/**
 * Builds the Stripe OAuth authorization URL that redirects the user to Stripe's
 * consent page for connecting their Stripe account via Stripe Connect Standard.
 *
 * @param organizationId - The CUID of the organization initiating the connection.
 *                         Passed as the `state` parameter for CSRF protection and
 *                         to identify the organization during the callback.
 * @returns The full Stripe OAuth authorization URL, or null if STRIPE_CLIENT_ID is not configured.
 */
export const buildStripeConnectAuthorizeUrl = (organizationId: string): string | null => {
  const clientId = env.STRIPE_CLIENT_ID;
  if (!clientId) {
    logger.warn("STRIPE_CLIENT_ID is not configured — Stripe Connect OAuth is unavailable");
    return null;
  }

  const baseUrl = "https://connect.stripe.com/oauth/authorize";
  const params = new URLSearchParams({
    response_type: "code",
    client_id: clientId,
    scope: "read_write",
    state: organizationId,
  });

  return `${baseUrl}?${params.toString()}`;
};

/**
 * Exchanges a Stripe OAuth authorization code for connected account credentials.
 * This is called during the OAuth callback after the user approves the connection.
 *
 * @param code - The authorization code returned by Stripe in the callback URL.
 * @returns An object containing the connected account's `stripe_user_id` and `stripe_publishable_key`.
 * @throws Error if STRIPE_SECRET_KEY is not configured or if the Stripe API call fails.
 */
export const exchangeStripeConnectCode = async (
  code: string
): Promise<{
  stripeUserId: string;
  stripePublishableKey: string;
}> => {
  if (!env.STRIPE_SECRET_KEY) {
    throw new Error(
      "STRIPE_SECRET_KEY is not configured — cannot exchange Stripe Connect authorization code"
    );
  }

  const stripe = new Stripe(env.STRIPE_SECRET_KEY, {
    apiVersion: STRIPE_API_VERSION,
  });

  // Isolate the Stripe API call in its own try-catch so that our validation
  // errors (e.g. missing stripe_user_id) propagate without being wrapped.
  let response: Stripe.OAuthToken;
  try {
    response = await stripe.oauth.token({
      grant_type: "authorization_code",
      code,
    });
  } catch (err) {
    logger.error(err, "Failed to exchange Stripe Connect authorization code");

    if (err instanceof Stripe.errors.StripeInvalidGrantError) {
      throw new Error(
        "The Stripe authorization code is invalid or has already been used. Please try connecting again."
      );
    }

    if (err instanceof Stripe.errors.StripeAuthenticationError) {
      throw new Error("Stripe authentication failed. Please verify your platform Stripe configuration.");
    }

    throw new Error("Failed to connect your Stripe account. Please try again.");
  }

  if (!response.stripe_user_id) {
    throw new Error("Stripe Connect OAuth response did not include stripe_user_id");
  }

  return {
    stripeUserId: response.stripe_user_id,
    stripePublishableKey: response.stripe_publishable_key ?? "",
  };
};
