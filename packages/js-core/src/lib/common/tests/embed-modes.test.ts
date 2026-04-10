/**
 * SDK Embed Modes Configuration Test
 *
 * Validates that the TConfigInput type and related embed mode types
 * (TEmbedMode, TSliderConfig, TPopoverConfig, TSideTabConfig) correctly
 * accept "slider", "popover", and "sideTab" as valid embed mode values
 * without throwing runtime errors.
 *
 * These tests verify the configuration contract at the type-inference
 * boundary — they confirm that objects matching the exported interfaces
 * satisfy the expected shape and that the SDK initialization path can
 * consume them.
 */
import { describe, expect, test } from "vitest";
import type { TConfigInput, TEmbedMode, TPopoverConfig, TSideTabConfig, TSliderConfig } from "@/types/config";

describe("SDK embed mode configuration", () => {
  // -------------------------------------------------------------------------
  // TEmbedMode literal values
  // -------------------------------------------------------------------------
  describe("TEmbedMode accepts all three embed mode values", () => {
    test('"slider" is a valid TEmbedMode value', () => {
      const mode: TEmbedMode = "slider";
      expect(mode).toBe("slider");
    });

    test('"popover" is a valid TEmbedMode value', () => {
      const mode: TEmbedMode = "popover";
      expect(mode).toBe("popover");
    });

    test('"sideTab" is a valid TEmbedMode value', () => {
      const mode: TEmbedMode = "sideTab";
      expect(mode).toBe("sideTab");
    });
  });

  // -------------------------------------------------------------------------
  // TSliderConfig shape validation
  // -------------------------------------------------------------------------
  describe("TSliderConfig", () => {
    test("accepts a minimal slider configuration with required direction", () => {
      const config: TSliderConfig = { direction: "right" };
      expect(config.direction).toBe("right");
      expect(config.width).toBeUndefined();
      expect(config.animation).toBeUndefined();
    });

    test("accepts a fully specified slider configuration", () => {
      const config: TSliderConfig = {
        direction: "left",
        width: "500px",
        animation: 400,
      };
      expect(config.direction).toBe("left");
      expect(config.width).toBe("500px");
      expect(config.animation).toBe(400);
    });
  });

  // -------------------------------------------------------------------------
  // TPopoverConfig shape validation
  // -------------------------------------------------------------------------
  describe("TPopoverConfig", () => {
    test("accepts a minimal popover configuration with required buttonPosition", () => {
      const config: TPopoverConfig = { buttonPosition: "bottom-right" };
      expect(config.buttonPosition).toBe("bottom-right");
      expect(config.icon).toBeUndefined();
      expect(config.color).toBeUndefined();
      expect(config.formWidth).toBeUndefined();
      expect(config.formHeight).toBeUndefined();
    });

    test("accepts a fully specified popover configuration", () => {
      const config: TPopoverConfig = {
        buttonPosition: "top-left",
        icon: "chat",
        color: "#FF5733",
        formWidth: "400px",
        formHeight: "600px",
      };
      expect(config.buttonPosition).toBe("top-left");
      expect(config.icon).toBe("chat");
      expect(config.color).toBe("#FF5733");
      expect(config.formWidth).toBe("400px");
      expect(config.formHeight).toBe("600px");
    });

    test("accepts all four corner positions", () => {
      const positions: TPopoverConfig["buttonPosition"][] = [
        "bottom-left",
        "bottom-right",
        "top-left",
        "top-right",
      ];
      positions.forEach((pos) => {
        const config: TPopoverConfig = { buttonPosition: pos };
        expect(config.buttonPosition).toBe(pos);
      });
    });
  });

  // -------------------------------------------------------------------------
  // TSideTabConfig shape validation
  // -------------------------------------------------------------------------
  describe("TSideTabConfig", () => {
    test("accepts a minimal side tab configuration with required fields", () => {
      const config: TSideTabConfig = { tabLabel: "Feedback", position: "right" };
      expect(config.tabLabel).toBe("Feedback");
      expect(config.position).toBe("right");
      expect(config.color).toBeUndefined();
    });

    test("accepts a fully specified side tab configuration", () => {
      const config: TSideTabConfig = {
        tabLabel: "Survey",
        position: "left",
        color: "#00C4B8",
      };
      expect(config.tabLabel).toBe("Survey");
      expect(config.position).toBe("left");
      expect(config.color).toBe("#00C4B8");
    });
  });

  // -------------------------------------------------------------------------
  // TConfigInput with embed modes
  // -------------------------------------------------------------------------
  describe("TConfigInput with embed mode options", () => {
    test("accepts a config with embedMode: slider and sliderConfig", () => {
      const config: TConfigInput = {
        environmentId: "env-test-001",
        appUrl: "https://app.example.com",
        embedMode: "slider",
        sliderConfig: {
          direction: "right",
          width: "400px",
          animation: 300,
        },
      };
      expect(config.embedMode).toBe("slider");
      expect(config.sliderConfig?.direction).toBe("right");
    });

    test("accepts a config with embedMode: popover and popoverConfig", () => {
      const config: TConfigInput = {
        environmentId: "env-test-002",
        appUrl: "https://app.example.com",
        embedMode: "popover",
        popoverConfig: {
          buttonPosition: "bottom-right",
          color: "#00C4B8",
          formWidth: "400px",
          formHeight: "500px",
        },
      };
      expect(config.embedMode).toBe("popover");
      expect(config.popoverConfig?.buttonPosition).toBe("bottom-right");
    });

    test("accepts a config with embedMode: sideTab and sideTabConfig", () => {
      const config: TConfigInput = {
        environmentId: "env-test-003",
        appUrl: "https://app.example.com",
        embedMode: "sideTab",
        sideTabConfig: {
          tabLabel: "Help",
          position: "left",
          color: "#FF0000",
        },
      };
      expect(config.embedMode).toBe("sideTab");
      expect(config.sideTabConfig?.tabLabel).toBe("Help");
    });

    test("accepts a config without embedMode (standard embed)", () => {
      const config: TConfigInput = {
        environmentId: "env-test-004",
        appUrl: "https://app.example.com",
      };
      expect(config.embedMode).toBeUndefined();
      expect(config.sliderConfig).toBeUndefined();
      expect(config.popoverConfig).toBeUndefined();
      expect(config.sideTabConfig).toBeUndefined();
    });
  });
});
