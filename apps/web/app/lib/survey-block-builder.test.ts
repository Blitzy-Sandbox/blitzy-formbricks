import type { TFunction } from "i18next";
import { describe, expect, test, vi } from "vitest";
import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/elements";
import { createI18nString } from "@/lib/i18n/utils";
import { buildBlock, buildOpinionScaleElement, buildPaymentElement } from "./survey-block-builder";

const mockT = vi.fn((key: string) => {
  const translations: Record<string, string> = {
    "common.next": "Next",
    "common.back": "Back",
    "": "",
  };
  return translations[key] || key;
}) as unknown as TFunction;

describe("survey-block-builder", () => {
  describe("buildBlock", () => {
    const mockElements = [
      {
        id: "element-1",
        type: TSurveyElementTypeEnum.OpenText,
        headline: createI18nString("Test Question", []),
        required: false,
        inputType: "text",
        longAnswer: false,
        charLimit: { enabled: false },
      },
    ];

    test("should use getDefaultButtonLabel when buttonLabel is provided", () => {
      const result = buildBlock({
        name: "Test Block",
        elements: mockElements,
        buttonLabel: "Custom Next",
        t: mockT,
      });

      expect(result.buttonLabel).toEqual({
        default: "Custom Next",
      });
    });

    test("should use createI18nString with empty translation when buttonLabel is not provided", () => {
      const result = buildBlock({
        name: "Test Block",
        elements: mockElements,
        t: mockT,
      });

      expect(result.buttonLabel).toEqual({
        default: "",
      });
    });

    test("should use getDefaultBackButtonLabel when backButtonLabel is provided", () => {
      const result = buildBlock({
        name: "Test Block",
        elements: mockElements,
        backButtonLabel: "Custom Back",
        t: mockT,
      });

      expect(result.backButtonLabel).toEqual({
        default: "Custom Back",
      });
    });

    test("should use createI18nString with empty translation when backButtonLabel is not provided", () => {
      const result = buildBlock({
        name: "Test Block",
        elements: mockElements,
        t: mockT,
      });

      expect(result.backButtonLabel).toEqual({
        default: "",
      });
    });
  });

  describe("buildOpinionScaleElement", () => {
    test("should create an opinion scale element with default values", () => {
      const result = buildOpinionScaleElement({
        headline: "How satisfied are you?",
        scaleRange: 5,
        visualStyle: "number",
      });

      expect(result.type).toBe(TSurveyElementTypeEnum.OpinionScale);
      expect(result.headline).toEqual(createI18nString("How satisfied are you?", []));
      expect(result.scaleRange).toBe(5);
      expect(result.visualStyle).toBe("number");
      expect(result.required).toBe(false);
      expect(result.isColorCodingEnabled).toBe(false);
      expect(result.id).toBeDefined();
      expect(result.lowerLabel).toBeUndefined();
      expect(result.upperLabel).toBeUndefined();
      expect(result.subheader).toBeUndefined();
    });

    test("should create an opinion scale element with all fields provided", () => {
      const result = buildOpinionScaleElement({
        id: "custom-id",
        headline: "Rate your experience",
        subheader: "Please select a number",
        scaleRange: 10,
        lowerLabel: "Not at all",
        upperLabel: "Extremely",
        visualStyle: "star",
        isColorCodingEnabled: true,
        required: true,
      });

      expect(result.id).toBe("custom-id");
      expect(result.subheader).toEqual(createI18nString("Please select a number", []));
      expect(result.scaleRange).toBe(10);
      expect(result.lowerLabel).toEqual(createI18nString("Not at all", []));
      expect(result.upperLabel).toEqual(createI18nString("Extremely", []));
      expect(result.visualStyle).toBe("star");
      expect(result.isColorCodingEnabled).toBe(true);
      expect(result.required).toBe(true);
    });

    test("should correctly wrap labels with i18n strings", () => {
      const result = buildOpinionScaleElement({
        headline: "Test",
        scaleRange: 7,
        visualStyle: "smiley",
        lowerLabel: "Low",
        upperLabel: "High",
      });

      expect(result.lowerLabel).toEqual(createI18nString("Low", []));
      expect(result.upperLabel).toEqual(createI18nString("High", []));
    });

    test("should generate an id when not provided", () => {
      const result = buildOpinionScaleElement({
        headline: "Test",
        scaleRange: 5,
        visualStyle: "number",
      });

      expect(result.id).toBeTruthy();
      expect(typeof result.id).toBe("string");
    });

    test("should preserve provided id", () => {
      const result = buildOpinionScaleElement({
        id: "my-custom-id",
        headline: "Test",
        scaleRange: 5,
        visualStyle: "number",
      });

      expect(result.id).toBe("my-custom-id");
    });
  });

  describe("buildPaymentElement", () => {
    test("should create a payment element with default values", () => {
      const result = buildPaymentElement({
        headline: "Complete your payment",
        currency: "usd",
        amount: 1000,
        stripeIntegration: { publicKey: "pk_test_123", priceId: "price_123" },
      });

      expect(result.type).toBe(TSurveyElementTypeEnum.Payment);
      expect(result.headline).toEqual(createI18nString("Complete your payment", []));
      expect(result.currency).toBe("usd");
      expect(result.amount).toBe(1000);
      expect(result.required).toBe(false);
      expect(result.id).toBeDefined();
      expect(result.buttonLabel).toBeUndefined();
      expect(result.subheader).toBeUndefined();
      expect(result.stripeIntegration.publicKey).toBe("pk_test_123");
      expect(result.stripeIntegration.priceId).toBe("price_123");
    });

    test("should create a payment element with all fields provided", () => {
      const result = buildPaymentElement({
        id: "pay-id",
        headline: "Pay now",
        subheader: "Secure payment",
        currency: "eur",
        amount: 2500,
        buttonLabel: "Pay €25.00",
        stripeIntegration: { publicKey: "pk_test_456", priceId: "price_456" },
        required: true,
      });

      expect(result.id).toBe("pay-id");
      expect(result.subheader).toEqual(createI18nString("Secure payment", []));
      expect(result.currency).toBe("eur");
      expect(result.amount).toBe(2500);
      expect(result.buttonLabel).toEqual(createI18nString("Pay €25.00", []));
      expect(result.required).toBe(true);
    });

    test("should generate an id when not provided", () => {
      const result = buildPaymentElement({
        headline: "Test",
        currency: "gbp",
        amount: 500,
        stripeIntegration: { publicKey: "pk_test_789", priceId: "price_789" },
      });

      expect(result.id).toBeTruthy();
    });

    test("should preserve provided id", () => {
      const result = buildPaymentElement({
        id: "my-pay-id",
        headline: "Test",
        currency: "usd",
        amount: 100,
        stripeIntegration: { publicKey: "pk_test_000", priceId: "price_000" },
      });

      expect(result.id).toBe("my-pay-id");
    });
  });
});
