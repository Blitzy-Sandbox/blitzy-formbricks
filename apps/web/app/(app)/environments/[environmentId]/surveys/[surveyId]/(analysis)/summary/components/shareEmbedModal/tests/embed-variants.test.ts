/**
 * Embed Variant Integration Tests
 *
 * Tests the three new embed tab components (slider, popover, side tab)
 * created in Sprint 3 (Epic 3.2) to verify:
 *
 *  - Each component renders without errors
 *  - Generated embed code snippet contains the expected variant identifier
 *    ("slider", "popover", "sideTab" respectively)
 *  - Copy-to-clipboard button is present
 *
 * These tests complement the per-component unit tests in the parent
 * directory by providing cross-variant parity assertions in a single file.
 *
 * NOTE: This file uses React.createElement instead of JSX to maintain the
 * .test.ts extension as specified in the sprint requirements.
 *
 * @vitest-environment jsdom
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { PopoverEmbedTab } from "../popover-embed-tab";
import { SideTabEmbedTab } from "../side-tab-embed-tab";
// ---------------------------------------------------------------------------
// Import components under test
// ---------------------------------------------------------------------------

import { SliderEmbedTab } from "../slider-embed-tab";

// Shared mocks — all three components use the same UI primitives

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

vi.mock("react-hot-toast", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock("@/modules/ui/components/code-block", () => ({
  CodeBlock: ({ children }: { children: React.ReactNode }) =>
    React.createElement("pre", { "data-testid": "code-block" }, children),
}));

vi.mock("@/modules/ui/components/button", () => ({
  Button: ({
    children,
    onClick,
    ...rest
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    [key: string]: unknown;
  }) =>
    React.createElement(
      "button",
      { onClick, "aria-label": rest["aria-label"] as string | undefined },
      children
    ),
}));

vi.mock("@/modules/ui/components/advanced-option-toggle", () => ({
  AdvancedOptionToggle: ({
    isChecked,
    onToggle,
    title,
    children,
  }: {
    isChecked: boolean;
    onToggle: (v: boolean) => void;
    title: string;
    children?: React.ReactNode;
  }) =>
    React.createElement(
      "div",
      null,
      React.createElement("button", { onClick: () => onToggle(!isChecked) }, title),
      isChecked ? children : null
    ),
}));

vi.mock("lucide-react", () => ({
  CopyIcon: () => React.createElement("span", { "data-testid": "copy-icon" }),
}));

// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Test constants
// ---------------------------------------------------------------------------

const SURVEY_URL = "https://example.com/s/testsurvey123";
const ENV_ID = "clenvtest000000000000";

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("Embed Variants — cross-component parity tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Mock navigator.clipboard for copy button assertions
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    cleanup();
  });

  // =========================================================================
  // SliderEmbedTab
  // =========================================================================
  describe("SliderEmbedTab", () => {
    test("renders without errors", () => {
      expect(() =>
        render(React.createElement(SliderEmbedTab, { surveyUrl: SURVEY_URL, environmentId: ENV_ID }))
      ).not.toThrow();
    });

    test('generated embed code contains "slider" variant identifier', () => {
      render(React.createElement(SliderEmbedTab, { surveyUrl: SURVEY_URL, environmentId: ENV_ID }));
      const codeBlock = screen.getByTestId("code-block");
      expect(codeBlock.textContent).toContain("slider");
      expect(codeBlock.textContent).toContain('embedMode: "slider"');
    });

    test("copy-to-clipboard button is present", () => {
      render(React.createElement(SliderEmbedTab, { surveyUrl: SURVEY_URL, environmentId: ENV_ID }));
      const copyButton = screen.getByRole("button", { name: "common.copy_code" });
      expect(copyButton).toBeInTheDocument();
    });
  });

  // =========================================================================
  // PopoverEmbedTab
  // =========================================================================
  describe("PopoverEmbedTab", () => {
    test("renders without errors", () => {
      expect(() =>
        render(React.createElement(PopoverEmbedTab, { surveyUrl: SURVEY_URL, environmentId: ENV_ID }))
      ).not.toThrow();
    });

    test('generated embed code contains "popover" variant identifier', () => {
      render(React.createElement(PopoverEmbedTab, { surveyUrl: SURVEY_URL, environmentId: ENV_ID }));
      const codeBlock = screen.getByTestId("code-block");
      expect(codeBlock.textContent).toContain("popover");
      expect(codeBlock.textContent).toContain('embedMode: "popover"');
    });

    test("copy-to-clipboard button is present", () => {
      render(React.createElement(PopoverEmbedTab, { surveyUrl: SURVEY_URL, environmentId: ENV_ID }));
      const copyButton = screen.getByRole("button", { name: "common.copy_code" });
      expect(copyButton).toBeInTheDocument();
    });
  });

  // =========================================================================
  // SideTabEmbedTab
  // =========================================================================
  describe("SideTabEmbedTab", () => {
    test("renders without errors", () => {
      expect(() =>
        render(React.createElement(SideTabEmbedTab, { surveyUrl: SURVEY_URL, environmentId: ENV_ID }))
      ).not.toThrow();
    });

    test('generated embed code contains "sideTab" variant identifier (side-tab mode)', () => {
      render(React.createElement(SideTabEmbedTab, { surveyUrl: SURVEY_URL, environmentId: ENV_ID }));
      const codeBlock = screen.getByTestId("code-block");
      // The component uses "sideTab" as the embedMode value in the snippet
      expect(codeBlock.textContent).toContain("sideTab");
      expect(codeBlock.textContent).toContain('embedMode: "sideTab"');
    });

    test("copy-to-clipboard button is present", () => {
      render(React.createElement(SideTabEmbedTab, { surveyUrl: SURVEY_URL, environmentId: ENV_ID }));
      const copyButton = screen.getByRole("button", { name: "common.copy_code" });
      expect(copyButton).toBeInTheDocument();
    });
  });
});
