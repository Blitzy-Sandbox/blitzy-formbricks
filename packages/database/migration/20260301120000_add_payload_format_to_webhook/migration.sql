-- AlterTable
ALTER TABLE "public"."Webhook" ADD COLUMN "payloadFormat" TEXT DEFAULT 'default';

-- Rollback: ALTER TABLE "public"."Webhook" DROP COLUMN "payloadFormat";
