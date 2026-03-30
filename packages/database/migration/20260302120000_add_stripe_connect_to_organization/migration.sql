-- AlterTable: Add Stripe Connect fields to Organization
-- These columns store the connected Stripe account credentials obtained via Stripe Connect OAuth.
-- Both fields are nullable: NULL means no Stripe account has been connected for this organization.
-- Rollback: ALTER TABLE "Organization" DROP COLUMN "stripeConnectAccountId", DROP COLUMN "stripeConnectPublishableKey";

ALTER TABLE "Organization" ADD COLUMN "stripeConnectAccountId" TEXT;
ALTER TABLE "Organization" ADD COLUMN "stripeConnectPublishableKey" TEXT;
