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
import { Dropdown } from "@/modules/survey/editor/components/rating-type-dropdown";
import { Button } from "@/modules/ui/components/button";
import { Input } from "@/modules/ui/components/input";
import { Label } from "@/modules/ui/components/label";

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

  // Common props shared across all ElementFormInput components (same pattern as consent-element-form.tsx)
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
      {/* Headline — required question text */}
      <ElementFormInput
        {...commonInputProps}
        id="headline"
        value={element.headline}
        label={t("environments.surveys.edit.question") + "*"}
        autoFocus={!element.headline?.default || element.headline.default.trim() === ""}
      />

      {/* Subheader — optional description with add/remove toggle */}
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

      {/* Currency and Amount — side by side layout matching rating-element-form.tsx pattern */}
      <div className="mt-3 flex justify-between gap-8">
        {/* Currency Selector */}
        <div className="flex-1">
          <Label htmlFor="currency">{t("environments.surveys.edit.currency")}</Label>
          <div className="mt-2">
            <Dropdown
              options={[
                { label: "USD ($)", value: "usd" },
                { label: "EUR (€)", value: "eur" },
                { label: "GBP (£)", value: "gbp" },
              ]}
              defaultValue={element.currency || "usd"}
              onSelect={(option) =>
                updateElement(elementIdx, { currency: option.value as "usd" | "eur" | "gbp" })
              }
            />
          </div>
        </div>
        {/* Amount Input — value in smallest currency unit (cents/pence) */}
        <div className="flex-1">
          <Label htmlFor="amount">{t("environments.surveys.edit.amount")}</Label>
          <div className="mt-2">
            <Input
              type="number"
              id="amount"
              value={element.amount}
              onChange={(e) => updateElement(elementIdx, { amount: parseInt(e.target.value, 10) || 0 })}
              placeholder="1000"
              min={0}
            />
          </div>
          <p className="mt-1 text-xs text-slate-500">{t("environments.surveys.edit.amount_in_cents")}</p>
        </div>
      </div>

      {/* Stripe Configuration — publishable key and price ID inputs */}
      <div className="mt-3 space-y-3">
        {/* Stripe Publishable Key */}
        <div>
          <Label htmlFor="stripePublicKey">{t("environments.surveys.edit.stripe_publishable_key")}</Label>
          <div className="mt-2">
            <Input
              type="text"
              id="stripePublicKey"
              value={element.stripeIntegration.publicKey}
              onChange={(e) =>
                updateElement(elementIdx, {
                  stripeIntegration: {
                    ...element.stripeIntegration,
                    publicKey: e.target.value,
                  },
                })
              }
              placeholder="pk_live_..."
            />
          </div>
        </div>

        {/* Stripe Price ID */}
        <div>
          <Label htmlFor="stripePriceId">{t("environments.surveys.edit.stripe_price_id")}</Label>
          <div className="mt-2">
            <Input
              type="text"
              id="stripePriceId"
              value={element.stripeIntegration.priceId}
              onChange={(e) =>
                updateElement(elementIdx, {
                  stripeIntegration: {
                    ...element.stripeIntegration,
                    priceId: e.target.value,
                  },
                })
              }
              placeholder="price_..."
            />
          </div>
        </div>
      </div>

      {/* Button Label — i18n-enabled text for the payment submit button */}
      <ElementFormInput
        {...commonInputProps}
        id="buttonLabel"
        label={t("environments.surveys.edit.button_label")}
        placeholder="Pay now"
        value={element.buttonLabel}
      />
    </form>
  );
};
