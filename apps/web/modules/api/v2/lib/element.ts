import { TResponseData } from "@formbricks/types/responses";
import {
  TSurveyElement,
  TSurveyElementTypeEnum,
  TSurveyOpinionScaleElement,
  TSurveyPaymentElement,
} from "@formbricks/types/surveys/elements";
import { TSurveyQuestionChoice } from "@formbricks/types/surveys/types";
import { MAX_OTHER_OPTION_LENGTH } from "@/lib/constants";
import { getLocalizedValue } from "@/lib/i18n/utils";

/**
 * Helper function to check if a string value is a valid "other" option
 * @returns BadRequestResponse if the value exceeds the limit, undefined otherwise
 */
export const validateOtherOptionLength = (
  value: string,
  choices: TSurveyQuestionChoice[],
  questionId: string,
  language?: string
): string | undefined => {
  // Check if this is an "other" option (not in predefined choices)
  const matchingChoice = choices.find(
    (choice) => getLocalizedValue(choice.label, language ?? "default") === value
  );

  // If this is an "other" option with value that's too long, reject the response
  if (!matchingChoice && value.length > MAX_OTHER_OPTION_LENGTH) {
    return questionId;
  }
};

export const validateOtherOptionLengthForMultipleChoice = ({
  responseData,
  surveyQuestions,
  responseLanguage,
}: {
  responseData?: TResponseData;
  surveyQuestions: TSurveyElement[];
  responseLanguage?: string;
}): string | undefined => {
  if (!responseData) return undefined;
  for (const [questionId, answer] of Object.entries(responseData)) {
    const question = surveyQuestions.find((q) => q.id === questionId);
    if (!question) continue;

    const isMultiChoice =
      question.type === TSurveyElementTypeEnum.MultipleChoiceMulti ||
      question.type === TSurveyElementTypeEnum.MultipleChoiceSingle;

    if (!isMultiChoice) continue;

    const error = validateAnswer(answer, question.choices, questionId, responseLanguage);
    if (error) return error;
  }

  return undefined;
};

function validateAnswer(
  answer: unknown,
  choices: TSurveyQuestionChoice[],
  questionId: string,
  language?: string
): string | undefined {
  if (typeof answer === "string") {
    return validateOtherOptionLength(answer, choices, questionId, language);
  }

  if (Array.isArray(answer)) {
    for (const item of answer) {
      if (typeof item === "string") {
        const result = validateOtherOptionLength(item, choices, questionId, language);
        if (result) return result;
      }
    }
  }

  return undefined;
}

/**
 * Type guard to check if a survey element is an Opinion Scale element.
 * Useful for API v2 response formatting dispatch.
 */
export const isOpinionScaleElement = (element: TSurveyElement): element is TSurveyOpinionScaleElement => {
  return element.type === TSurveyElementTypeEnum.OpinionScale;
};

/**
 * Type guard to check if a survey element is a Payment element.
 * Useful for API v2 response formatting dispatch.
 */
export const isPaymentElement = (element: TSurveyElement): element is TSurveyPaymentElement => {
  return element.type === TSurveyElementTypeEnum.Payment;
};

/**
 * Formats an Opinion Scale response value for API v2 response payloads.
 * Opinion Scale values are numeric (1 to scaleRange), similar to Rating elements.
 * The function ensures robustness by handling both number and string inputs
 * (survey responses can arrive as strings from URL-encoded form data).
 * @param value - The raw response value for an opinion scale element
 * @returns The formatted numeric value, or null if the value is invalid
 */
export const formatOpinionScaleResponse = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    if (!Number.isNaN(parsed) && Number.isFinite(parsed)) {
      return parsed;
    }
  }

  return null;
};

/**
 * Formats a Payment response value for API v2 response payloads.
 * Payment responses contain a status ("paid" or "skipped"), and optionally the amount and currency.
 * Follows the pattern of status-based elements like Consent and CTA.
 * @param value - The raw response value for a payment element
 * @returns The formatted payment response object, or the raw value if it cannot be parsed
 */
export const formatPaymentResponse = (
  value: unknown
): { status: string; amount?: number; currency?: string } | string => {
  if (typeof value === "object" && value !== null) {
    const obj = value as Record<string, unknown>;
    const status = typeof obj.status === "string" ? obj.status : "skipped";
    const result: { status: string; amount?: number; currency?: string } = { status };

    if (typeof obj.amount === "number") {
      result.amount = obj.amount;
    }

    if (typeof obj.currency === "string") {
      result.currency = obj.currency;
    }

    return result;
  }

  if (typeof value === "string") {
    return value;
  }

  return { status: "skipped" };
};
