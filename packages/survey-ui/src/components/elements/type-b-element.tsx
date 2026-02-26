import * as React from "react";
import { ElementError } from "@/components/general/element-error";
import { ElementHeader } from "@/components/general/element-header";
import { Input } from "@/components/general/input";

/**
 * Props for the TypeB element component.
 * A generic survey element that collects text input from respondents.
 */
interface TypeBElementProps {
  /** Unique identifier for the element container */
  elementId: string;
  /** The main question or prompt text displayed as the headline */
  headline: string;
  /** Optional descriptive text displayed below the headline */
  description?: string;
  /** Unique identifier for the input control */
  inputId: string;
  /** Optional placeholder text for the input field */
  placeholder?: string;
  /** Current input value */
  value?: string;
  /** Callback function called when the input value changes */
  onChange: (value: string) => void;
  /** Whether the field is required (shows asterisk indicator) */
  required?: boolean;
  /** Custom label for the required indicator */
  requiredLabel?: string;
  /** Error message to display when validation fails */
  errorMessage?: string;
  /** Text direction: 'ltr' (left-to-right), 'rtl' (right-to-left), or 'auto' (auto-detect from content) */
  dir?: "ltr" | "rtl" | "auto";
  /** Whether the input is disabled */
  disabled?: boolean;
  /** Image URL to display above the headline */
  imageUrl?: string;
  /** Video URL to display above the headline */
  videoUrl?: string;
}

/**
 * TypeB survey element component.
 *
 * Renders a text input field with a headline, optional description,
 * optional media (image/video), error display, and full accessibility support.
 * Follows the simple element pattern established by consent.tsx and open-text.tsx.
 *
 * @param props - The component props conforming to {@link TypeBElementProps}
 * @returns A React element containing the TypeB survey input
 */
function TypeBElement({
  elementId,
  headline,
  description,
  inputId,
  placeholder,
  value = "",
  onChange,
  required = false,
  requiredLabel,
  errorMessage,
  dir = "auto",
  disabled = false,
  imageUrl,
  videoUrl,
}: Readonly<TypeBElementProps>): React.JSX.Element {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>): void => {
    if (disabled) return;
    onChange(e.target.value);
  };

  return (
    <div className="w-full space-y-4" id={elementId} dir={dir}>
      {/* Headline, description, required indicator, and optional media */}
      <ElementHeader
        headline={headline}
        description={description}
        required={required}
        requiredLabel={requiredLabel}
        htmlFor={inputId}
        imageUrl={imageUrl}
        videoUrl={videoUrl}
      />

      {/* Error indicator and text input */}
      <div className="relative">
        <ElementError errorMessage={errorMessage} dir={dir} />
        <Input
          id={inputId}
          placeholder={placeholder}
          value={value}
          onChange={handleChange}
          aria-required={required}
          aria-invalid={Boolean(errorMessage)}
          dir={dir}
          disabled={disabled}
          errorMessage={errorMessage}
        />
      </div>
    </div>
  );
}

export { TypeBElement };
export type { TypeBElementProps };
