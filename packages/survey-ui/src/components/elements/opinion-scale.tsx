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
 * Get the smiley icon for a given index and scale range.
 * The smiley palette scales based on the range (5, 7, 10).
 */
const getSmileyForIndex = (
  index: number,
  scaleRange: number,
  active: boolean,
  addColors: boolean
): React.JSX.Element => {
  // Map index to one of the 10 smileys evenly based on the range
  const normalised = Math.round(((index - 1) / (scaleRange - 1)) * 9);
  const smileys = [
    TiredFace,
    WearyFace,
    PerseveringFace,
    FrowningFace,
    ConfusedFace,
    NeutralFace,
    SlightlySmilingFace,
    SmilingFaceWithSmilingEyes,
    GrinningSquintingFace,
    GrinningFaceWithSmilingEyes,
  ];
  const Smiley = smileys[normalised] ?? NeutralFace;
  const colorClass = active
    ? addColors
      ? normalised >= 7
        ? "fill-emerald-300"
        : normalised >= 4
          ? "fill-orange-300"
          : "fill-rose-300"
      : "fill-yellow-200"
    : addColors
      ? normalised >= 7
        ? "fill-emerald-100"
        : normalised >= 4
          ? "fill-orange-100"
          : "fill-rose-100"
      : "fill-none";
  return <Smiley className={colorClass} />;
};

/**
 * Get the color for a number button based on index and scale range.
 */
const getNumberColor = (index: number, scaleRange: number, active: boolean): string => {
  const normalised = (index - 1) / (scaleRange - 1);
  if (active) {
    if (normalised >= 0.7) return "fb-bg-emerald-100";
    if (normalised >= 0.4) return "fb-bg-orange-100";
    return "fb-bg-rose-100";
  }
  return "";
};

interface OpinionScaleElementProps {
  elementId: string;
  headline: string;
  description?: string;
  scaleRange: number;
  lowerLabel: string;
  upperLabel: string;
  visualStyle?: "number" | "smiley" | "star";
  isColorCodingEnabled?: boolean;
  value?: number;
  onChange: (value: number) => void;
  dir?: "ltr" | "rtl" | "auto";
  required?: boolean;
  errorMessage?: string;
  languageCode: string;
}

export const OpinionScaleElement = React.forwardRef<HTMLDivElement, OpinionScaleElementProps>(
  (
    {
      elementId,
      headline,
      description,
      scaleRange,
      lowerLabel,
      upperLabel,
      visualStyle = "number",
      isColorCodingEnabled = false,
      value,
      onChange,
      dir = "ltr",
      required = false,
      errorMessage,
      languageCode,
    },
    ref
  ) => {
    const scaleItems = Array.from({ length: scaleRange }, (_, i) => i + 1);

    const renderScaleButton = (num: number) => {
      const isActive = value === num;

      if (visualStyle === "smiley") {
        return (
          <button
            key={num}
            type="button"
            onClick={() => onChange(num)}
            className={cn(
              "fb-flex fb-h-10 fb-w-10 fb-items-center fb-justify-center fb-rounded-full fb-border fb-transition-all",
              isActive ? "fb-border-brand fb-ring-2 fb-ring-brand" : "fb-border-border hover:fb-border-brand"
            )}>
            {getSmileyForIndex(num, scaleRange, isActive, isColorCodingEnabled)}
          </button>
        );
      }

      if (visualStyle === "star") {
        return (
          <button
            key={num}
            type="button"
            onClick={() => onChange(num)}
            className={cn(
              "fb-flex fb-h-10 fb-w-10 fb-items-center fb-justify-center fb-transition-all",
              isActive || (value != null && num <= value)
                ? "fb-text-brand"
                : "fb-text-border hover:fb-text-brand"
            )}>
            <Star
              className={cn(
                "fb-h-6 fb-w-6",
                isActive || (value != null && num <= value) ? "fill-current" : ""
              )}
            />
          </button>
        );
      }

      // Default: "number"
      return (
        <button
          key={num}
          type="button"
          onClick={() => onChange(num)}
          className={cn(
            "fb-flex fb-h-10 fb-min-w-10 fb-items-center fb-justify-center fb-rounded-custom fb-border fb-text-heading fb-transition-all",
            isActive
              ? "fb-border-brand fb-bg-brand fb-text-on-brand fb-font-semibold"
              : cn(
                  "fb-border-border hover:fb-border-brand",
                  isColorCodingEnabled ? getNumberColor(num, scaleRange, true) : ""
                )
          )}>
          {num}
        </button>
      );
    };

    return (
      <div ref={ref} dir={dir}>
        <ElementHeader headline={headline} description={description ?? ""} required={required} />
        <div className="fb-mt-4">
          <div className="fb-flex fb-flex-wrap fb-justify-between fb-gap-2">
            {scaleItems.map(renderScaleButton)}
          </div>
          <div className="fb-mt-2 fb-flex fb-justify-between fb-text-xs fb-text-subheading">
            <Label>{lowerLabel}</Label>
            <Label>{upperLabel}</Label>
          </div>
        </div>
        {errorMessage && <ElementError errorMessage={errorMessage} />}
      </div>
    );
  }
);

OpinionScaleElement.displayName = "OpinionScaleElement";
