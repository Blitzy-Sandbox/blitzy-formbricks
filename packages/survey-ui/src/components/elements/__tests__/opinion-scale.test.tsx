// @vitest-environment jsdom
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { OpinionScale } from "../opinion-scale";

// ---------------------------------------------------------------------------
// Shared default props — `onChange` is cleared before every test
// ---------------------------------------------------------------------------

const defaultProps = {
  elementId: "test-opinion-scale",
  headline: "How do you feel about this?",
  inputId: "test-opinion-scale-input",
  scaleRange: 5 as const,
  visualStyle: "number" as const,
  onChange: vi.fn(),
};

// ===========================================================================
// OpinionScale component tests
// ===========================================================================

describe("OpinionScale", () => {
  beforeEach(() => {
    defaultProps.onChange.mockClear();
  });

  // -------------------------------------------------------------------------
  // Rendering tests
  // -------------------------------------------------------------------------

  test("renders with default 5-point number scale", () => {
    render(<OpinionScale {...defaultProps} />);
    expect(screen.getByText("How do you feel about this?")).toBeInTheDocument();
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(5);
  });

  test("renders with 7-point scale", () => {
    render(<OpinionScale {...defaultProps} scaleRange={7} />);
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(7);
  });

  test("renders with 10-point scale", () => {
    render(<OpinionScale {...defaultProps} scaleRange={10} />);
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(10);
  });

  test("renders headline text", () => {
    render(<OpinionScale {...defaultProps} headline="Rate your experience" />);
    expect(screen.getByText("Rate your experience")).toBeInTheDocument();
  });

  test("renders description when provided", () => {
    render(<OpinionScale {...defaultProps} description="Please select a value" />);
    expect(screen.getByText("Please select a value")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Visual style tests
  // -------------------------------------------------------------------------

  test("renders number visual style", () => {
    render(<OpinionScale {...defaultProps} visualStyle="number" />);
    for (let i = 1; i <= 5; i++) {
      expect(screen.getByText(String(i))).toBeInTheDocument();
    }
  });

  test("renders star visual style", () => {
    const { container } = render(<OpinionScale {...defaultProps} visualStyle="star" />);
    // Star visual style renders SVG elements from lucide-react Star icon
    const svgs = container.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThanOrEqual(5);
    // Should still have 5 radio inputs
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(5);
  });

  test("renders smiley visual style", () => {
    const { container } = render(<OpinionScale {...defaultProps} visualStyle="smiley" />);
    // Smiley visual style renders SVG smiley face elements
    const svgs = container.querySelectorAll("svg");
    expect(svgs.length).toBeGreaterThanOrEqual(5);
    // Should still have 5 radio inputs
    const radios = screen.getAllByRole("radio");
    expect(radios).toHaveLength(5);
  });

  // -------------------------------------------------------------------------
  // Value selection tests
  // -------------------------------------------------------------------------

  test("calls onChange when a value is selected", () => {
    render(<OpinionScale {...defaultProps} />);
    const radio = screen.getByRole("radio", { name: "Select 3 out of 5" });
    fireEvent.click(radio);
    expect(defaultProps.onChange).toHaveBeenCalledWith(3);
  });

  test("calls onChange with correct value for each option", () => {
    render(<OpinionScale {...defaultProps} />);
    const radio = screen.getByRole("radio", { name: "Select 5 out of 5" });
    fireEvent.click(radio);
    expect(defaultProps.onChange).toHaveBeenCalledWith(5);
  });

  test("highlights selected value", () => {
    render(<OpinionScale {...defaultProps} value={3} />);
    const radio = screen.getByRole("radio", { name: "Select 3 out of 5" });
    expect(radio).toBeChecked();
  });

  // -------------------------------------------------------------------------
  // Keyboard navigation tests
  // -------------------------------------------------------------------------

  test("supports keyboard Enter to select", () => {
    render(<OpinionScale {...defaultProps} />);
    // Fire keyDown on the label containing "3" (event bubbles to label's onKeyDown)
    fireEvent.keyDown(screen.getByText("3"), { key: "Enter" });
    expect(defaultProps.onChange).toHaveBeenCalledWith(3);
  });

  test("supports keyboard Space to select", () => {
    render(<OpinionScale {...defaultProps} />);
    fireEvent.keyDown(screen.getByText("3"), { key: " " });
    expect(defaultProps.onChange).toHaveBeenCalledWith(3);
  });

  test("supports ArrowRight keyboard navigation", () => {
    render(<OpinionScale {...defaultProps} value={2} />);
    // ArrowRight on any label computes newValue from currentValue + 1
    fireEvent.keyDown(screen.getByText("2"), { key: "ArrowRight" });
    expect(defaultProps.onChange).toHaveBeenCalledWith(3);
  });

  test("supports ArrowLeft keyboard navigation", () => {
    render(<OpinionScale {...defaultProps} value={3} />);
    // ArrowLeft on any label computes newValue from currentValue - 1
    fireEvent.keyDown(screen.getByText("3"), { key: "ArrowLeft" });
    expect(defaultProps.onChange).toHaveBeenCalledWith(2);
  });

  test("does not navigate below 1 with ArrowLeft", () => {
    render(<OpinionScale {...defaultProps} value={1} />);
    // At the minimum boundary (1), ArrowLeft should clamp to 1
    fireEvent.keyDown(screen.getByText("1"), { key: "ArrowLeft" });
    expect(defaultProps.onChange).toHaveBeenCalledWith(1);
  });

  test("does not navigate above scaleRange with ArrowRight", () => {
    render(<OpinionScale {...defaultProps} value={5} scaleRange={5} />);
    // At the maximum boundary (scaleRange), ArrowRight should clamp to scaleRange
    fireEvent.keyDown(screen.getByText("5"), { key: "ArrowRight" });
    expect(defaultProps.onChange).toHaveBeenCalledWith(5);
  });

  // -------------------------------------------------------------------------
  // Disabled state tests
  // -------------------------------------------------------------------------

  test("does not call onChange when disabled", () => {
    render(<OpinionScale {...defaultProps} disabled={true} />);
    // Click the label text — handleSelect checks `if (!disabled)` and returns
    fireEvent.click(screen.getByText("3"));
    expect(defaultProps.onChange).not.toHaveBeenCalled();
  });

  test("does not respond to keyboard when disabled", () => {
    render(<OpinionScale {...defaultProps} disabled={true} />);
    // Keyboard handler returns early when disabled
    fireEvent.keyDown(screen.getByText("3"), { key: "Enter" });
    expect(defaultProps.onChange).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Color coding tests
  // -------------------------------------------------------------------------

  test("renders without color coding by default", () => {
    const { container } = render(<OpinionScale {...defaultProps} />);
    // Without isColorCodingEnabled, no color-coded indicator bars should be present
    expect(container.innerHTML).not.toContain("bg-rose-100");
    expect(container.innerHTML).not.toContain("bg-orange-100");
    expect(container.innerHTML).not.toContain("bg-emerald-100");
  });

  test("renders with color coding when enabled", () => {
    const { container } = render(
      <OpinionScale {...defaultProps} isColorCodingEnabled={true} visualStyle="number" />
    );
    // When color coding is enabled, at least one color indicator class should be present
    const hasColorBars =
      container.innerHTML.includes("bg-rose-100") ||
      container.innerHTML.includes("bg-orange-100") ||
      container.innerHTML.includes("bg-emerald-100");
    expect(hasColorBars).toBe(true);
  });

  // -------------------------------------------------------------------------
  // Label tests
  // -------------------------------------------------------------------------

  test("renders lower and upper labels", () => {
    render(<OpinionScale {...defaultProps} lowerLabel="Strongly disagree" upperLabel="Strongly agree" />);
    expect(screen.getByText("Strongly disagree")).toBeInTheDocument();
    expect(screen.getByText("Strongly agree")).toBeInTheDocument();
  });

  test("does not render labels section when neither label is provided", () => {
    render(<OpinionScale {...defaultProps} />);
    // Without lowerLabel or upperLabel, no label text should appear (aside from headline)
    expect(screen.queryByText("Strongly disagree")).toBeNull();
    expect(screen.queryByText("Strongly agree")).toBeNull();
  });

  test("renders only lower label when upper is not provided", () => {
    render(<OpinionScale {...defaultProps} lowerLabel="Not at all" />);
    expect(screen.getByText("Not at all")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Error message tests
  // -------------------------------------------------------------------------

  test("renders error message when provided", () => {
    render(<OpinionScale {...defaultProps} errorMessage="Please select a value" />);
    expect(screen.getByText("Please select a value")).toBeInTheDocument();
  });

  test("does not render error when no error message", () => {
    render(<OpinionScale {...defaultProps} />);
    expect(screen.queryByText("Please select a value")).toBeNull();
  });

  // -------------------------------------------------------------------------
  // RTL support
  // -------------------------------------------------------------------------

  test("applies RTL direction when dir is rtl", () => {
    const { container } = render(<OpinionScale {...defaultProps} dir="rtl" />);
    const rootDiv = container.firstChild as HTMLElement;
    expect(rootDiv).toHaveAttribute("dir", "rtl");
  });

  // -------------------------------------------------------------------------
  // Required indicator
  // -------------------------------------------------------------------------

  test("shows required indicator when required is true", () => {
    render(<OpinionScale {...defaultProps} required={true} />);
    // ElementHeader renders the default requiredLabel "Required" when required is true
    expect(screen.getByText("Required")).toBeInTheDocument();
  });
});
