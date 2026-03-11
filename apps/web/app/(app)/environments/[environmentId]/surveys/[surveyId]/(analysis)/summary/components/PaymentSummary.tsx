"use client";

import { InboxIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { TSurvey, TSurveyElementSummaryPayment } from "@formbricks/types/surveys/types";
import { ProgressBar } from "@/modules/ui/components/progress-bar";
import { convertFloatToNDecimal } from "../lib/utils";
import { ElementSummaryHeader } from "./ElementSummaryHeader";

const formatCurrency = (amount: number, currency: string): string => {
  const displayAmount = amount / 100;
  const symbols: Record<string, string> = { usd: "$", eur: "€", gbp: "£" };
  const symbol = symbols[currency] || currency.toUpperCase();
  return `${symbol}${displayAmount.toFixed(2)}`;
};

interface PaymentSummaryProps {
  elementSummary: TSurveyElementSummaryPayment;
  survey: TSurvey;
}

export const PaymentSummary = ({ elementSummary, survey }: PaymentSummaryProps) => {
  const { t } = useTranslation();

  const totalCollected = formatCurrency(elementSummary.totalAmount, elementSummary.currency);
  const totalResponses = elementSummary.successCount + elementSummary.skippedCount;
  const successPercentage =
    totalResponses > 0 ? convertFloatToNDecimal((elementSummary.successCount / totalResponses) * 100, 2) : 0;
  const skippedPercentage =
    totalResponses > 0 ? convertFloatToNDecimal((elementSummary.skippedCount / totalResponses) * 100, 2) : 0;

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <ElementSummaryHeader
        survey={survey}
        elementSummary={elementSummary}
        showResponses={false}
        additionalInfo={
          <>
            <div className="flex items-center rounded-lg bg-slate-100 p-2">
              <InboxIcon className="mr-2 h-4 w-4" />
              {`${totalCollected} ${t("common.collected")}`}
            </div>
            <div className="flex items-center rounded-lg bg-slate-100 p-2">
              <InboxIcon className="mr-2 h-4 w-4" />
              {`${elementSummary.successCount} ${t("common.successful")}`}
            </div>
            {elementSummary.skippedCount > 0 && (
              <div className="flex items-center rounded-lg bg-slate-100 p-2">
                <InboxIcon className="mr-2 h-4 w-4" />
                {`${elementSummary.skippedCount} ${t("common.skipped")}`}
              </div>
            )}
          </>
        }
      />
      <div className="space-y-5 px-4 pb-6 pt-4 text-sm md:px-6 md:text-base">
        <div>
          <div className="text flex justify-between px-2 pb-2">
            <div className="mr-8 flex space-x-1">
              <p className="font-semibold text-slate-700">{t("common.successful")}</p>
              <div>
                <p className="rounded-lg bg-slate-100 px-2 text-slate-700">{successPercentage}%</p>
              </div>
            </div>
            <p className="flex w-32 items-end justify-end text-slate-600">
              {elementSummary.successCount}{" "}
              {elementSummary.successCount === 1 ? t("common.response") : t("common.responses")}
            </p>
          </div>
          <ProgressBar barColor="bg-brand-dark" progress={successPercentage / 100} />
        </div>
        {elementSummary.skippedCount > 0 && (
          <div>
            <div className="text flex justify-between px-2 pb-2">
              <div className="mr-8 flex space-x-1">
                <p className="font-semibold text-slate-700">{t("common.skipped")}</p>
                <div>
                  <p className="rounded-lg bg-slate-100 px-2 text-slate-700">{skippedPercentage}%</p>
                </div>
              </div>
              <p className="flex w-32 items-end justify-end text-slate-600">
                {elementSummary.skippedCount}{" "}
                {elementSummary.skippedCount === 1 ? t("common.response") : t("common.responses")}
              </p>
            </div>
            <ProgressBar barColor="bg-slate-300" progress={skippedPercentage / 100} />
          </div>
        )}
      </div>
    </div>
  );
};
