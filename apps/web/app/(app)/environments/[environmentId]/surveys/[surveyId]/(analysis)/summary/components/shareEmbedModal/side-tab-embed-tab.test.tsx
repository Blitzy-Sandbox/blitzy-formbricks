import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import toast from "react-hot-toast";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { SideTabEmbedTab } from "./side-tab-embed-tab";

// Mock react-hot-toast to provide spy functions for toast.success/error assertions
vi.mock("react-hot-toast", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

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

describe("SideTabEmbedTab", () => {
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
    render(<SideTabEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Verify the code block is rendered with snippet content
    expect(screen.getByTestId("code-block")).toBeInTheDocument();

    // Verify the copy button is visible using the i18n key
    expect(screen.getByText("common.copy_code")).toBeVisible();
  });

  test('default tab label is "Feedback"', () => {
    render(<SideTabEmbedTab surveyUrl="https://example.com/s/test123" />);

    const codeBlock = screen.getByTestId("code-block");

    // The generated embed snippet should contain the default tab label value "Feedback"
    expect(codeBlock.textContent).toContain("Feedback");

    // The snippet should reference the surveyUrl origin
    expect(codeBlock.textContent).toContain("https://example.com");
  });

  test("tab label input changes update the code snippet", () => {
    render(<SideTabEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Find the tab label text input which has default value "Feedback"
    const tabLabelInput = screen.getByDisplayValue("Feedback");

    // Change the tab label to "Survey"
    fireEvent.change(tabLabelInput, { target: { value: "Survey" } });

    // Verify the generated code snippet updates to include the new label value
    const codeBlock = screen.getByTestId("code-block");
    expect(codeBlock.textContent).toContain("Survey");
  });

  test("position selection changes update the code snippet", () => {
    render(<SideTabEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Verify the default position is "right"
    const rightRadio = screen.getByLabelText("environments.surveys.share.side_tab_embed.position_right");
    expect(rightRadio).toBeChecked();

    // Select the "left" position option
    const leftRadio = screen.getByLabelText("environments.surveys.share.side_tab_embed.position_left");
    fireEvent.click(leftRadio);

    // Verify the generated code snippet updates to include position "left"
    const codeBlock = screen.getByTestId("code-block");
    expect(codeBlock.textContent).toContain('"left"');
  });

  test("color picker configuration changes update the code snippet", () => {
    render(<SideTabEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Find the color text input by its accessible name (aria-label)
    const colorTextInput = screen.getByRole("textbox", {
      name: "environments.surveys.share.side_tab_embed.tab_color",
    });

    // Change the color from default "#00C4B8" to "#FF5733"
    fireEvent.change(colorTextInput, { target: { value: "#FF5733" } });

    // Verify the generated code snippet updates to include the new color value
    const codeBlock = screen.getByTestId("code-block");
    expect(codeBlock.textContent).toContain("#FF5733");
  });

  test("copy-to-clipboard functionality triggers toast", async () => {
    render(<SideTabEmbedTab surveyUrl="https://example.com/s/test123" />);

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
    expect(clipboardArg).toContain("sideTab");

    // Verify toast.success was called with the correct i18n key
    expect(toast.success).toHaveBeenCalledWith(
      "environments.surveys.share.side_tab_embed.embed_code_copied_to_clipboard"
    );
  });

  test("i18n keys render correctly", () => {
    render(<SideTabEmbedTab surveyUrl="https://example.com/s/test123" />);

    // Verify all expected i18n key strings are rendered in the component output
    // Since useTranslation is mocked to return keys as-is, these keys appear as visible text
    expect(screen.getByText("environments.surveys.share.side_tab_embed.tab_label")).toBeInTheDocument();
    expect(screen.getByText("environments.surveys.share.side_tab_embed.position")).toBeInTheDocument();
    expect(screen.getByText("environments.surveys.share.side_tab_embed.position_left")).toBeInTheDocument();
    expect(screen.getByText("environments.surveys.share.side_tab_embed.position_right")).toBeInTheDocument();
    expect(screen.getByText("environments.surveys.share.side_tab_embed.tab_color")).toBeInTheDocument();
    expect(screen.getByText("common.copy_code")).toBeInTheDocument();
  });
});
