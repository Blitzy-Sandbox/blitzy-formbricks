import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import toast from "react-hot-toast";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { SliderEmbedTab } from "./slider-embed-tab";

// Mock react-i18next locally — not globally mocked in vitestSetup.ts.
// Returns a pass-through function so i18n keys render as literal strings in the DOM.
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

// Mock internal UI components with minimal implementations to keep tests
// focused on SliderEmbedTab logic rather than child component internals.

vi.mock("@/modules/ui/components/code-block", () => ({
  CodeBlock: ({ children }: { children: React.ReactNode }) => (
    <code data-testid="code-block">{children}</code>
  ),
}));

vi.mock("@/modules/ui/components/button", () => ({
  Button: ({
    children,
    onClick,
    ...props
  }: {
    children: React.ReactNode;
    onClick?: () => void;
    [key: string]: unknown;
  }) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

vi.mock("@/modules/ui/components/advanced-option-toggle", () => ({
  AdvancedOptionToggle: ({
    isChecked,
    onToggle,
    title,
    description,
    children,
    htmlId,
  }: {
    isChecked: boolean;
    onToggle: (value: boolean) => void;
    title: string;
    description?: string;
    children?: React.ReactNode;
    htmlId: string;
    customContainerClass?: string;
  }) => (
    <div>
      <label>
        <input
          type="checkbox"
          checked={isChecked}
          onChange={() => onToggle(!isChecked)}
          data-testid={htmlId}
        />
        {title}
      </label>
      {description && <span>{description}</span>}
      {isChecked && children}
    </div>
  ),
}));

vi.mock("lucide-react", () => ({
  CopyIcon: () => <span data-testid="copy-icon" />,
}));

// ---------------------------------------------------------------------------
// Test constants
// ---------------------------------------------------------------------------

const TEST_SURVEY_URL = "https://example.com/s/test123";
const TEST_ENV_ID = "env-test-123";

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("SliderEmbedTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Mock navigator.clipboard.writeText before each test
    Object.defineProperty(navigator, "clipboard", {
      value: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
      writable: true,
      configurable: true,
    });
  });

  // Explicit cleanup is required because the global vitestSetup calls
  // vi.resetModules() in its beforeEach, which can break the automatic
  // cleanup registration from @testing-library/react.
  afterEach(() => {
    cleanup();
  });

  // -------------------------------------------------------------------------
  // Test 1: Renders with default props
  // -------------------------------------------------------------------------
  test("renders with default props", () => {
    render(<SliderEmbedTab surveyUrl={TEST_SURVEY_URL} environmentId={TEST_ENV_ID} />);

    // The code block should be present in the document
    const codeBlock = screen.getByTestId("code-block");
    expect(codeBlock).toBeInTheDocument();

    // The copy button should be visible (identified by i18n key)
    const copyButton = screen.getByRole("button", { name: "common.copy_code" });
    expect(copyButton).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // Test 2: Default direction is "right"
  // -------------------------------------------------------------------------
  test('default direction is "right"', () => {
    render(<SliderEmbedTab surveyUrl={TEST_SURVEY_URL} environmentId={TEST_ENV_ID} />);

    const codeBlock = screen.getByTestId("code-block");
    const snippetContent = codeBlock.textContent ?? "";

    // The default direction should be "right"
    expect(snippetContent).toContain('direction: "right"');

    // The apiHost (origin of surveyUrl) should be in the snippet
    expect(snippetContent).toContain("https://example.com");

    // The environmentId should be in the snippet
    expect(snippetContent).toContain(TEST_ENV_ID);
  });

  // -------------------------------------------------------------------------
  // Test 3: Direction selection changes to "left"
  // -------------------------------------------------------------------------
  test('direction selection changes to "left"', () => {
    render(<SliderEmbedTab surveyUrl={TEST_SURVEY_URL} environmentId={TEST_ENV_ID} />);

    // Find the "left" radio button (first radio in DOM order) and click it
    const radios = screen.getAllByRole("radio");
    const leftRadio = radios[0]; // "left" appears first in the component
    fireEvent.click(leftRadio);

    // Verify the generated code snippet updated to "left"
    const codeBlock = screen.getByTestId("code-block");
    expect(codeBlock.textContent).toContain('direction: "left"');
  });

  // -------------------------------------------------------------------------
  // Test 4: Width configuration updates
  // -------------------------------------------------------------------------
  test("width configuration updates", () => {
    render(<SliderEmbedTab surveyUrl={TEST_SURVEY_URL} environmentId={TEST_ENV_ID} />);

    const codeBlock = screen.getByTestId("code-block");

    // Default width of 400 should be present in the generated snippet
    expect(codeBlock.textContent).toContain('"400px"');

    // Find the width input (the only spinbutton visible when advanced options are hidden)
    const widthInput = screen.getByRole("spinbutton");
    fireEvent.change(widthInput, { target: { value: "500" } });

    // Verify the snippet updated to reflect the new width
    expect(codeBlock.textContent).toContain('"500px"');
  });

  // -------------------------------------------------------------------------
  // Test 5: Animation timing configuration
  // -------------------------------------------------------------------------
  test("animation timing configuration", () => {
    render(<SliderEmbedTab surveyUrl={TEST_SURVEY_URL} environmentId={TEST_ENV_ID} />);

    // Default snippet should have animation: 300
    const codeBlock = screen.getByTestId("code-block");
    expect(codeBlock.textContent).toContain("animation: 300");

    // Toggle the AdvancedOptionToggle to reveal animation settings
    const advancedToggle = screen.getByTestId("sliderAnimationDuration");
    fireEvent.click(advancedToggle);

    // Find the animation duration input via its associated label
    const animationInput = screen.getByLabelText(
      "environments.surveys.share.slider_embed.animation_duration"
    );
    fireEvent.change(animationInput, { target: { value: "500" } });

    // Verify the snippet reflects the new animation duration
    expect(codeBlock.textContent).toContain("animation: 500");
  });

  // -------------------------------------------------------------------------
  // Test 6: Copy-to-clipboard functionality triggers toast
  // -------------------------------------------------------------------------
  test("copy-to-clipboard functionality triggers toast", () => {
    render(<SliderEmbedTab surveyUrl={TEST_SURVEY_URL} environmentId={TEST_ENV_ID} />);

    // Find and click the copy button
    const copyButton = screen.getByRole("button", { name: "common.copy_code" });
    fireEvent.click(copyButton);

    // Verify clipboard.writeText was called with the snippet content
    expect(navigator.clipboard.writeText).toHaveBeenCalledTimes(1);
    const clipboardArg = (navigator.clipboard.writeText as ReturnType<typeof vi.fn>).mock.calls[0][0];
    expect(clipboardArg).toContain('embedMode: "slider"');
    expect(clipboardArg).toContain('direction: "right"');
    expect(clipboardArg).toContain(TEST_ENV_ID);

    // Verify toast.success was called with the correct i18n key
    expect(toast.success).toHaveBeenCalledWith(
      "environments.surveys.share.slider_embed.embed_code_copied_to_clipboard"
    );
  });

  // -------------------------------------------------------------------------
  // Test 7: i18n keys render correctly
  // -------------------------------------------------------------------------
  test("i18n keys render correctly", () => {
    render(<SliderEmbedTab surveyUrl={TEST_SURVEY_URL} environmentId={TEST_ENV_ID} />);

    // Direction section — label and both option labels
    expect(screen.getByText("environments.surveys.share.slider_embed.direction")).toBeInTheDocument();
    expect(screen.getByText("environments.surveys.share.slider_embed.direction_left")).toBeInTheDocument();
    expect(screen.getByText("environments.surveys.share.slider_embed.direction_right")).toBeInTheDocument();

    // Width label
    expect(screen.getByText("environments.surveys.share.slider_embed.width")).toBeInTheDocument();

    // Animation settings toggle title
    expect(
      screen.getByText("environments.surveys.share.slider_embed.animation_settings")
    ).toBeInTheDocument();

    // Animation settings description
    expect(
      screen.getByText("environments.surveys.share.slider_embed.animation_settings_description")
    ).toBeInTheDocument();

    // Copy button text
    expect(screen.getByText("common.copy_code")).toBeInTheDocument();
  });
});
