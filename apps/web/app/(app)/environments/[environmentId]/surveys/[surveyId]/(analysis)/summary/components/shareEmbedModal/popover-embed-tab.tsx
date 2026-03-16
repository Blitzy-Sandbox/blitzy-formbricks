"use client";

import { CopyIcon } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { AdvancedOptionToggle } from "@/modules/ui/components/advanced-option-toggle";
import { Button } from "@/modules/ui/components/button";
import { CodeBlock } from "@/modules/ui/components/code-block";

interface PopoverEmbedTabProps {
  surveyUrl: string;
}

export const PopoverEmbedTab = ({ surveyUrl }: PopoverEmbedTabProps) => {
  const { t } = useTranslation();
  const [buttonPosition, setButtonPosition] = useState<string>("bottom-right");
  const [buttonColor, setButtonColor] = useState<string>("#00C4B8");
  const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
  const [formWidth, setFormWidth] = useState<number>(400);
  const [formHeight, setFormHeight] = useState<number>(500);

  let environmentId = "YOUR_ENVIRONMENT_ID";
  let apiHost = surveyUrl;
  try {
    const urlObj = new URL(surveyUrl);
    const pathSegments = urlObj.pathname.split("/").filter(Boolean);
    if (pathSegments.length >= 2) {
      environmentId = pathSegments[pathSegments.length - 2];
    }
    apiHost = urlObj.origin;
  } catch {
    // If the URL is malformed, fall back to defaults
  }

  const snippetCode = `<script type="text/javascript">
!function(){var e=document.createElement("script");e.src="https://unpkg.com/@formbricks/js@latest/dist/index.umd.js";
e.async=true;document.head.appendChild(e);e.onload=function(){
window.formbricks.init({
  environmentId: "${environmentId}",
  apiHost: "${apiHost}",
  embedMode: "popover",
  popoverConfig: {
    buttonPosition: "${buttonPosition}",
    color: "${buttonColor}",
    formWidth: "${formWidth}px",
    formHeight: "${formHeight}px"
  }
})}}();
</script>`;

  return (
    <>
      <CodeBlock language="html" noMargin>
        {snippetCode}
      </CodeBlock>

      <div className="mt-4 flex flex-col gap-3 px-1">
        <div className="flex flex-col gap-1">
          <label htmlFor="popoverButtonPosition" className="text-sm font-semibold text-slate-700">
            {t("environments.surveys.share.popover_embed.button_position")}
          </label>
          <select
            id="popoverButtonPosition"
            className="focus-visible:ring-ring rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus-visible:outline-none focus-visible:ring-1"
            value={buttonPosition}
            onChange={(e) => setButtonPosition(e.target.value)}>
            <option value="bottom-right">
              {t("environments.surveys.share.popover_embed.position_bottom_right")}
            </option>
            <option value="bottom-left">
              {t("environments.surveys.share.popover_embed.position_bottom_left")}
            </option>
            <option value="top-right">
              {t("environments.surveys.share.popover_embed.position_top_right")}
            </option>
            <option value="top-left">
              {t("environments.surveys.share.popover_embed.position_top_left")}
            </option>
          </select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="popoverButtonColor" className="text-sm font-semibold text-slate-700">
            {t("environments.surveys.share.popover_embed.button_color")}
          </label>
          <div className="flex items-center gap-2">
            <input
              type="color"
              id="popoverButtonColor"
              className="h-8 w-8 cursor-pointer rounded border border-slate-300"
              value={buttonColor}
              onChange={(e) => setButtonColor(e.target.value)}
            />
            <input
              type="text"
              className="focus-visible:ring-ring rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus-visible:outline-none focus-visible:ring-1"
              value={buttonColor}
              onChange={(e) => {
                const value = e.target.value;
                if (/^#[0-9A-Fa-f]{0,6}$/.test(value) || value === "") {
                  setButtonColor(value);
                }
              }}
              aria-label={t("environments.surveys.share.popover_embed.button_color")}
            />
          </div>
        </div>
      </div>

      <AdvancedOptionToggle
        htmlId="popoverFormDimensions"
        isChecked={showAdvancedSettings}
        onToggle={setShowAdvancedSettings}
        title={t("environments.surveys.share.popover_embed.form_dimensions")}
        description={t("environments.surveys.share.popover_embed.form_dimensions_description")}
        customContainerClass="pl-1 pr-0 py-0">
        <div className="flex w-full items-center gap-4 p-4">
          <div className="flex flex-1 flex-col gap-1">
            <label htmlFor="popoverFormWidth" className="text-sm font-semibold text-slate-700">
              {t("environments.surveys.share.popover_embed.form_width")}
            </label>
            <input
              type="number"
              id="popoverFormWidth"
              className="focus-visible:ring-ring rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus-visible:outline-none focus-visible:ring-1"
              value={formWidth}
              min={200}
              max={800}
              onChange={(e) => setFormWidth(Number(e.target.value))}
            />
          </div>
          <div className="flex flex-1 flex-col gap-1">
            <label htmlFor="popoverFormHeight" className="text-sm font-semibold text-slate-700">
              {t("environments.surveys.share.popover_embed.form_height")}
            </label>
            <input
              type="number"
              id="popoverFormHeight"
              className="focus-visible:ring-ring rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 focus-visible:outline-none focus-visible:ring-1"
              value={formHeight}
              min={200}
              max={900}
              onChange={(e) => setFormHeight(Number(e.target.value))}
            />
          </div>
        </div>
      </AdvancedOptionToggle>

      <Button
        className="self-start"
        title={t("common.copy_code")}
        aria-label={t("common.copy_code")}
        onClick={() => {
          navigator.clipboard.writeText(snippetCode);
          toast.success(t("environments.surveys.share.popover_embed.embed_code_copied_to_clipboard"));
        }}>
        {t("common.copy_code")}
        <CopyIcon />
      </Button>
    </>
  );
};
