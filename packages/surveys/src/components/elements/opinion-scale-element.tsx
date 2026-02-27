import { useState } from "preact/hooks";
import { OpinionScaleElement as OpinionScaleUI } from "@formbricks/survey-ui";
import { type TResponseData, type TResponseTtc } from "@formbricks/types/responses";
import type { TSurveyOpinionScaleElement } from "@formbricks/types/surveys/elements";
import { getLocalizedValue } from "@/lib/i18n";
import { getUpdatedTtc, useTtc } from "@/lib/ttc";

interface OpinionScaleElementProps {
  element: TSurveyOpinionScaleElement;
  value?: number;
  onChange: (responseData: TResponseData) => void;
  languageCode: string;
  ttc: TResponseTtc;
  setTtc: (ttc: TResponseTtc) => void;
  currentElementId: string;
  dir?: "ltr" | "rtl" | "auto";
  errorMessage?: string;
}

export function OpinionScaleElement({
  element,
  value,
  onChange,
  languageCode,
  ttc,
  setTtc,
  currentElementId,
  dir = "auto",
  errorMessage,
}: Readonly<OpinionScaleElementProps>) {
  const [startTime, setStartTime] = useState(performance.now());
  const isCurrent = element.id === currentElementId;
  useTtc(element.id, ttc, setTtc, startTime, setStartTime, isCurrent);

  const handleChange = (scaleValue: number) => {
    onChange({ [element.id]: scaleValue });
    const updatedTtcObj = getUpdatedTtc(ttc, element.id, performance.now() - startTime);
    setTtc(updatedTtcObj);
  };

  const handleSubmit = (e: Event) => {
    e.preventDefault();
    const updatedTtcObj = getUpdatedTtc(ttc, element.id, performance.now() - startTime);
    setTtc(updatedTtcObj);
  };

  return (
    <form key={element.id} onSubmit={handleSubmit} className="w-full">
      <OpinionScaleUI
        elementId={element.id}
        headline={getLocalizedValue(element.headline, languageCode)}
        description={element.subheader ? getLocalizedValue(element.subheader, languageCode) : undefined}
        scaleRange={element.scaleRange}
        lowerLabel={getLocalizedValue(element.lowerLabel, languageCode)}
        upperLabel={getLocalizedValue(element.upperLabel, languageCode)}
        visualStyle={element.visualStyle}
        isColorCodingEnabled={element.isColorCodingEnabled}
        value={value}
        onChange={handleChange}
        dir={dir}
        required={element.required}
        errorMessage={errorMessage}
        languageCode={languageCode}
      />
    </form>
  );
}
