import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";
import {
  type BaseStylingOptions,
  type LabelStylingOptions,
  commonArgTypes,
  createCSSVariablesDecorator,
  createStatefulRender,
  elementStylingArgTypes,
  inputStylingArgTypes,
  labelStylingArgTypes,
  pickArgTypes,
  surveyStylingArgTypes,
} from "../../lib/story-helpers";
import { OpinionScale, type OpinionScaleProps } from "./opinion-scale";

type StoryProps = OpinionScaleProps &
  Partial<BaseStylingOptions & LabelStylingOptions> &
  Record<string, unknown>;

const meta: Meta<StoryProps> = {
  title: "UI-package/Elements/OpinionScale",
  component: OpinionScale,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "An opinion scale element that supports number, smiley, and star visual styles. Users select from a 1–N scale (5, 7, or 10 points) with customizable endpoint labels.",
      },
    },
  },
  tags: ["autodocs"],
  argTypes: {
    ...commonArgTypes,
    scaleRange: {
      control: { type: "select" },
      options: [5, 7, 10],
      description: "Number of scale points",
      table: { category: "Content" },
    },
    visualStyle: {
      control: { type: "select" },
      options: ["number", "smiley", "star"],
      description: "Visual rendering style",
      table: { category: "Content" },
    },
    value: {
      control: { type: "number", min: 1 },
      description: "Currently selected value",
      table: { category: "State" },
    },
    lowerLabel: {
      control: "text",
      description: "Label for the lower end of the scale",
      table: { category: "Content" },
    },
    upperLabel: {
      control: "text",
      description: "Label for the upper end of the scale",
      table: { category: "Content" },
    },
    isColorCodingEnabled: {
      control: "boolean",
      description: "Whether color coding gradient is enabled",
      table: { category: "Content" },
    },
  },
  render: createStatefulRender(OpinionScale),
};

export default meta;
type Story = StoryObj<StoryProps>;

export const StylingPlayground: Story = {
  args: {
    elementId: "opinion-scale-1",
    inputId: "opinion-scale-input-1",
    headline: "How would you rate this?",
    description: "Share your opinion",
    scaleRange: 5,
    visualStyle: "number",
    lowerLabel: "Strongly disagree",
    upperLabel: "Strongly agree",
    elementHeadlineFontFamily: "system-ui, sans-serif",
    elementHeadlineFontSize: "1.125rem",
    elementHeadlineFontWeight: "600",
    elementHeadlineColor: "#1e293b",
    elementDescriptionFontFamily: "system-ui, sans-serif",
    elementDescriptionFontSize: "0.875rem",
    elementDescriptionFontWeight: "400",
    elementDescriptionColor: "#64748b",
    labelFontFamily: "system-ui, sans-serif",
    labelFontSize: "0.75rem",
    labelFontWeight: "400",
    labelColor: "#64748b",
    labelOpacity: "1",
  },
  argTypes: {
    ...elementStylingArgTypes,
    ...labelStylingArgTypes,
    ...pickArgTypes(inputStylingArgTypes, [
      "inputBgColor",
      "inputBorderColor",
      "inputColor",
      "inputFontWeight",
      "inputBorderRadius",
    ]),
    ...surveyStylingArgTypes,
  },
  decorators: [createCSSVariablesDecorator<StoryProps>()],
};

export const Default: Story = {
  args: {
    elementId: "opinion-scale-default",
    inputId: "opinion-scale-input-default",
    headline: "How would you rate this?",
    scaleRange: 5,
    visualStyle: "number",
  },
};

export const SevenPointRange: Story = {
  args: {
    elementId: "opinion-scale-7",
    inputId: "opinion-scale-input-7",
    headline: "Rate your agreement",
    scaleRange: 7,
    visualStyle: "number",
  },
};

export const TenPointRange: Story = {
  args: {
    elementId: "opinion-scale-10",
    inputId: "opinion-scale-input-10",
    headline: "Rate your experience",
    scaleRange: 10,
    visualStyle: "number",
  },
};

export const SmileyVisualStyle: Story = {
  args: {
    elementId: "opinion-scale-smiley",
    inputId: "opinion-scale-input-smiley",
    headline: "How do you feel?",
    scaleRange: 5,
    visualStyle: "smiley",
  },
};

export const StarVisualStyle: Story = {
  args: {
    elementId: "opinion-scale-star",
    inputId: "opinion-scale-input-star",
    headline: "Rate this product",
    scaleRange: 5,
    visualStyle: "star",
  },
};

export const ColorCodingEnabled: Story = {
  args: {
    elementId: "opinion-scale-color",
    inputId: "opinion-scale-input-color",
    headline: "Rate your satisfaction",
    scaleRange: 5,
    visualStyle: "number",
    isColorCodingEnabled: true,
  },
};

export const WithLabels: Story = {
  args: {
    elementId: "opinion-scale-labels",
    inputId: "opinion-scale-input-labels",
    headline: "Rate your agreement",
    scaleRange: 5,
    visualStyle: "number",
    lowerLabel: "Strongly disagree",
    upperLabel: "Strongly agree",
  },
};

export const RTL: Story = {
  args: {
    elementId: "opinion-scale-rtl",
    dir: "rtl",
    inputId: "opinion-scale-input-rtl",
    headline: "كيف تقيم تجربتك؟",
    description: "شاركنا رأيك",
    scaleRange: 5,
    visualStyle: "number",
    lowerLabel: "غير موافق",
    upperLabel: "موافق تماماً",
  },
};

export const Disabled: Story = {
  args: {
    elementId: "opinion-scale-disabled",
    inputId: "opinion-scale-input-disabled",
    headline: "Rate your experience",
    scaleRange: 5,
    visualStyle: "number",
    value: 3,
    disabled: true,
  },
};

export const WithError: Story = {
  args: {
    elementId: "opinion-scale-error",
    inputId: "opinion-scale-input-error",
    headline: "Rate your experience",
    scaleRange: 5,
    visualStyle: "number",
    required: true,
    errorMessage: "Please select a value",
  },
};
