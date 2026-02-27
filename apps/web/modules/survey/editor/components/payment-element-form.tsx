"use client";

import { useAutoAnimate } from "@formkit/auto-animate/react";
import { PlusIcon } from "lucide-react";
import { type JSX } from "react";
import { useTranslation } from "react-i18next";
import { TSurveyPaymentElement } from "@formbricks/types/surveys/elements";
import { TSurvey } from "@formbricks/types/surveys/types";
import { TUserLocale } from "@formbricks/types/user";
import { createI18nString, extractLanguageCodes } from "@/lib/i18n/utils";
import { ElementFormInput } from "@/modules/survey/components/element-form-input";
import { Button } from "@/modules/ui/components/button";
import { Input } from "@/modules/ui/components/input";
import { Label } from "@/modules/ui/components/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/modules/ui/components/select";

interface PaymentElementFormProps {
  localSurvey: TSurvey;
  element: TSurveyPaymentElement;
  elementIdx: number;
  updateElement: (elementIdx: number, updatedAttributes: Partial<TSurveyPaymentElement>) => void;
  selectedLanguageCode: string;
  setSelectedLanguageCode: (languageCode: string) => void;
  isInvalid: boolean;
  locale: TUserLocale;
  isStorageConfigured: boolean;
  isExternalUrlsAllowed?: boolean;
}

export const PaymentElementForm = ({
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
}: PaymentElementFormProps): JSX.Element => {
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

  /** Convert the stored smallest-unit amount to a display value (e.g. 1000 → "10.00") */
  const displayAmount = element.amount != null ? (element.amount / 100).toFixed(2) : "";

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

      {/* Currency selector */}
      <div className="mt-4">
        <Label htmlFor="currency">{t("environments.surveys.edit.currency")}</Label>
        <Select
          value={element.currency}
          onValueChange={(value) => {
            updateElement(elementIdx, {
              currency: value as "usd" | "eur" | "gbp",
            });
          }}>
          <SelectTrigger className="mt-1 w-full">
            <SelectValue placeholder={t("environments.surveys.edit.select_currency")} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="usd">USD ($)</SelectItem>
            <SelectItem value="eur">EUR (€)</SelectItem>
            <SelectItem value="gbp">GBP (£)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Amount input */}
      <div className="mt-4">
        <Label htmlFor="amount">{t("environments.surveys.edit.amount")}</Label>
        <Input
          id="amount"
          type="number"
          className="mt-1"
          min={0.01}
          step={0.01}
          value={displayAmount}
          onChange={(e) => {
            const val = parseFloat(e.target.value);
            if (!isNaN(val)) {
              updateElement(elementIdx, { amount: Math.round(val * 100) });
            }
          }}
          placeholder="0.00"
        />
      </div>

      {/* Stripe public key */}
      <div className="mt-4">
        <Label htmlFor="stripePublicKey">{t("environments.surveys.edit.stripe_public_key")}</Label>
        <Input
          id="stripePublicKey"
          type="text"
          className="mt-1"
          value={element.stripeIntegration?.publicKey ?? ""}
          onChange={(e) => {
            updateElement(elementIdx, {
              stripeIntegration: {
                ...element.stripeIntegration,
                publicKey: e.target.value,
              },
            });
          }}
          placeholder="pk_..."
        />
      </div>

      {/* Stripe price ID */}
      <div className="mt-4">
        <Label htmlFor="stripePriceId">{t("environments.surveys.edit.stripe_price_id")}</Label>
        <Input
          id="stripePriceId"
          type="text"
          className="mt-1"
          value={element.stripeIntegration?.priceId ?? ""}
          onChange={(e) => {
            updateElement(elementIdx, {
              stripeIntegration: {
                ...element.stripeIntegration,
                priceId: e.target.value,
              },
            });
          }}
          placeholder="price_..."
        />
      </div>

      {/* Button label (optional) */}
      <div className="mt-4">
        <ElementFormInput
          {...commonInputProps}
          id="buttonLabel"
          value={element.buttonLabel ?? createI18nString("", surveyLanguageCodes)}
          label={t("environments.surveys.edit.button_label")}
        />
      </div>
    </form>
  );
};
