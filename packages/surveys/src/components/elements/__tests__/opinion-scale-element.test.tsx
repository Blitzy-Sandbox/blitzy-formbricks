// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, test, vi } from "vitest";
import type { TResponseTtc } from "@formbricks/types/responses";
import { OpinionScaleElement } from "../opinion-scale-element";

// ---------------------------------------------------------------------------
// Mock @formbricks/survey-ui — OpinionScale presentational component.
// The mock renders clickable buttons from 1..scaleRange so tests can simulate
// user interactions and verify that onChange fires with correct numeric values.
// It also exposes headline, scaleRange, and elementId as data-testid elements
// for rendering assertions.
// ---------------------------------------------------------------------------

vi.mock("@formbricks/survey-ui", () => ({
  OpinionScale: vi.fn(
    ({
      onChange,
      value,
      scaleRange,
      elementId,
      headline,
      description,
      lowerLabel,
      upperLabel,
      isColorCodingEnabled,
      visualStyle,
      required,
      requiredLabel,
      dir,
      errorMessage,
    }: {
      onChange: (val: number) => void;
      value?: number;
      scaleRange: number;
      elementId: string;
      headline: string;
      description?: string;
      lowerLabel?: string;
      upperLabel?: string;
      isColorCodingEnabled?: boolean;
      visualStyle?: string;
      required?: boolean;
      requiredLabel?: string;
      dir?: string;
      errorMessage?: string;
    }) => (
      <div data-testid={`opinion-scale-${elementId}`}>
        <span data-testid="headline">{headline}</span>
        <span data-testid="scale-range">{scaleRange}</span>
        {description && <span data-testid="description">{description}</span>}
        {lowerLabel && <span data-testid="lower-label">{lowerLabel}</span>}
        {upperLabel && <span data-testid="upper-label">{upperLabel}</span>}
        {visualStyle && <span data-testid="visual-style">{visualStyle}</span>}
        {isColorCodingEnabled && <span data-testid="color-coding">enabled</span>}
        {required && <span data-testid="required">{requiredLabel}</span>}
        {dir && <span data-testid="dir">{dir}</span>}
        {errorMessage && <span data-testid="error-message">{errorMessage}</span>}
        {Array.from({ length: scaleRange }, (_, i) => i + 1).map((num) => (
          <button
            key={num}
            data-testid={`scale-option-${num}`}
            onClick={() => onChange(num)}
            aria-pressed={value === num}>
            {num}
          </button>
        ))}
      </div>
    )
  ),
}));

// ---------------------------------------------------------------------------
// Mock TTC tracking utilities — getUpdatedTtc computes a new TTC record and
// useTtc sets up the tracking hook. These mocks are declared at module scope
// so individual tests can inspect call arguments.
// ---------------------------------------------------------------------------

const mockGetUpdatedTtc = vi.fn(
  (ttc: TResponseTtc, id: string, time: number): TResponseTtc => ({
    ...ttc,
    [id]: ((ttc[id] as number) || 0) + time,
  })
);
const mockUseTtc = vi.fn();

vi.mock("@/lib/ttc", () => ({
  getUpdatedTtc: (...args: unknown[]) => mockGetUpdatedTtc(...(args as [TResponseTtc, string, number])),
  useTtc: (...args: unknown[]) => mockUseTtc(...args),
}));

// ---------------------------------------------------------------------------
// Mock @/lib/i18n — getLocalizedValue resolves i18n strings.
// ---------------------------------------------------------------------------

vi.mock("@/lib/i18n", () => ({
  getLocalizedValue: vi.fn(
    (localizedString: Record<string, string> | undefined, languageCode: string): string | undefined => {
      if (!localizedString) return undefined;
      return localizedString[languageCode] || localizedString["default"] || "";
    }
  ),
}));

// ---------------------------------------------------------------------------
// Mock performance.now for deterministic TTC timing assertions.
// ---------------------------------------------------------------------------

vi.spyOn(performance, "now").mockReturnValue(1000);

// ---------------------------------------------------------------------------
// Test helper — creates a realistic mock Opinion Scale element with sensible
// defaults that match the ZSurveyOpinionScaleElement Zod schema.
// ---------------------------------------------------------------------------

function createMockElement(overrides: Record<string, unknown> = {}): {
  id: string;
  type: "opinionScale";
  headline: { default: string };
  subheader: { default: string } | undefined;
  required: boolean;
  scaleRange: number;
  lowerLabel: { default: string };
  upperLabel: { default: string };
  visualStyle: "number" | "smiley" | "star";
  isColorCodingEnabled: boolean;
  imageUrl: string | undefined;
  videoUrl: string | undefined;
} {
  return {
    id: "os1",
    type: "opinionScale",
    headline: { default: "How would you rate this?" },
    subheader: { default: "Select a value" },
    required: true,
    scaleRange: 5,
    lowerLabel: { default: "Not at all likely" },
    upperLabel: { default: "Extremely likely" },
    visualStyle: "number",
    isColorCodingEnabled: false,
    imageUrl: undefined,
    videoUrl: undefined,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Test Suites
// ---------------------------------------------------------------------------

describe("OpinionScaleElement", () => {
  const defaultProps = {
    element: createMockElement() as any,
    value: undefined as number | undefined,
    onChange: vi.fn(),
    languageCode: "default",
    ttc: {} as TResponseTtc,
    setTtc: vi.fn(),
    currentElementId: "os1",
    dir: "auto" as const,
    errorMessage: undefined as string | undefined,
  };

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    // Re-stub performance.now after clearAllMocks so it stays deterministic
    vi.spyOn(performance, "now").mockReturnValue(1000);
  });

  // -----------------------------------------------------------------------
  // Suite 1: Basic Rendering
  // -----------------------------------------------------------------------

  describe("basic rendering", () => {
    test("renders with default 5-point scale", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      expect(screen.getByTestId("opinion-scale-os1")).toBeTruthy();
      expect(screen.getByTestId("scale-range").textContent).toBe("5");
    });

    test("renders with 7-point scale", () => {
      const element = createMockElement({ scaleRange: 7 }) as any;
      render(<OpinionScaleElement {...defaultProps} element={element} />);
      expect(screen.getByTestId("scale-option-7")).toBeTruthy();
      expect(screen.getByTestId("scale-range").textContent).toBe("7");
    });

    test("renders with 10-point scale", () => {
      const element = createMockElement({ scaleRange: 10 }) as any;
      render(<OpinionScaleElement {...defaultProps} element={element} />);
      expect(screen.getByTestId("scale-option-10")).toBeTruthy();
      expect(screen.getByTestId("scale-range").textContent).toBe("10");
    });

    test("renders headline correctly", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      expect(screen.getByTestId("headline").textContent).toBe("How would you rate this?");
    });

    test("renders lower and upper labels", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      expect(screen.getByTestId("lower-label").textContent).toBe("Not at all likely");
      expect(screen.getByTestId("upper-label").textContent).toBe("Extremely likely");
    });

    test("renders visual style", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      expect(screen.getByTestId("visual-style").textContent).toBe("number");
    });

    test("renders smiley visual style", () => {
      const element = createMockElement({ visualStyle: "smiley" }) as any;
      render(<OpinionScaleElement {...defaultProps} element={element} />);
      expect(screen.getByTestId("visual-style").textContent).toBe("smiley");
    });

    test("renders star visual style", () => {
      const element = createMockElement({ visualStyle: "star" }) as any;
      render(<OpinionScaleElement {...defaultProps} element={element} />);
      expect(screen.getByTestId("visual-style").textContent).toBe("star");
    });

    test("renders all scale options from 1 to scaleRange", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      for (let i = 1; i <= 5; i++) {
        expect(screen.getByTestId(`scale-option-${i}`)).toBeTruthy();
      }
    });

    test("does not render scale options beyond scaleRange", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      expect(screen.queryByTestId("scale-option-6")).toBeNull();
    });

    test("renders inside a form element", () => {
      const { container } = render(<OpinionScaleElement {...defaultProps} />);
      const form = container.querySelector("form");
      expect(form).toBeTruthy();
      expect(form?.className).toContain("w-full");
    });

    test("renders description when subheader is provided", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      expect(screen.getByTestId("description").textContent).toBe("Select a value");
    });

    test("does not render description when subheader is undefined", () => {
      const element = createMockElement({ subheader: undefined }) as any;
      render(<OpinionScaleElement {...defaultProps} element={element} />);
      expect(screen.queryByTestId("description")).toBeNull();
    });
  });

  // -----------------------------------------------------------------------
  // Suite 2: onChange Handler
  // -----------------------------------------------------------------------

  describe("onChange handler", () => {
    test("fires onChange with correct response data format", () => {
      const onChange = vi.fn();
      render(<OpinionScaleElement {...defaultProps} onChange={onChange} />);
      fireEvent.click(screen.getByTestId("scale-option-3"));
      expect(onChange).toHaveBeenCalledWith({ os1: 3 });
    });

    test("fires onChange with scale boundary value 1 (minimum)", () => {
      const onChange = vi.fn();
      render(<OpinionScaleElement {...defaultProps} onChange={onChange} />);
      fireEvent.click(screen.getByTestId("scale-option-1"));
      expect(onChange).toHaveBeenCalledWith({ os1: 1 });
    });

    test("fires onChange with max scale value", () => {
      const onChange = vi.fn();
      render(<OpinionScaleElement {...defaultProps} onChange={onChange} />);
      fireEvent.click(screen.getByTestId("scale-option-5"));
      expect(onChange).toHaveBeenCalledWith({ os1: 5 });
    });

    test("fires onChange with 7-point scale max value", () => {
      const onChange = vi.fn();
      const element = createMockElement({ scaleRange: 7 }) as any;
      render(<OpinionScaleElement {...defaultProps} element={element} onChange={onChange} />);
      fireEvent.click(screen.getByTestId("scale-option-7"));
      expect(onChange).toHaveBeenCalledWith({ os1: 7 });
    });

    test("fires onChange with 10-point scale max value", () => {
      const onChange = vi.fn();
      const element = createMockElement({ scaleRange: 10 }) as any;
      render(<OpinionScaleElement {...defaultProps} element={element} onChange={onChange} />);
      fireEvent.click(screen.getByTestId("scale-option-10"));
      expect(onChange).toHaveBeenCalledWith({ os1: 10 });
    });

    test("uses element.id as the response key", () => {
      const onChange = vi.fn();
      const element = createMockElement({ id: "custom-opinion-scale" }) as any;
      render(
        <OpinionScaleElement
          {...defaultProps}
          element={element}
          currentElementId="custom-opinion-scale"
          onChange={onChange}
        />
      );
      fireEvent.click(screen.getByTestId("scale-option-2"));
      expect(onChange).toHaveBeenCalledWith({ "custom-opinion-scale": 2 });
    });

    test("fires onChange exactly once per click", () => {
      const onChange = vi.fn();
      render(<OpinionScaleElement {...defaultProps} onChange={onChange} />);
      fireEvent.click(screen.getByTestId("scale-option-4"));
      expect(onChange).toHaveBeenCalledTimes(1);
    });
  });

  // -----------------------------------------------------------------------
  // Suite 3: TTC Tracking
  // -----------------------------------------------------------------------

  describe("TTC tracking", () => {
    test("useTtc hook is called on render", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      expect(mockUseTtc).toHaveBeenCalled();
    });

    test("useTtc hook receives correct element id as first argument", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      expect(mockUseTtc.mock.calls[0][0]).toBe("os1");
    });

    test("useTtc hook receives ttc object", () => {
      const ttc = { existingQ: 500 } as TResponseTtc;
      render(<OpinionScaleElement {...defaultProps} ttc={ttc} />);
      expect(mockUseTtc.mock.calls[0][1]).toBe(ttc);
    });

    test("useTtc hook receives setTtc callback", () => {
      const setTtc = vi.fn();
      render(<OpinionScaleElement {...defaultProps} setTtc={setTtc} />);
      expect(mockUseTtc.mock.calls[0][2]).toBe(setTtc);
    });

    test("getUpdatedTtc is called on value change", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      fireEvent.click(screen.getByTestId("scale-option-2"));
      expect(mockGetUpdatedTtc).toHaveBeenCalled();
      // Second arg is element id
      expect(mockGetUpdatedTtc.mock.calls[0][1]).toBe("os1");
    });

    test("getUpdatedTtc receives the ttc object and element id", () => {
      const ttc = { os1: 200 } as TResponseTtc;
      render(<OpinionScaleElement {...defaultProps} ttc={ttc} />);
      fireEvent.click(screen.getByTestId("scale-option-3"));
      expect(mockGetUpdatedTtc.mock.calls[0][0]).toEqual(ttc);
      expect(mockGetUpdatedTtc.mock.calls[0][1]).toBe("os1");
    });

    test("setTtc is called with updated TTC after value change", () => {
      const setTtc = vi.fn();
      render(<OpinionScaleElement {...defaultProps} setTtc={setTtc} />);
      fireEvent.click(screen.getByTestId("scale-option-2"));
      expect(setTtc).toHaveBeenCalled();
    });

    test("isCurrent is true when element.id matches currentElementId", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      // The sixth argument to useTtc should be isCurrent (true)
      expect(mockUseTtc.mock.calls[0][5]).toBe(true);
    });

    test("isCurrent is false when element.id does not match currentElementId", () => {
      render(<OpinionScaleElement {...defaultProps} currentElementId="different-id" />);
      expect(mockUseTtc.mock.calls[0][5]).toBe(false);
    });
  });

  // -----------------------------------------------------------------------
  // Suite 4: Form Submission
  // -----------------------------------------------------------------------

  describe("form submission", () => {
    test("prevents default form submission", () => {
      const { container } = render(<OpinionScaleElement {...defaultProps} />);
      const form = container.querySelector("form");
      expect(form).toBeTruthy();
      const submitEvent = new Event("submit", { bubbles: true, cancelable: true });
      const preventDefault = vi.spyOn(submitEvent, "preventDefault");
      form?.dispatchEvent(submitEvent);
      expect(preventDefault).toHaveBeenCalled();
    });

    test("updates TTC on form submission via getUpdatedTtc", () => {
      const { container } = render(<OpinionScaleElement {...defaultProps} />);
      const form = container.querySelector("form");
      fireEvent.submit(form!);
      expect(mockGetUpdatedTtc).toHaveBeenCalled();
    });

    test("calls setTtc on form submission", () => {
      const setTtc = vi.fn();
      const { container } = render(<OpinionScaleElement {...defaultProps} setTtc={setTtc} />);
      const form = container.querySelector("form");
      fireEvent.submit(form!);
      expect(setTtc).toHaveBeenCalled();
    });

    test("getUpdatedTtc receives element id on form submission", () => {
      const { container } = render(<OpinionScaleElement {...defaultProps} />);
      const form = container.querySelector("form");
      fireEvent.submit(form!);
      expect(mockGetUpdatedTtc.mock.calls[0][1]).toBe("os1");
    });
  });

  // -----------------------------------------------------------------------
  // Suite 5: Prop Variations
  // -----------------------------------------------------------------------

  describe("prop variations", () => {
    test("renders without value (unselected state)", () => {
      render(<OpinionScaleElement {...defaultProps} value={undefined} />);
      expect(screen.getByTestId("opinion-scale-os1")).toBeTruthy();
      // No button should have aria-pressed="true"
      for (let i = 1; i <= 5; i++) {
        expect(screen.getByTestId(`scale-option-${i}`).getAttribute("aria-pressed")).toBe("false");
      }
    });

    test("renders with pre-selected value", () => {
      render(<OpinionScaleElement {...defaultProps} value={3} />);
      const button = screen.getByTestId("scale-option-3");
      expect(button.getAttribute("aria-pressed")).toBe("true");
    });

    test("only the selected option has aria-pressed true", () => {
      render(<OpinionScaleElement {...defaultProps} value={4} />);
      for (let i = 1; i <= 5; i++) {
        const pressed = screen.getByTestId(`scale-option-${i}`).getAttribute("aria-pressed");
        expect(pressed).toBe(i === 4 ? "true" : "false");
      }
    });

    test("renders with different element ID", () => {
      const element = createMockElement({ id: "custom-id" }) as any;
      render(<OpinionScaleElement {...defaultProps} element={element} currentElementId="custom-id" />);
      expect(screen.getByTestId("opinion-scale-custom-id")).toBeTruthy();
    });

    test("renders with color coding enabled", () => {
      const element = createMockElement({ isColorCodingEnabled: true }) as any;
      render(<OpinionScaleElement {...defaultProps} element={element} />);
      expect(screen.getByTestId("color-coding")).toBeTruthy();
    });

    test("renders without color coding when disabled", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      expect(screen.queryByTestId("color-coding")).toBeNull();
    });

    test("renders with error message", () => {
      render(<OpinionScaleElement {...defaultProps} errorMessage="This field is required" />);
      expect(screen.getByTestId("error-message").textContent).toBe("This field is required");
    });

    test("renders without error message when undefined", () => {
      render(<OpinionScaleElement {...defaultProps} errorMessage={undefined} />);
      expect(screen.queryByTestId("error-message")).toBeNull();
    });

    test("passes dir prop correctly", () => {
      render(<OpinionScaleElement {...defaultProps} dir="rtl" />);
      expect(screen.getByTestId("dir").textContent).toBe("rtl");
    });

    test("renders required label when element is required", () => {
      render(<OpinionScaleElement {...defaultProps} />);
      expect(screen.getByTestId("required")).toBeTruthy();
    });

    test("does not render required label when element is not required", () => {
      const element = createMockElement({ required: false }) as any;
      render(<OpinionScaleElement {...defaultProps} element={element} />);
      expect(screen.queryByTestId("required")).toBeNull();
    });
  });
});
