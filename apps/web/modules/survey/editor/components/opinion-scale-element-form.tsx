"use client";

import { useAutoAnimate } from "@formkit/auto-animate/react";
import { PlusIcon } from "lucide-react";
import { type JSX } from "react";
import { useTranslation } from "react-i18next";
import { TSurveyOpinionScaleElement } from "@formbricks/types/surveys/elements";
import { TSurvey } from "@formbricks/types/surveys/types";
import { TUserLocale } from "@formbricks/types/user";
import { createI18nString, extractLanguageCodes } from "@/lib/i18n/utils";
import { ElementFormInput } from "@/modules/survey/components/element-form-input";
import { Button } from "@/modules/ui/components/button";
import { Label } from "@/modules/ui/components/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/modules/ui/components/select";
import { Switch } from "@/modules/ui/components/switch";

interface OpinionScaleElementFormProps {
  localSurvey: TSurvey;
  element: TSurveyOpinionScaleElement;
  elementIdx: number;
  updateElement: (elementIdx: number, updatedAttributes: Partial<TSurveyOpinionScaleElement>) => void;
  selectedLanguageCode: string;
  setSelectedLanguageCode: (languageCode: string) => void;
  isInvalid: boolean;
  locale: TUserLocale;
  isStorageConfigured: boolean;
  isExternalUrlsAllowed?: boolean;
}

export const OpinionScaleElementForm = ({
  element,
  elementIdx,
  updateElement,
  isInvalid,
  localSurvey,
  selectedLanguageCode,
  setSelectedLanguageCode,
  locale,
  isStorageConfigured = true,
  isExternalUrlsAllowed,
}: OpinionScaleElementFormProps): JSX.Element => {
  const { t } = useTranslation();
  const surveyLanguageCodes = extractLanguageCodes(localSurvey.languages);

  const commonInputProps = {
    localSurvey,
    elementIdx,
    isInvalid,
    updateElement,
    selectedLanguageCode,
    setSelectedLanguageCode,
    locale,
    isStorageConfigured,
    isExternalUrlsAllowed,
  };

  const [parent] = useAutoAnimate();

  return (
    <form>
      <ElementFormInput
        {...commonInputProps}
        id="headline"
        value={element.headline}
        label={t("environments.surveys.edit.question") + "*"}
        autoFocus={!element.headline?.default || element.headline.default.trim() === ""}
      />

      <div ref={parent}>
        {element.subheader !== undefined && (
          <div className="inline-flex w-full items-center">
            <div className="w-full">
              <ElementFormInput
                {...commonInputProps}
                id="subheader"
                value={element.subheader}
                label={t("common.description")}
                autoFocus={!element.subheader?.default || element.subheader.default.trim() === ""}
              />
            </div>
          </div>
        )}
        {element.subheader === undefined && (
          <Button
            size="sm"
            variant="secondary"
            className="mt-3"
            type="button"
            onClick={() => {
              updateElement(elementIdx, {
                subheader: createI18nString("", surveyLanguageCodes),
              });
            }}>
            <PlusIcon className="mr-1 h-4 w-4" />
            {t("environments.surveys.edit.add_description")}
          </Button>
        )}
      </div>

      {/* Scale range selector */}
      <div className="mt-4">
        <Label htmlFor="scaleRange">{t("environments.surveys.edit.scale_range")}</Label>
        <Select
          value={String(element.scaleRange)}
          onValueChange={(value) => {
            updateElement(elementIdx, { scaleRange: parseInt(value, 10) as 5 | 7 | 10 });
          }}>
          <SelectTrigger className="mt-1 w-full">
            <SelectValue placeholder={t("environments.surveys.edit.select_scale_range")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="5">1 – 5</SelectItem>
            <SelectItem value="7">1 – 7</SelectItem>
            <SelectItem value="10">1 – 10</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Visual style selector */}
      <div className="mt-4">
        <Label htmlFor="visualStyle">{t("environments.surveys.edit.visual_style")}</Label>
        <Select
          value={element.visualStyle ?? "number"}
          onValueChange={(value) => {
            updateElement(elementIdx, { visualStyle: value as "number" | "smiley" | "star" });
          }}>
          <SelectTrigger className="mt-1 w-full">
            <SelectValue placeholder={t("environments.surveys.edit.select_visual_style")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="number">{t("environments.surveys.edit.numbers")}</SelectItem>
            <SelectItem value="smiley">{t("environments.surveys.edit.smileys")}</SelectItem>
            <SelectItem value="star">{t("environments.surveys.edit.stars")}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Lower label */}
      <div className="mt-4">
        <ElementFormInput
          {...commonInputProps}
          id="lowerLabel"
          value={element.lowerLabel}
          label={t("environments.surveys.edit.lower_label")}
        />
      </div>

      {/* Upper label */}
      <div className="mt-4">
        <ElementFormInput
          {...commonInputProps}
          id="upperLabel"
          value={element.upperLabel}
          label={t("environments.surveys.edit.upper_label")}
        />
      </div>

      {/* Color coding toggle */}
      <div className="mt-4 flex items-center gap-2">
        <Switch
          id="isColorCodingEnabled"
          checked={element.isColorCodingEnabled ?? false}
          onCheckedChange={(checked) => {
            updateElement(elementIdx, { isColorCodingEnabled: checked });
          }}
        />
        <Label htmlFor="isColorCodingEnabled">{t("environments.surveys.edit.enable_color_coding")}</Label>
      </div>
    </form>
  );
};
