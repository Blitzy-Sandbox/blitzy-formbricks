import type { Meta, StoryObj } from "@storybook/react";
import {
  type BaseStylingOptions,
  type InputLayoutStylingOptions,
  commonArgTypes,
  createCSSVariablesDecorator,
  createStatefulRender,
  elementStylingArgTypes,
  inputStylingArgTypes,
  pickArgTypes,
  surveyStylingArgTypes,
} from "../../lib/story-helpers";
import { TypeBElement, type TypeBElementProps } from "./type-b-element";

type StoryProps = TypeBElementProps &
  Partial<BaseStylingOptions & InputLayoutStylingOptions> &
  Record<string, unknown>;

const meta: Meta<StoryProps> = {
  title: "UI-package/Elements/TypeBElement",
  component: TypeBElement,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component: "A TypeB survey element that collects text input from respondents.",
      },
    },
  },
  tags: ["autodocs"],
  argTypes: {
    ...commonArgTypes,
    placeholder: {
      control: "text",
      description: "Placeholder text for the input field",
      table: { category: "Content" },
    },
    value: {
      control: "text",
      description: "Current input value",
      table: { category: "State" },
    },
  },
  render: createStatefulRender(TypeBElement),
};

export default meta;
type Story = StoryObj<StoryProps>;

export const StylingPlayground: Story = {
  args: {
    elementId: "type-b-1",
    inputId: "type-b-input-1",
    headline: "TypeB Element Question",
    description: "Please provide your answer below",
    placeholder: "Type your answer here...",
    onChange: () => {},
  },
  argTypes: {
    ...elementStylingArgTypes,
    ...pickArgTypes(inputStylingArgTypes, [
      "inputBgColor",
      "inputBorderColor",
      "inputColor",
      "inputFontSize",
      "inputFontWeight",
      "inputWidth",
      "inputHeight",
      "inputBorderRadius",
      "inputPlaceholderColor",
      "inputPaddingX",
      "inputPaddingY",
    ]),
    ...surveyStylingArgTypes,
  },
  decorators: [createCSSVariablesDecorator<StoryProps>()],
};

export const Default: Story = {
  args: {
    elementId: "type-b-1",
    inputId: "type-b-input-1",
    headline: "What is your answer?",
    placeholder: "Type your answer here...",
    onChange: () => {},
  },
};

export const WithDescription: Story = {
  args: {
    elementId: "type-b-2",
    inputId: "type-b-input-2",
    headline: "What is your answer?",
    description: "Please provide a detailed response",
    placeholder: "Type your answer here...",
    onChange: () => {},
  },
};

export const WithValue: Story = {
  args: {
    elementId: "type-b-3",
    inputId: "type-b-input-3",
    headline: "What is your answer?",
    placeholder: "Type your answer here...",
    value: "Sample response text",
    onChange: () => {},
  },
};

export const Required: Story = {
  args: {
    elementId: "type-b-4",
    inputId: "type-b-input-4",
    headline: "What is your answer?",
    placeholder: "Type your answer here...",
    required: true,
    onChange: () => {},
  },
};

export const WithError: Story = {
  args: {
    elementId: "type-b-5",
    inputId: "type-b-input-5",
    headline: "What is your answer?",
    placeholder: "Type your answer here...",
    required: true,
    errorMessage: "This field is required",
    onChange: () => {},
  },
};

export const Disabled: Story = {
  args: {
    elementId: "type-b-6",
    inputId: "type-b-input-6",
    headline: "This field is disabled",
    description: "You cannot edit this field",
    placeholder: "Disabled input",
    disabled: true,
    onChange: () => {},
  },
};

export const RTL: Story = {
  args: {
    elementId: "type-b-rtl",
    inputId: "type-b-input-rtl",
    headline: "ما هو جوابك؟",
    description: "يرجى تقديم إجابتك",
    placeholder: "اكتب إجابتك هنا...",
    dir: "rtl",
    onChange: () => {},
  },
};

export const MultipleElements: Story = {
  render: () => (
    <div className="w-[600px] space-y-8">
      <TypeBElement
        elementId="type-b-1"
        inputId="type-b-input-1"
        headline="First question"
        description="Please answer this question"
        placeholder="Type your answer here..."
        onChange={() => {}}
      />
      <TypeBElement
        elementId="type-b-2"
        inputId="type-b-input-2"
        headline="Second question"
        placeholder="Type your answer here..."
        required
        onChange={() => {}}
      />
    </div>
  ),
};
