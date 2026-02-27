"use client";

import Link from "next/link";
import { useTranslation } from "react-i18next";
import { TSurvey, TSurveyElementSummaryOpinionScale } from "@formbricks/types/surveys/types";
import { TUserLocale } from "@formbricks/types/user";
import { timeSince } from "@/lib/time";
import { getContactIdentifier } from "@/lib/utils/contact";
import { PersonAvatar } from "@/modules/ui/components/avatars";
import { EmptyState } from "@/modules/ui/components/empty-state";
import { ElementSummaryHeader } from "./ElementSummaryHeader";

interface OpinionScaleSummaryProps {
  elementSummary: TSurveyElementSummaryOpinionScale;
  environmentId: string;
  survey: TSurvey;
  locale: TUserLocale;
}

export const OpinionScaleSummary = ({
  elementSummary,
  environmentId,
  survey,
  locale,
}: OpinionScaleSummaryProps) => {
  const { t } = useTranslation();
  const { overall } = elementSummary;

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <ElementSummaryHeader elementSummary={elementSummary} survey={survey} />

      {/* Aggregate stats */}
      {overall && (
        <div className="grid grid-cols-3 gap-4 border-b border-slate-200 p-4 text-center">
          <div>
            <p className="text-sm text-slate-500">{t("common.mean")}</p>
            <p className="text-lg font-semibold">{overall.mean.toFixed(2)}</p>
          </div>
          <div>
            <p className="text-sm text-slate-500">{t("common.median")}</p>
            <p className="text-lg font-semibold">{overall.median.toFixed(1)}</p>
          </div>
          <div>
            <p className="text-sm text-slate-500">{t("common.responses")}</p>
            <p className="text-lg font-semibold">{elementSummary.responseCount}</p>
          </div>
        </div>
      )}

      {/* Distribution bar chart */}
      {overall?.distribution && (
        <div className="border-b border-slate-200 p-4">
          <div className="flex items-end gap-1" style={{ height: 80 }}>
            {Object.entries(overall.distribution)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([key, count]) => {
                const maxCount = Math.max(...Object.values(overall.distribution), 1);
                const heightPct = (count / maxCount) * 100;
                return (
                  <div key={key} className="flex flex-1 flex-col items-center gap-1">
                    <div
                      className="bg-brand w-full rounded-t"
                      style={{ height: `${heightPct}%`, minHeight: count > 0 ? 4 : 0 }}
                    />
                    <span className="text-xs text-slate-500">{key}</span>
                  </div>
                );
              })}
          </div>
        </div>
      )}

      {/* Samples table */}
      <div>
        <div className="grid h-10 grid-cols-4 items-center border-y border-slate-200 bg-slate-100 text-sm font-bold text-slate-600">
          <div className="pl-4 md:pl-6">{t("common.user")}</div>
          <div className="col-span-2 pl-4 md:pl-6">{t("common.response")}</div>
          <div className="px-4 md:px-6">{t("common.time")}</div>
        </div>
        <div className="max-h-[62vh] w-full overflow-y-auto">
          {elementSummary.samples.length === 0 ? (
            <div className="p-8">
              <EmptyState text={t("environments.surveys.summary.no_responses_found")} variant="simple" />
            </div>
          ) : (
            elementSummary.samples.map((response) => (
              <div
                key={response.id}
                className="grid grid-cols-4 items-center border-b border-slate-100 py-2 text-sm text-slate-800 last:border-transparent md:text-base">
                <div className="pl-4 md:pl-6">
                  {response.contact ? (
                    <Link
                      className="ph-no-capture group flex items-center"
                      href={`/environments/${environmentId}/contacts/${response.contact.id}`}>
                      <div className="hidden md:flex">
                        <PersonAvatar personId={response.contact.id} />
                      </div>
                      <p className="ph-no-capture break-all text-slate-600 group-hover:underline md:ml-2">
                        {getContactIdentifier(response.contact, response.contactAttributes)}
                      </p>
                    </Link>
                  ) : (
                    <div className="group flex items-center">
                      <div className="hidden md:flex">
                        <PersonAvatar personId="anonymous" />
                      </div>
                      <p className="break-all text-slate-600 md:ml-2">{t("common.anonymous")}</p>
                    </div>
                  )}
                </div>
                <div className="ph-no-capture col-span-2 whitespace-pre-wrap pl-6 font-semibold">
                  {response.value}
                </div>
                <div className="px-4 text-slate-500 md:px-6">
                  {timeSince(new Date(response.updatedAt).toISOString(), locale)}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
