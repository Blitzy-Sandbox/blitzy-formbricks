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
import { PaymentElement } from "./payment";

type StoryProps = React.ComponentPropsWithoutRef<typeof PaymentElement> &
  Partial<BaseStylingOptions & LabelStylingOptions> &
  Record<string, unknown>;

const meta: Meta<StoryProps> = {
  title: "UI-package/Elements/Payment",
  component: PaymentElement as React.ComponentType<StoryProps>,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "A payment element that collects payments via Stripe during the survey flow. Respondents can view the amount and currency, then click to pay.",
      },
    },
  },
  tags: ["autodocs"],
  argTypes: {
    ...commonArgTypes,
    currency: {
      control: { type: "select" },
      options: ["usd", "eur", "gbp"],
      description: "Currency for the payment (ISO 4217 lowercase)",
      table: { category: "Content" },
    },
    amount: {
      control: { type: "number", min: 1 },
      description: "Amount in smallest currency unit (e.g. cents)",
      table: { category: "Content" },
    },
    buttonLabel: {
      control: "text",
      description: "Label for the pay button",
      table: { category: "Content" },
    },
    ...pickArgTypes(elementStylingArgTypes, "elementBackgroundColor", "elementBorderColor"),
    ...pickArgTypes(labelStylingArgTypes, "headlineColor", "descriptionColor"),
    ...surveyStylingArgTypes,
  },
};

export default meta;
type Story = StoryObj<StoryProps>;

const render = createStatefulRender<StoryProps, string>({
  mapPropToState: (props) => (props as Record<string, string>).value ?? "",
  renderComponent: (props, val, setVal) => (
    <PaymentElement
      {...(props as React.ComponentPropsWithoutRef<typeof PaymentElement>)}
      value={val}
      onChange={setVal}
    />
  ),
});

export const Default: Story = {
  args: {
    elementId: "payment-default",
    headline: "Complete your payment",
    description: "Please pay the amount below to continue.",
    currency: "usd",
    amount: 2500,
    buttonLabel: "Pay now",
    required: true,
    languageCode: "en",
  },
  render,
  decorators: [createCSSVariablesDecorator({})],
};

export const EuroPayment: Story = {
  args: {
    ...Default.args,
    elementId: "payment-euro",
    currency: "eur",
    amount: 1500,
    buttonLabel: "Jetzt bezahlen",
  },
  render,
  decorators: [createCSSVariablesDecorator({})],
};

export const WithError: Story = {
  args: {
    ...Default.args,
    elementId: "payment-error",
    errorMessage: "Payment is required to continue.",
  },
  render,
  decorators: [createCSSVariablesDecorator({})],
};
