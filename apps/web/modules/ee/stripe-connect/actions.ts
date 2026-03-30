"use server";

import { z } from "zod";
import { ZId } from "@formbricks/types/common";
import { authenticatedActionClient } from "@/lib/utils/action-client";
import { checkAuthorizationUpdated } from "@/lib/utils/action-client/action-client-middleware";
import { AuthenticatedActionClientCtx } from "@/lib/utils/action-client/types/context";
import {
  disconnectStripeConnectAccount,
  getStripeConnectAccount,
} from "@/modules/ee/stripe-connect/lib/stripe-connect";

// -------------------------------------------------------------------
// Schema definitions
// -------------------------------------------------------------------

const ZGetStripeConnectAccountAction = z.object({
  organizationId: ZId,
});

const ZDisconnectStripeConnectAction = z.object({
  organizationId: ZId,
});

// -------------------------------------------------------------------
// Actions
// -------------------------------------------------------------------

/**
 * Retrieves the Stripe Connect status for an organization.
 * Only organization owners and managers can view Stripe Connect credentials.
 */
export const getStripeConnectAccountAction = authenticatedActionClient
  .schema(ZGetStripeConnectAccountAction)
  .action(
    async ({
      ctx,
      parsedInput,
    }: {
      ctx: AuthenticatedActionClientCtx;
      parsedInput: { organizationId: string };
    }) => {
      await checkAuthorizationUpdated({
        userId: ctx.user.id,
        organizationId: parsedInput.organizationId,
        access: [
          {
            type: "organization",
            roles: ["owner", "manager"],
          },
        ],
      });

      return await getStripeConnectAccount(parsedInput.organizationId);
    }
  );

/**
 * Disconnects a Stripe Connect account from an organization.
 * Only organization owners can disconnect a Stripe Connect account.
 */
export const disconnectStripeConnectAction = authenticatedActionClient
  .schema(ZDisconnectStripeConnectAction)
  .action(
    async ({
      ctx,
      parsedInput,
    }: {
      ctx: AuthenticatedActionClientCtx;
      parsedInput: { organizationId: string };
    }) => {
      await checkAuthorizationUpdated({
        userId: ctx.user.id,
        organizationId: parsedInput.organizationId,
        access: [
          {
            type: "organization",
            roles: ["owner"],
          },
        ],
      });

      return await disconnectStripeConnectAccount(parsedInput.organizationId);
    }
  );
