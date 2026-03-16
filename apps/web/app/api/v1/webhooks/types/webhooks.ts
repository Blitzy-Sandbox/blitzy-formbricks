import { z } from "zod";
import { ZWebhook } from "@formbricks/database/zod/webhooks";

export const ZWebhookInput = ZWebhook.partial({
  name: true,
  source: true,
  surveyIds: true,
  payloadFormat: true,
}).pick({
  name: true,
  source: true,
  surveyIds: true,
  triggers: true,
  url: true,
  environmentId: true,
  payloadFormat: true,
});

export type TWebhookInput = z.infer<typeof ZWebhookInput>;
