import type { Meta, StoryObj } from "@storybook/react";
import * as React from "react";
import {
  type BaseStylingOptions,
  type LabelStylingOptions,
  commonArgTypes,
  createCSSVariablesDecorator,
  createStatefulRender,
  elementStylingArgTypes,
  labelStylingArgTypes,
  pickArgTypes,
  surveyStylingArgTypes,
} from "../../lib/story-helpers";
import { OpinionScaleElement } from "./opinion-scale";

type StoryProps = React.ComponentPropsWithoutRef<typeof OpinionScaleElement> &
  Partial<BaseStylingOptions & LabelStylingOptions> &
  Record<string, unknown>;

const meta: Meta<StoryProps> = {
  title: "UI-package/Elements/OpinionScale",
  component: OpinionScaleElement as React.ComponentType<StoryProps>,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "An opinion scale element that presents respondents with a configurable numeric scale (5, 7, or 10) with customisable endpoint labels and visual styles (number, smiley, star).",
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
    visualStyle: {
      control: { type: "select" },
      options: ["number", "smiley", "star"],
      description: "Visual presentation style",
      table: { category: "Content" },
    },
    isColorCodingEnabled: {
      control: "boolean",
      description: "Whether to show colour coding on the scale",
      table: { category: "Content" },
    },
    ...pickArgTypes(elementStylingArgTypes, "elementBackgroundColor", "elementBorderColor"),
    ...pickArgTypes(labelStylingArgTypes, "headlineColor", "descriptionColor"),
    ...surveyStylingArgTypes,
  },
};

export default meta;
type Story = StoryObj<StoryProps>;

const render = createStatefulRender<StoryProps, number>({
  mapPropToState: (props) => (props as Record<string, number>).value ?? undefined,
  renderComponent: (props, val, setVal) => (
    <OpinionScaleElement
      {...(props as React.ComponentPropsWithoutRef<typeof OpinionScaleElement>)}
      value={val}
      onChange={setVal}
    />
  ),
});

export const Default: Story = {
  args: {
    elementId: "os-default",
    headline: "How satisfied are you?",
    description: "Please rate your experience.",
    scaleRange: 5,
    lowerLabel: "Not at all",
    upperLabel: "Extremely",
    visualStyle: "number",
    isColorCodingEnabled: false,
    required: true,
    languageCode: "en",
  },
  render,
  decorators: [createCSSVariablesDecorator({})],
};

export const SevenPointSmiley: Story = {
  args: {
    ...Default.args,
    elementId: "os-smiley",
    scaleRange: 7,
    visualStyle: "smiley",
    isColorCodingEnabled: true,
  },
  render,
  decorators: [createCSSVariablesDecorator({})],
};

export const TenPointStar: Story = {
  args: {
    ...Default.args,
    elementId: "os-star",
    scaleRange: 10,
    visualStyle: "star",
  },
  render,
  decorators: [createCSSVariablesDecorator({})],
};

export const WithError: Story = {
  args: {
    ...Default.args,
    elementId: "os-error",
    errorMessage: "Please select a value.",
  },
  render,
  decorators: [createCSSVariablesDecorator({})],
};

export const RTL: Story = {
  args: {
    ...Default.args,
    elementId: "os-rtl",
    dir: "rtl",
    lowerLabel: "لا على الإطلاق",
    upperLabel: "بشكل كبير",
  },
  render,
  decorators: [createCSSVariablesDecorator({})],
};
