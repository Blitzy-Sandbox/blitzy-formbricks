import { Star } from "lucide-react";
import * as React from "react";
import { ElementError } from "@/components/general/element-error";
import { ElementHeader } from "@/components/general/element-header";
import { Label } from "@/components/general/label";
import {
  ConfusedFace,
  FrowningFace,
  GrinningFaceWithSmilingEyes,
  GrinningSquintingFace,
  NeutralFace,
  PerseveringFace,
  SlightlySmilingFace,
  SmilingFaceWithSmilingEyes,
  TiredFace,
  WearyFace,
} from "@/components/general/smileys";
import { cn, getRTLScaleOptionClasses } from "@/lib/utils";

/**
 * Get smiley color class based on range and index
 */
const getSmileyColor = (range: number, idx: number): string => {
  if (range > 5) {
    if (range - idx < 3) return "fill-emerald-100";
    if (range - idx < 5) return "fill-orange-100";
    return "fill-rose-100";
  } else if (range < 5) {
    if (range - idx < 2) return "fill-emerald-100";
    if (range - idx < 3) return "fill-orange-100";
    return "fill-rose-100";
  }
  if (range - idx < 3) return "fill-emerald-100";
  if (range - idx < 4) return "fill-orange-100";
  return "fill-rose-100";
};

/**
 * Get active smiley color class based on range and index
 */
const getActiveSmileyColor = (range: number, idx: number): string => {
  if (range > 5) {
    if (range - idx < 3) return "fill-emerald-300";
    if (range - idx < 5) return "fill-orange-300";
    return "fill-rose-300";
  } else if (range < 5) {
    if (range - idx < 2) return "fill-emerald-300";
    if (range - idx < 3) return "fill-orange-300";
    return "fill-rose-300";
  }
  if (range - idx < 3) return "fill-emerald-300";
  if (range - idx < 4) return "fill-orange-300";
  return "fill-rose-300";
};

/**
 * Get the appropriate smiley icon based on range and index
 */
const getSmileyIcon = (
  iconIdx: number,
  idx: number,
  range: number,
  active: boolean,
  addColors: boolean
): React.JSX.Element => {
  const activeColor = addColors ? getActiveSmileyColor(range, idx) : "fill-yellow-200";
  const inactiveColor = addColors ? getSmileyColor(range, idx) : "fill-none";

  const icons = [
    <TiredFace key="tired-face" className={active ? activeColor : inactiveColor} />,
    <WearyFace key="weary-face" className={active ? activeColor : inactiveColor} />,
    <PerseveringFace key="persevering-face" className={active ? activeColor : inactiveColor} />,
    <FrowningFace key="frowning-face" className={active ? activeColor : inactiveColor} />,
    <ConfusedFace key="confused-face" className={active ? activeColor : inactiveColor} />,
    <NeutralFace key="neutral-face" className={active ? activeColor : inactiveColor} />,
    <SlightlySmilingFace key="slightly-smiling-face" className={active ? activeColor : inactiveColor} />,
    <SmilingFaceWithSmilingEyes
      key="smiling-face-with-smiling-eyes"
      className={active ? activeColor : inactiveColor}
    />,
    <GrinningFaceWithSmilingEyes
      key="grinning-face-with-smiling-eyes"
      className={active ? activeColor : inactiveColor}
    />,
    <GrinningSquintingFace key="grinning-squinting-face" className={active ? activeColor : inactiveColor} />,
  ];
  return icons[iconIdx];
};

/**
 * Smiley component for opinion scale
 * Maps scale ranges (5, 7, 10) to appropriate smiley icon indices
 */
const OpinionScaleSmiley = ({
  active,
  idx,
  range,
  addColors = false,
}: {
  active: boolean;
  idx: number;
  range: number;
  addColors?: boolean;
}): React.JSX.Element => {
  let iconsIdx: number[] = [];
  if (range === 10) iconsIdx = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
  else if (range === 7) iconsIdx = [1, 3, 4, 5, 6, 8, 9];
  else if (range === 5) iconsIdx = [3, 4, 5, 6, 7];

  return getSmileyIcon(iconsIdx[idx], idx, range, active, addColors);
};

interface OpinionScaleProps {
  /** Unique identifier for the element container */
  elementId: string;
  /** The main element or prompt text displayed as the headline */
  headline: string;
  /** Optional descriptive text displayed below the headline */
  description?: string;
  /** Unique identifier for the opinion scale group */
  inputId: string;
  /** Number of scale points: 5, 7, or 10 */
  scaleRange: 5 | 7 | 10;
  /** Visual rendering style: 'number', 'smiley', or 'star' */
  visualStyle: "number" | "smiley" | "star";
  /** Currently selected value (1 to scaleRange) */
  value?: number;
  /** Callback function called when value changes */
  onChange: (value: number) => void;
  /** Optional label for the lower end of the scale */
  lowerLabel?: string;
  /** Optional label for the upper end of the scale */
  upperLabel?: string;
  /** Whether color coding gradient is enabled (red-yellow-green) */
  isColorCodingEnabled?: boolean;
  /** Whether the field is required (shows asterisk indicator) */
  required?: boolean;
  /** Custom label for the required indicator */
  requiredLabel?: string;
  /** Error message to display */
  errorMessage?: string;
  /** Text direction */
  dir?: "ltr" | "rtl" | "auto";
  /** Whether the controls are disabled */
  disabled?: boolean;
  /** Image URL to display above the headline */
  imageUrl?: string;
  /** Video URL to display above the headline */
  videoUrl?: string;
}

function OpinionScale({
  elementId,
  headline,
  description,
  inputId,
  scaleRange,
  visualStyle,
  value,
  onChange,
  lowerLabel,
  upperLabel,
  isColorCodingEnabled = false,
  required = false,
  requiredLabel,
  errorMessage,
  dir = "auto",
  disabled = false,
  imageUrl,
  videoUrl,
}: Readonly<OpinionScaleProps>): React.JSX.Element {
  const [hoveredValue, setHoveredValue] = React.useState<number | null>(null);

  // Ensure value is within valid range (1 to scaleRange)
  const currentValue = value && value >= 1 && value <= scaleRange ? value : undefined;

  // Handle scale value selection
  const handleSelect = (ratingValue: number): void => {
    if (!disabled) {
      onChange(ratingValue);
    }
  };

  // Handle keyboard navigation (ArrowLeft/ArrowRight for traversal, Enter/Space for selection)
  const handleKeyDown = (ratingValue: number) => (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      handleSelect(ratingValue);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      e.preventDefault();
      const direction = e.key === "ArrowLeft" ? -1 : 1;
      const newValue = Math.max(1, Math.min(scaleRange, (currentValue ?? 1) + direction));
      handleSelect(newValue);
    }
  };

  // Get number option color for color coding gradient
  const getRatingNumberOptionColor = (ratingRange: number, idx: number): string => {
    if (ratingRange > 5) {
      if (ratingRange - idx < 2) return "bg-emerald-100";
      if (ratingRange - idx < 4) return "bg-orange-100";
      return "bg-rose-100";
    } else if (ratingRange < 5) {
      if (ratingRange - idx < 1) return "bg-emerald-100";
      if (ratingRange - idx < 2) return "bg-orange-100";
      return "bg-rose-100";
    }
    if (ratingRange - idx < 2) return "bg-emerald-100";
    if (ratingRange - idx < 3) return "bg-orange-100";
    return "bg-rose-100";
  };

  // Render number scale option
  const renderNumberOption = (number: number, totalLength: number): React.JSX.Element => {
    const isSelected = currentValue === number;
    const isHovered = hoveredValue === number;
    const isLast = totalLength === number;
    const isFirst = number === 1;

    // Use CSS logical properties for RTL-aware borders and border radius
    // The parent div's dir attribute automatically handles direction
    const { borderRadiusClasses, borderClasses } = getRTLScaleOptionClasses(isFirst, isLast);

    return (
      // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- label is interactive
      <label
        key={number}
        tabIndex={disabled ? -1 : 0}
        onKeyDown={handleKeyDown(number)}
        className={cn(
          "text-input-text font-input font-input-weight relative flex w-full cursor-pointer items-center justify-center overflow-hidden transition-colors focus:outline-none",
          borderClasses,
          isSelected
            ? "bg-brand-20 border-brand z-10 -ml-[1px] border-2 first:ml-0"
            : "border-input-border bg-input-bg",
          borderRadiusClasses,
          isHovered && !isSelected && "bg-input-selected-bg",
          isColorCodingEnabled ? "min-h-[47px]" : "min-h-[41px]",
          disabled && "cursor-not-allowed opacity-50",
          "focus:border-brand focus:border-2"
        )}
        onMouseEnter={() => {
          if (!disabled) {
            setHoveredValue(number);
          }
        }}
        onMouseLeave={() => {
          setHoveredValue(null);
        }}
        onFocus={() => {
          if (!disabled) {
            setHoveredValue(number);
          }
        }}
        onBlur={() => {
          setHoveredValue(null);
        }}>
        {isColorCodingEnabled ? (
          <div
            className={cn(
              "absolute left-0 top-0 h-[6px] w-full",
              getRatingNumberOptionColor(scaleRange, number)
            )}
          />
        ) : null}
        <input
          type="radio"
          name={inputId}
          value={number}
          checked={isSelected}
          onChange={() => {
            handleSelect(number);
          }}
          disabled={disabled}
          className="sr-only"
          aria-label={`Select ${String(number)} out of ${String(scaleRange)}`}
        />
        <span className="text-sm">{number}</span>
      </label>
    );
  };

  // Render star scale option
  const renderStarOption = (number: number): React.JSX.Element => {
    const isSelected = currentValue === number;
    // Fill all stars up to the hovered value (if hovering) or selected value
    const activeValue = hoveredValue ?? currentValue ?? 0;
    const isActive = number <= activeValue;

    return (
      // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- label is interactive
      <label
        key={number}
        className={cn(
          "flex min-h-[48px] flex-1 cursor-pointer items-center justify-center transition-opacity",
          disabled && "cursor-not-allowed opacity-50"
        )}
        onMouseEnter={() => {
          if (!disabled) {
            setHoveredValue(number);
          }
        }}
        onMouseLeave={() => {
          setHoveredValue(null);
        }}
        onFocus={() => {
          if (!disabled) {
            setHoveredValue(number);
          }
        }}
        onBlur={() => {
          setHoveredValue(null);
        }}
        tabIndex={disabled ? -1 : 0}
        onKeyDown={handleKeyDown(number)}>
        <input
          type="radio"
          name={inputId}
          value={number}
          checked={isSelected}
          onChange={() => {
            handleSelect(number);
          }}
          disabled={disabled}
          className="sr-only"
          aria-label={`Select ${String(number)} out of ${String(scaleRange)} stars`}
        />
        <div className="pointer-events-none flex w-full max-w-[74px] items-center justify-center">
          {isActive ? (
            <Star className="h-full w-full fill-yellow-400 text-yellow-400 transition-colors" />
          ) : (
            <Star className="h-full w-full fill-slate-300 text-slate-300 transition-colors" />
          )}
        </div>
      </label>
    );
  };

  // Render smiley scale option
  const renderSmileyOption = (number: number, index: number): React.JSX.Element => {
    const isSelected = currentValue === number;
    const isHovered = hoveredValue === number;
    const isActive = isSelected || isHovered;

    return (
      // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- label is interactive
      <label
        key={number}
        tabIndex={disabled ? -1 : 0}
        onKeyDown={handleKeyDown(number)}
        className={cn(
          "relative flex max-h-16 min-h-9 w-full cursor-pointer justify-center transition-colors focus:outline-none",
          isActive
            ? "stroke-brand text-brand"
            : "stroke-muted-foreground text-muted-foreground focus:border-accent focus:border-2",
          disabled && "cursor-not-allowed opacity-50"
        )}
        onMouseEnter={() => {
          if (!disabled) {
            setHoveredValue(number);
          }
        }}
        onMouseLeave={() => {
          setHoveredValue(null);
        }}
        onFocus={() => {
          if (!disabled) {
            setHoveredValue(number);
          }
        }}
        onBlur={() => {
          setHoveredValue(null);
        }}>
        <input
          type="radio"
          name={inputId}
          value={number}
          checked={isSelected}
          onChange={() => {
            handleSelect(number);
          }}
          disabled={disabled}
          className="sr-only"
          aria-label={`Select ${String(number)} out of ${String(scaleRange)}`}
        />
        <div className="text-input-text pointer-events-none h-full w-full max-w-[74px] object-contain">
          <OpinionScaleSmiley
            active={isActive}
            idx={index}
            range={scaleRange}
            addColors={isColorCodingEnabled}
          />
        </div>
      </label>
    );
  };

  // Generate opinion scale options (1 to scaleRange)
  const scaleOptions = Array.from({ length: scaleRange }, (_, i) => i + 1);

  return (
    <div className="w-full space-y-4" id={elementId} dir={dir}>
      {/* Headline */}
      <ElementHeader
        headline={headline}
        description={description}
        required={required}
        requiredLabel={requiredLabel}
        htmlFor={inputId}
        imageUrl={imageUrl}
        videoUrl={videoUrl}
      />

      {/* Opinion Scale Options */}
      <div className="relative">
        <ElementError errorMessage={errorMessage} dir={dir} />
        <fieldset className="w-full" dir={dir}>
          <legend className="sr-only">Opinion scale options</legend>
          <div className="flex w-full px-[2px]">
            {scaleOptions.map((number, index) => {
              if (visualStyle === "number") {
                return renderNumberOption(number, scaleOptions.length);
              } else if (visualStyle === "star") {
                return renderStarOption(number);
              }
              return renderSmileyOption(number, index);
            })}
          </div>

          {/* Labels */}
          {(lowerLabel ?? upperLabel) ? (
            <div className="mt-4 flex justify-between gap-8 px-1.5">
              {lowerLabel ? (
                <Label variant="default" className="max-w-[50%] text-xs leading-6" dir={dir}>
                  {lowerLabel}
                </Label>
              ) : null}
              {upperLabel ? (
                <Label variant="default" className="max-w-[50%] text-right text-xs leading-6" dir={dir}>
                  {upperLabel}
                </Label>
              ) : null}
            </div>
          ) : null}
        </fieldset>
      </div>
    </div>
  );
}

export { OpinionScale };
export type { OpinionScaleProps };
