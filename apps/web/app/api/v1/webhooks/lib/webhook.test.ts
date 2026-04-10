import { Prisma, WebhookSource } from "@prisma/client";
import { cleanup } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { prisma } from "@formbricks/database";
import { DatabaseError, ValidationError } from "@formbricks/types/errors";
import { createWebhook, getWebhooks } from "@/app/api/v1/webhooks/lib/webhook";
import { TWebhookInput } from "@/app/api/v1/webhooks/types/webhooks";
import { validateInputs } from "@/lib/utils/validate";

vi.mock("@formbricks/database", () => ({
  prisma: {
    webhook: {
      create: vi.fn(),
      findMany: vi.fn(),
    },
  },
}));

vi.mock("@/lib/utils/validate", () => ({
  validateInputs: vi.fn(),
}));

vi.mock("@/lib/crypto", () => ({
  generateWebhookSecret: vi.fn(() => "whsec_test_secret_1234567890"),
}));

describe("createWebhook", () => {
  afterEach(() => {
    cleanup();
  });

  test("should create a webhook", async () => {
    const webhookInput: TWebhookInput = {
      environmentId: "test-env-id",
      name: "Test Webhook",
      url: "https://example.com",
      source: "user",
      triggers: ["responseCreated"],
      surveyIds: ["survey1", "survey2"],
    };

    const createdWebhook = {
      id: "webhook-id",
      environmentId: "test-env-id",
      name: "Test Webhook",
      url: "https://example.com",
      source: "user" as WebhookSource,
      triggers: ["responseCreated"],
      surveyIds: ["survey1", "survey2"],
      createdAt: new Date(),
      updatedAt: new Date(),
    } as any;

    vi.mocked(prisma.webhook.create).mockResolvedValueOnce(createdWebhook);

    const result = await createWebhook(webhookInput);

    expect(validateInputs).toHaveBeenCalled();

    expect(prisma.webhook.create).toHaveBeenCalledWith({
      data: {
        url: webhookInput.url,
        name: webhookInput.name,
        source: webhookInput.source,
        surveyIds: webhookInput.surveyIds,
        triggers: webhookInput.triggers,
        payloadFormat: undefined,
        secret: "whsec_test_secret_1234567890",
        environment: {
          connect: {
            id: webhookInput.environmentId,
          },
        },
      },
    });

    expect(result).toEqual(createdWebhook);
  });

  test("should throw a ValidationError if the input data does not match the ZWebhookInput schema", async () => {
    const invalidWebhookInput = {
      environmentId: "test-env-id",
      name: "Test Webhook",
      url: 123, // Invalid URL
      source: "user" as WebhookSource,
      triggers: ["responseCreated"],
      surveyIds: ["survey1", "survey2"],
    };

    vi.mocked(validateInputs).mockImplementation(() => {
      throw new ValidationError("Validation failed");
    });

    await expect(createWebhook(invalidWebhookInput as any)).rejects.toThrowError(ValidationError);
  });

  test("should throw a DatabaseError if a PrismaClientKnownRequestError occurs", async () => {
    const webhookInput: TWebhookInput = {
      environmentId: "test-env-id",
      name: "Test Webhook",
      url: "https://example.com",
      source: "user",
      triggers: ["responseCreated"],
      surveyIds: ["survey1", "survey2"],
    };

    vi.mocked(prisma.webhook.create).mockRejectedValueOnce(
      new Prisma.PrismaClientKnownRequestError("Test error", {
        code: "P2002",
        clientVersion: "5.0.0",
      })
    );

    await expect(createWebhook(webhookInput)).rejects.toThrowError(DatabaseError);
  });

  test("should throw a DatabaseError when provided with invalid surveyIds", async () => {
    const webhookInput: TWebhookInput = {
      environmentId: "test-env-id",
      name: "Test Webhook",
      url: "https://example.com",
      source: "user",
      triggers: ["responseCreated"],
      surveyIds: ["invalid-survey-id"],
    };

    vi.mocked(prisma.webhook.create).mockRejectedValueOnce(new Error("Foreign key constraint violation"));

    await expect(createWebhook(webhookInput)).rejects.toThrowError(DatabaseError);
  });

  test("should handle edge case URLs that are technically valid but problematic", async () => {
    const webhookInput: TWebhookInput = {
      environmentId: "test-env-id",
      name: "Test Webhook",
      url: "http://localhost:3000", // Example of a potentially problematic URL
      source: "user",
      triggers: ["responseCreated"],
      surveyIds: ["survey1", "survey2"],
    };

    vi.mocked(prisma.webhook.create).mockRejectedValueOnce(new DatabaseError("Invalid URL"));

    await expect(createWebhook(webhookInput)).rejects.toThrowError(DatabaseError);

    expect(validateInputs).toHaveBeenCalled();
    expect(prisma.webhook.create).toHaveBeenCalledWith({
      data: {
        url: webhookInput.url,
        name: webhookInput.name,
        source: webhookInput.source,
        surveyIds: webhookInput.surveyIds,
        triggers: webhookInput.triggers,
        secret: "whsec_test_secret_1234567890",
        environment: {
          connect: {
            id: webhookInput.environmentId,
          },
        },
      },
    });
  });
});

describe("getWebhooks", () => {
  afterEach(() => {
    cleanup();
  });

  test("should return webhooks for given environment IDs", async () => {
    const mockWebhooks = [
      {
        id: "wh-1",
        environmentId: "env-1",
        name: "Webhook 1",
        url: "https://example.com/hook1",
        source: "user" as WebhookSource,
        triggers: ["responseCreated"],
        surveyIds: ["s1"],
        createdAt: new Date(),
        updatedAt: new Date(),
        secret: "whsec_secret",
        payloadFormat: "default",
      },
      {
        id: "wh-2",
        environmentId: "env-1",
        name: "Webhook 2",
        url: "https://example.com/hook2",
        source: "user" as WebhookSource,
        triggers: ["responseFinished"],
        surveyIds: [],
        createdAt: new Date(),
        updatedAt: new Date(),
        secret: "whsec_secret2",
        payloadFormat: "typeform",
      },
    ];

    vi.mocked(prisma.webhook.findMany).mockResolvedValueOnce(mockWebhooks as any);

    const result = await getWebhooks(["env-1"]);

    expect(validateInputs).toHaveBeenCalled();
    expect(prisma.webhook.findMany).toHaveBeenCalledWith({
      where: { environmentId: { in: ["env-1"] } },
      take: undefined,
      skip: undefined,
    });
    expect(result).toEqual(mockWebhooks);
  });

  test("should paginate results when page parameter is provided", async () => {
    vi.mocked(prisma.webhook.findMany).mockResolvedValueOnce([]);

    const result = await getWebhooks(["env-1", "env-2"], 2);

    expect(prisma.webhook.findMany).toHaveBeenCalledWith({
      where: { environmentId: { in: ["env-1", "env-2"] } },
      take: expect.any(Number),
      skip: expect.any(Number),
    });
    expect(result).toEqual([]);
  });

  test("should throw DatabaseError on PrismaClientKnownRequestError", async () => {
    vi.mocked(prisma.webhook.findMany).mockRejectedValueOnce(
      new Prisma.PrismaClientKnownRequestError("Test error", {
        code: "P2025",
        clientVersion: "5.0.0",
      })
    );

    await expect(getWebhooks(["env-1"])).rejects.toThrowError(DatabaseError);
  });

  test("should rethrow unknown errors", async () => {
    const unknownError = new Error("Unexpected error");
    vi.mocked(prisma.webhook.findMany).mockRejectedValueOnce(unknownError);

    await expect(getWebhooks(["env-1"])).rejects.toThrowError("Unexpected error");
  });
});
