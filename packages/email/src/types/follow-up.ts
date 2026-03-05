import { TSurveyElementTypeEnum } from "@formbricks/types/surveys/elements";

export interface ProcessedResponseElement {
  element: string;
  response: string | string[];
  type: TSurveyElementTypeEnum;
  metadata?: {
    currency?: string;
    paymentStatus?: string;
  };
}

export interface ProcessedVariable {
  id: string;
  name: string;
  type: "text" | "number";
  value: string | number;
}

export interface ProcessedHiddenField {
  id: string;
  value: string;
}
