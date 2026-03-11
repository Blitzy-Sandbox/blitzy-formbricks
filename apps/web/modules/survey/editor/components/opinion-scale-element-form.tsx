"use client";

import { useAutoAnimate } from "@formkit/auto-animate/react";
import { HashIcon, PlusIcon, SmileIcon, StarIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { TSurveyOpinionScaleElement } from "@formbricks/types/surveys/elements";
import { TSurvey } from "@formbricks/types/surveys/types";
import { TUserLocale } from "@formbricks/types/user";
import { createI18nString, extractLanguageCodes } from "@/lib/i18n/utils";
import { ElementFormInput } from "@/modules/survey/components/element-form-input";
import { Dropdown } from "@/modules/survey/editor/components/rating-type-dropdown";
import { AdvancedOptionToggle } from "@/modules/ui/components/advanced-option-toggle";
import { Button } from "@/modules/ui/components/button";
import { Label } from "@/modules/ui/components/label";

interface OpinionScaleElementFormProps {
  localSurvey: TSurvey;
  element: TSurveyOpinionScaleElement;
  elementIdx: number;
  updateElement: (elementIdx: number, updatedAttributes: Partial<TSurveyOpinionScaleElement>) => void;
  lastElement: boolean;
  selectedLanguageCode: string;
  setSelectedLanguageCode: (language: string) => void;
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
}: OpinionScaleElementFormProps) => {
  const { t } = useTranslation();
  const surveyLanguageCodes = extractLanguageCodes(localSurvey.languages);
  const [parent] = useAutoAnimate();

  return (
    <form>
      {/* Headline input — required field for the opinion scale question text */}
      <ElementFormInput
        id="headline"
        value={element.headline}
        label={t("environments.surveys.edit.question") + "*"}
        localSurvey={localSurvey}
        elementIdx={elementIdx}
        isInvalid={isInvalid}
        updateElement={updateElement}
        selectedLanguageCode={selectedLanguageCode}
        setSelectedLanguageCode={setSelectedLanguageCode}
        locale={locale}
        isStorageConfigured={isStorageConfigured}
        autoFocus={!element.headline?.default || element.headline.default.trim() === ""}
        isExternalUrlsAllowed={isExternalUrlsAllowed}
      />

      {/* Subheader / description — optional, toggled via "Add description" button */}
      <div ref={parent}>
        {element.subheader !== undefined && (
          <div className="inline-flex w-full items-center">
            <div className="w-full">
              <ElementFormInput
                id="subheader"
                value={element.subheader}
                label={t("common.description")}
                localSurvey={localSurvey}
                elementIdx={elementIdx}
                isInvalid={isInvalid}
                updateElement={updateElement}
                selectedLanguageCode={selectedLanguageCode}
                setSelectedLanguageCode={setSelectedLanguageCode}
                locale={locale}
                isStorageConfigured={isStorageConfigured}
                autoFocus={!element.subheader?.default || element.subheader.default.trim() === ""}
                isExternalUrlsAllowed={isExternalUrlsAllowed}
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

      {/* Visual Style and Scale Range selectors — side by side layout */}
      <div className="mt-3 flex justify-between gap-8">
        {/* Visual style selector (number / star / smiley) */}
        <div className="flex-1">
          <Label htmlFor="visualStyle">{t("environments.surveys.edit.scale")}</Label>
          <div className="mt-2">
            <Dropdown
              options={[
                { label: t("environments.surveys.edit.number"), value: "number", icon: HashIcon },
                { label: t("environments.surveys.edit.star"), value: "star", icon: StarIcon },
                { label: t("environments.surveys.edit.smiley"), value: "smiley", icon: SmileIcon },
              ]}
              defaultValue={element.visualStyle || "number"}
              onSelect={(option) => {
                if (option.value === "star") {
                  // Star style does not support color coding — disable it on selection
                  updateElement(elementIdx, {
                    visualStyle: option.value as "number" | "smiley" | "star",
                    isColorCodingEnabled: false,
                  });
                  return;
                }
                updateElement(elementIdx, {
                  visualStyle: option.value as "number" | "smiley" | "star",
                });
              }}
            />
          </div>
        </div>

        {/* Scale range selector — Opinion Scale supports 5, 7, or 10 point ranges only */}
        <div className="flex-1">
          <Label htmlFor="scaleRange">{t("environments.surveys.edit.range")}</Label>
          <div className="mt-2">
            <Dropdown
              options={[
                { label: t("environments.surveys.edit.five_points_recommended"), value: 5 },
                { label: t("environments.surveys.edit.seven_points"), value: 7 },
                { label: t("environments.surveys.edit.ten_points"), value: 10 },
              ]}
              defaultValue={element.scaleRange || 5}
              onSelect={(option) => updateElement(elementIdx, { scaleRange: option.value as 5 | 7 | 10 })}
            />
          </div>
        </div>
      </div>

      {/* Lower and upper endpoint labels — side by side layout with i18n support */}
      <div className="flex justify-between gap-8">
        <div className="flex-1">
          <ElementFormInput
            id="lowerLabel"
            placeholder="Not at all likely"
            value={element.lowerLabel}
            label={t("environments.surveys.edit.lower_label")}
            localSurvey={localSurvey}
            elementIdx={elementIdx}
            isInvalid={isInvalid}
            updateElement={updateElement}
            selectedLanguageCode={selectedLanguageCode}
            setSelectedLanguageCode={setSelectedLanguageCode}
            locale={locale}
            isStorageConfigured={isStorageConfigured}
          />
        </div>
        <div className="flex-1">
          <ElementFormInput
            id="upperLabel"
            placeholder="Very likely"
            value={element.upperLabel}
            label={t("environments.surveys.edit.upper_label")}
            localSurvey={localSurvey}
            elementIdx={elementIdx}
            isInvalid={isInvalid}
            updateElement={updateElement}
            selectedLanguageCode={selectedLanguageCode}
            setSelectedLanguageCode={setSelectedLanguageCode}
            locale={locale}
            isStorageConfigured={isStorageConfigured}
          />
        </div>
      </div>

      {/* Color coding toggle — hidden when star visual style is selected */}
      {element.visualStyle !== "star" && (
        <AdvancedOptionToggle
          isChecked={element.isColorCodingEnabled}
          onToggle={() => updateElement(elementIdx, { isColorCodingEnabled: !element.isColorCodingEnabled })}
          htmlId="isColorCodingEnabled"
          title={t("environments.surveys.edit.add_color_coding")}
          description={t("environments.surveys.edit.add_color_coding_description")}
          childBorder
          customContainerClass="p-0 mt-4"
        />
      )}
    </form>
  );
};
