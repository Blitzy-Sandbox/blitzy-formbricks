"use client";

import { CopyIcon } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { Button } from "@/modules/ui/components/button";
import { CodeBlock } from "@/modules/ui/components/code-block";

interface SideTabEmbedTabProps {
  surveyUrl: string;
}

export const SideTabEmbedTab = ({ surveyUrl }: SideTabEmbedTabProps) => {
  const { t } = useTranslation();
  const [tabLabel, setTabLabel] = useState<string>("Feedback");
  const [position, setPosition] = useState<"left" | "right">("right");
  const [tabColor, setTabColor] = useState<string>("#00C4B8");

  let apiHost = surveyUrl;
  let environmentId = "YOUR_ENVIRONMENT_ID";
  try {
    const urlObj = new URL(surveyUrl);
    apiHost = urlObj.origin;
    const pathSegments = urlObj.pathname.split("/").filter(Boolean);
    if (pathSegments.length >= 2) {
      environmentId = pathSegments[pathSegments.length - 2];
    }
  } catch {
    // If the URL is malformed, fall back to defaults
  }

  const snippetCode = `<script type="text/javascript">
!function(){var e=document.createElement("script");e.src="https://unpkg.com/@formbricks/js@latest/dist/index.umd.js";
e.async=true;document.head.appendChild(e);e.onload=function(){
window.formbricks.init({
  environmentId: "${environmentId}",
  apiHost: "${apiHost}",
  embedMode: "sideTab",
  sideTabConfig: {
    tabLabel: "${tabLabel}",
    position: "${position}",
    color: "${tabColor}"
  }
})}}();
</script>`;

  return (
    <>
      <CodeBlock language="html" noMargin>
        {snippetCode}
      </CodeBlock>

      <div className="flex flex-col gap-1">
        <label htmlFor="sideTabLabel" className="text-sm font-semibold text-slate-700">
          {t("environments.surveys.share.side_tab_embed.tab_label")}
        </label>
        <input
          id="sideTabLabel"
          type="text"
          value={tabLabel}
          onChange={(e) => setTabLabel(e.target.value)}
          className="focus:border-brand-dark flex h-10 w-full rounded-md border border-slate-300 bg-transparent px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
        />
      </div>

      <fieldset className="flex flex-col gap-1">
        <legend className="text-sm font-semibold text-slate-700">
          {t("environments.surveys.share.side_tab_embed.position")}
        </legend>
        <div className="flex items-center gap-4">
          <label
            htmlFor="positionLeft"
            className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
            <input
              id="positionLeft"
              type="radio"
              name="sideTabPosition"
              value="left"
              checked={position === "left"}
              onChange={() => setPosition("left")}
              className="text-brand focus:ring-brand-dark h-4 w-4 border-slate-300"
            />
            {t("environments.surveys.share.side_tab_embed.position_left")}
          </label>
          <label
            htmlFor="positionRight"
            className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
            <input
              id="positionRight"
              type="radio"
              name="sideTabPosition"
              value="right"
              checked={position === "right"}
              onChange={() => setPosition("right")}
              className="text-brand focus:ring-brand-dark h-4 w-4 border-slate-300"
            />
            {t("environments.surveys.share.side_tab_embed.position_right")}
          </label>
        </div>
      </fieldset>

      <div className="flex flex-col gap-1">
        <label htmlFor="sideTabColor" className="text-sm font-semibold text-slate-700">
          {t("environments.surveys.share.side_tab_embed.tab_color")}
        </label>
        <div className="flex items-center gap-2">
          <input
            id="sideTabColor"
            type="color"
            value={tabColor}
            onChange={(e) => setTabColor(e.target.value)}
            className="h-10 w-10 cursor-pointer rounded-md border border-slate-300"
          />
          <input
            type="text"
            value={tabColor}
            onChange={(e) => {
              const value = e.target.value;
              if (/^#[0-9A-Fa-f]{0,6}$/.test(value) || value === "") {
                setTabColor(value);
              }
            }}
            aria-label={t("environments.surveys.share.side_tab_embed.tab_color")}
            className="focus:border-brand-dark flex h-10 w-full rounded-md border border-slate-300 bg-transparent px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>
      </div>

      <Button
        className="self-start"
        title={t("common.copy_code")}
        aria-label={t("common.copy_code")}
        onClick={() => {
          navigator.clipboard.writeText(snippetCode);
          toast.success(t("environments.surveys.share.side_tab_embed.embed_code_copied_to_clipboard"));
        }}>
        {t("common.copy_code")}
        <CopyIcon />
      </Button>
    </>
  );
};
