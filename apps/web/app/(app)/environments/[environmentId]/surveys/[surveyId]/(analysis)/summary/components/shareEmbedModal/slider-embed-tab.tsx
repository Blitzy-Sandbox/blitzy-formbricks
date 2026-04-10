"use client";

import { CopyIcon } from "lucide-react";
import { useState } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { AdvancedOptionToggle } from "@/modules/ui/components/advanced-option-toggle";
import { Button } from "@/modules/ui/components/button";
import { CodeBlock } from "@/modules/ui/components/code-block";

interface SliderEmbedTabProps {
  surveyUrl: string;
  environmentId: string;
}

export const SliderEmbedTab = ({ surveyUrl, environmentId }: SliderEmbedTabProps) => {
  const { t } = useTranslation();
  const [direction, setDirection] = useState<"left" | "right">("right");
  const [width, setWidth] = useState<number>(400);
  const [animation, setAnimation] = useState<number>(300);
  const [showAnimationSettings, setShowAnimationSettings] = useState(false);

  const MIN_WIDTH = 200;
  const MAX_WIDTH = 1200;

  let apiHost = surveyUrl;
  try {
    const parsedUrl = new URL(surveyUrl);
    apiHost = parsedUrl.origin;
  } catch {
    // If the URL is malformed, fall back to the raw surveyUrl
  }

  const snippetCode = `<script type="text/javascript">
!function(){var e=document.createElement("script");e.src="https://unpkg.com/@formbricks/js@latest/dist/index.umd.js";
e.async=true;document.head.appendChild(e);e.onload=function(){
window.formbricks.init({
  environmentId: "${environmentId}",
  apiHost: "${apiHost}",
  embedMode: "slider",
  sliderConfig: {
    direction: "${direction}",
    width: "${width}px",
    animation: ${animation}
  }
})}}();
</script>`;

  return (
    <>
      <CodeBlock language="html" noMargin>
        {snippetCode}
      </CodeBlock>

      <div className="mt-4 flex flex-col gap-2 pl-1">
        <span className="text-sm font-semibold text-slate-700">
          {t("environments.surveys.share.slider_embed.direction")}
        </span>
        <div className="flex items-center gap-4">
          <label className="flex cursor-pointer items-center gap-1.5 text-sm text-slate-600">
            <input
              type="radio"
              name="sliderDirection"
              value="left"
              checked={direction === "left"}
              onChange={() => setDirection("left")}
              className="h-4 w-4 border-slate-300 text-slate-800 focus:ring-slate-500"
            />
            {t("environments.surveys.share.slider_embed.direction_left")}
          </label>
          <label className="flex cursor-pointer items-center gap-1.5 text-sm text-slate-600">
            <input
              type="radio"
              name="sliderDirection"
              value="right"
              checked={direction === "right"}
              onChange={() => setDirection("right")}
              className="h-4 w-4 border-slate-300 text-slate-800 focus:ring-slate-500"
            />
            {t("environments.surveys.share.slider_embed.direction_right")}
          </label>
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-2 pl-1">
        <label htmlFor="sliderWidth" className="text-sm font-semibold text-slate-700">
          {t("environments.surveys.share.slider_embed.width")}
        </label>
        <input
          id="sliderWidth"
          type="number"
          min={MIN_WIDTH}
          max={MAX_WIDTH}
          value={width}
          onChange={(e) => setWidth(Number(e.target.value))}
          onBlur={() => {
            if (width < MIN_WIDTH) setWidth(MIN_WIDTH);
            else if (width > MAX_WIDTH) setWidth(MAX_WIDTH);
          }}
          className="w-32 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
        />
      </div>

      <AdvancedOptionToggle
        htmlId="sliderAnimationDuration"
        isChecked={showAnimationSettings}
        onToggle={setShowAnimationSettings}
        title={t("environments.surveys.share.slider_embed.animation_settings")}
        description={t("environments.surveys.share.slider_embed.animation_settings_description")}
        customContainerClass="pl-1 pr-0 py-0">
        <div className="flex w-full items-center gap-3 px-3 py-2">
          <label htmlFor="sliderAnimationDuration-input" className="whitespace-nowrap text-sm text-slate-600">
            {t("environments.surveys.share.slider_embed.animation_duration")}
          </label>
          <input
            id="sliderAnimationDuration-input"
            type="number"
            min={0}
            max={2000}
            value={animation}
            onChange={(e) => setAnimation(Number(e.target.value))}
            className="w-24 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
          />
        </div>
      </AdvancedOptionToggle>

      <Button
        className="self-start"
        title={t("common.copy_code")}
        aria-label={t("common.copy_code")}
        onClick={() => {
          navigator.clipboard.writeText(snippetCode);
          toast.success(t("environments.surveys.share.slider_embed.embed_code_copied_to_clipboard"));
        }}>
        {t("common.copy_code")}
        <CopyIcon />
      </Button>
    </>
  );
};
