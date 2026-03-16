import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import toast from "react-hot-toast";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { PopoverEmbedTab } from "./popover-embed-tab";

// Mock react-i18next with a pass-through useTranslation hook that returns i18n keys as-is,
// allowing tests to verify i18n key rendering without actual translation files
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock CodeBlock to render children in a testable pre element so snippet content is queryable
vi.mock("@/modules/ui/components/code-block", () => ({
  CodeBlock: (props: { children: React.ReactNode }) => <pre data-testid="code-block">{props.children}</pre>,
}));

// Mock Button as a native button element preserving onClick handler and accessibility attributes
vi.mock("@/modules/ui/components/button", () => ({
  Button: (props: any) => (
    <button
      onClick={props.onClick}
      className={props.className}
      title={props.title}
      aria-label={props["aria-label"]}>
      {props.children}
    </button>
  ),
}));

// Mock lucide-react CopyIcon to avoid SVG rendering issues in the jsdom test environment
vi.mock("lucide-react", () => ({
  CopyIcon: () => <span data-testid="copy-icon" />,
}));

// Mock AdvancedOptionToggle to provide a simple toggle button that renders children
// when isChecked is true, matching the real component's conditional rendering behavior
vi.mock("@/modules/ui/components/advanced-option-toggle", () => ({
  AdvancedOptionToggle: (props: any) => (
    <div>
      <button data-testid="advanced-toggle" onClick={() => props.onToggle(!props.isChecked)}>
        {props.title}
      </button>
      <p>{props.description}</p>
      {props.isChecked && props.children}
    </div>
  ),
}));

describe("PopoverEmbedTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Setup navigator.clipboard.writeText mock for each test
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
      writable: true,
      configurable: true,
    });
  });

  // Explicitly clean up the DOM between tests to prevent element accumulation
  // (vitestSetup's vi.resetModules() can interfere with automatic RTL cleanup)
  afterEach(() => {
    cleanup();
  });

  test("renders with default props", () => {
    render(<PopoverEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Verify the code block is rendered with snippet content
    expect(screen.getByTestId("code-block")).toBeInTheDocument();

    // Verify the copy button is visible using the i18n key
    expect(screen.getByText("common.copy_code")).toBeVisible();
  });

  test('default button position is "bottom-right"', () => {
    render(<PopoverEmbedTab surveyUrl="https://example.com/s/test123" />);

    const codeBlock = screen.getByTestId("code-block");

    // The generated embed code snippet should contain the default position "bottom-right"
    expect(codeBlock.textContent).toContain("bottom-right");

    // The snippet should reference the surveyUrl origin
    expect(codeBlock.textContent).toContain("https://example.com");
  });

  test("position selection changes update the code snippet", () => {
    render(<PopoverEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Find the position selector (the <select> element) via its combobox role
    const positionSelect = screen.getByRole("combobox");

    // Change position from default "bottom-right" to "bottom-left"
    fireEvent.change(positionSelect, { target: { value: "bottom-left" } });

    // Verify the generated code snippet updates to reflect the new position
    const codeBlock = screen.getByTestId("code-block");
    expect(codeBlock.textContent).toContain("bottom-left");
  });

  test("color picker configuration changes update the code snippet", () => {
    render(<PopoverEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Find the color text input by its accessible name (aria-label)
    const colorTextInput = screen.getByRole("textbox", {
      name: "environments.surveys.share.popover_embed.button_color",
    });

    // Change the color from default "#00C4B8" to "#FF5733"
    fireEvent.change(colorTextInput, { target: { value: "#FF5733" } });

    // Verify the generated code snippet updates to include the new color value
    const codeBlock = screen.getByTestId("code-block");
    expect(codeBlock.textContent).toContain("#FF5733");
  });

  test("form dimension inputs via AdvancedOptionToggle", () => {
    render(<PopoverEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Toggle the advanced settings to reveal width/height inputs
    const toggleButton = screen.getByTestId("advanced-toggle");
    fireEvent.click(toggleButton);

    // Find the width input by its default display value (400)
    const widthInput = screen.getByDisplayValue("400");
    fireEvent.change(widthInput, { target: { value: "600" } });

    // Verify the code snippet updates with the new width
    const codeBlock = screen.getByTestId("code-block");
    expect(codeBlock.textContent).toContain("600");

    // Find the height input by its default display value (500)
    const heightInput = screen.getByDisplayValue("500");
    fireEvent.change(heightInput, { target: { value: "700" } });

    // Verify the code snippet updates with the new height
    expect(codeBlock.textContent).toContain("700");
  });

  test("copy-to-clipboard functionality triggers toast", async () => {
    render(<PopoverEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Find and click the copy button using the i18n key
    const copyButton = screen.getByText("common.copy_code");
    fireEvent.click(copyButton);

    // Verify navigator.clipboard.writeText was called with the snippet content
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalled();
    });

    // Verify the clipboard content includes the expected embed configuration keys
    const clipboardArg = (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(clipboardArg).toContain("formbricks");
    expect(clipboardArg).toContain("popover");

    // Verify toast.success was called with the correct i18n key
    expect(toast.success).toHaveBeenCalledWith(
      "environments.surveys.share.popover_embed.embed_code_copied_to_clipboard"
    );
  });

  test("i18n keys render correctly", () => {
    render(<PopoverEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Verify all expected i18n key strings are rendered in the component output
    // Since useTranslation is mocked to return keys as-is, these keys appear as visible text
    expect(screen.getByText("environments.surveys.share.popover_embed.button_position")).toBeInTheDocument();
    expect(screen.getByText("environments.surveys.share.popover_embed.button_color")).toBeInTheDocument();
    expect(screen.getByText("environments.surveys.share.popover_embed.form_dimensions")).toBeInTheDocument();
    expect(
      screen.getByText("environments.surveys.share.popover_embed.form_dimensions_description")
    ).toBeInTheDocument();
    expect(screen.getByText("common.copy_code")).toBeInTheDocument();
  });
});
