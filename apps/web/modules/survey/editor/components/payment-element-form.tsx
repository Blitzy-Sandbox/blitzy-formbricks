"use client";

import { useAutoAnimate } from "@formkit/auto-animate/react";
import { Project } from "@prisma/client";
import { CheckCircle2Icon, ExternalLinkIcon, LinkIcon, PlusIcon, UnplugIcon } from "lucide-react";
import { type JSX, useCallback, useEffect, useState } from "react";
import { toast } from "react-hot-toast";
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
  project: Project;
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
  project,
  selectedLanguageCode,
  setSelectedLanguageCode,
  locale,
  isStorageConfigured = true,
  isExternalUrlsAllowed,
}: PaymentElementFormProps): JSX.Element => {
  const { t } = useTranslation();
  const surveyLanguageCodes = extractLanguageCodes(localSurvey.languages);

  // Stripe Connect state
  const [stripeConnectStatus, setStripeConnectStatus] = useState<"loading" | "connected" | "disconnected">(
    "loading"
  );
  const [stripeConnectAccountId, setStripeConnectAccountId] = useState<string | null>(null);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  // Fetch Stripe Connect status for the organization
  const fetchStripeConnectStatus = useCallback(async () => {
    try {
      const response = await fetch(`/api/stripe-connect/status?organizationId=${project.organizationId}`);
      if (response.ok) {
        const data = await response.json();
        if (data.data?.stripeConnectAccountId) {
          setStripeConnectStatus("connected");
          setStripeConnectAccountId(data.data.stripeConnectAccountId);
          // Update the element's stripeIntegration.publicKey with the OAuth-provided key
          if (
            data.data.stripeConnectPublishableKey &&
            data.data.stripeConnectPublishableKey !== element.stripeIntegration.publicKey
          ) {
            updateElement(elementIdx, {
              stripeIntegration: {
                ...element.stripeIntegration,
                publicKey: data.data.stripeConnectPublishableKey,
              },
            });
          }
        } else {
          setStripeConnectStatus("disconnected");
          setStripeConnectAccountId(null);
        }
      } else {
        setStripeConnectStatus("disconnected");
      }
    } catch {
      setStripeConnectStatus("disconnected");
    }
  }, [project.organizationId, element.stripeIntegration, elementIdx, updateElement]);

  useEffect(() => {
    fetchStripeConnectStatus();
    // Only run on mount and when organizationId changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.organizationId]);

  // Handle initiating Stripe Connect
  const handleConnectStripe = () => {
    window.location.href = `/api/stripe-connect/authorize?organizationId=${project.organizationId}`;
  };

  // Handle disconnecting Stripe
  const handleDisconnectStripe = async () => {
    setIsDisconnecting(true);
    try {
      const response = await fetch("/api/stripe-connect/disconnect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ organizationId: project.organizationId }),
      });
      if (response.ok) {
        setStripeConnectStatus("disconnected");
        setStripeConnectAccountId(null);
        // Clear the publishable key from the element
        updateElement(elementIdx, {
          stripeIntegration: {
            ...element.stripeIntegration,
            publicKey: "",
          },
        });
        toast.success(t("environments.surveys.edit.stripe_disconnected"));
      } else {
        toast.error(t("environments.surveys.edit.stripe_disconnect_failed"));
      }
    } catch {
      toast.error(t("environments.surveys.edit.stripe_disconnect_failed"));
    } finally {
      setIsDisconnecting(false);
    }
  };

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
              onChange={(e) => {
                const parsed = parseInt(e.target.value, 10) || 1;
                updateElement(elementIdx, { amount: Math.max(1, parsed) });
              }}
              placeholder="1000"
              min={1}
            />
          </div>
          <p className="mt-1 text-xs text-slate-500">{t("environments.surveys.edit.amount_in_cents")}</p>
        </div>
      </div>

      {/* Stripe Connect Configuration — replaces the manual publishable key input */}
      <div className="mt-3 space-y-3">
        <Label>{t("environments.surveys.edit.stripe_configuration")}</Label>

        {stripeConnectStatus === "loading" && (
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
            <span className="text-sm text-slate-500">
              {t("environments.surveys.edit.checking_stripe_status")}
            </span>
          </div>
        )}

        {stripeConnectStatus === "connected" && (
          <div className="rounded-lg border border-green-200 bg-green-50 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2Icon className="h-5 w-5 text-green-600" />
                <div>
                  <p className="text-sm font-medium text-green-800">
                    {t("environments.surveys.edit.stripe_connected")}
                  </p>
                  {stripeConnectAccountId && (
                    <p className="text-xs text-green-600">
                      {t("environments.surveys.edit.account_id")}: {stripeConnectAccountId}
                    </p>
                  )}
                </div>
              </div>
              <Button
                type="button"
                variant="destructive"
                size="sm"
                onClick={handleDisconnectStripe}
                disabled={isDisconnecting}>
                <UnplugIcon className="mr-1 h-4 w-4" />
                {isDisconnecting
                  ? t("environments.surveys.edit.disconnecting")
                  : t("environments.surveys.edit.disconnect_stripe")}
              </Button>
            </div>
          </div>
        )}

        {stripeConnectStatus === "disconnected" && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <LinkIcon className="h-5 w-5 text-slate-400" />
                <div>
                  <p className="text-sm font-medium text-slate-700">
                    {t("environments.surveys.edit.no_stripe_account")}
                  </p>
                  <p className="text-xs text-slate-500">
                    {t("environments.surveys.edit.connect_stripe_description")}
                  </p>
                </div>
              </div>
              <Button type="button" size="sm" onClick={handleConnectStripe}>
                <ExternalLinkIcon className="mr-1 h-4 w-4" />
                {t("environments.surveys.edit.connect_stripe")}
              </Button>
            </div>
          </div>
        )}
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
