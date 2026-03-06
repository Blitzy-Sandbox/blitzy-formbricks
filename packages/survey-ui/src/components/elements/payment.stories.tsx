import type { Meta, StoryObj } from "@storybook/react";
import {
  type BaseStylingOptions,
  type ButtonStylingOptions,
  buttonStylingArgTypes,
  commonArgTypes,
  createCSSVariablesDecorator,
  elementStylingArgTypes,
} from "../../lib/story-helpers";
import { Payment, type PaymentProps } from "./payment";

type StoryProps = PaymentProps & Partial<BaseStylingOptions & ButtonStylingOptions> & Record<string, unknown>;

const meta: Meta<StoryProps> = {
  title: "UI-package/Elements/Payment",
  component: Payment,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "A payment element that displays an amount with currency and accepts card input via a children slot. Supports processing and success states.",
      },
    },
  },
  tags: ["autodocs"],
  argTypes: {
    ...commonArgTypes,
    currency: {
      control: { type: "select" },
      options: ["usd", "eur", "gbp"],
      description: "Payment currency",
      table: { category: "Content" },
    },
    amount: {
      control: { type: "number" },
      description: "Amount in smallest currency unit (cents/pence)",
      table: { category: "Content" },
    },
    buttonLabel: {
      control: "text",
      description: "Label for the submit button",
      table: { category: "Content" },
    },
    isProcessing: {
      control: "boolean",
      description: "Whether payment is being processed",
      table: { category: "State" },
    },
    isSuccess: {
      control: "boolean",
      description: "Whether payment was successful",
      table: { category: "State" },
    },
    onSubmit: {
      action: "submitted",
      table: { category: "Events" },
    },
    ...elementStylingArgTypes,
    ...buttonStylingArgTypes,
  },
  decorators: [createCSSVariablesDecorator<StoryProps>()],
};

export default meta;
type Story = StoryObj<StoryProps>;

export const Default: Story = {
  args: {
    elementId: "payment-1",
    inputId: "payment-input-1",
    headline: "Complete your payment",
    currency: "usd",
    amount: 1000,
    buttonLabel: "Pay $10.00",
    onSubmit: () => {
      alert("Payment submitted");
    },
  },
};

export const EURCurrency: Story = {
  args: {
    elementId: "payment-eur",
    inputId: "payment-input-eur",
    headline: "Complete your payment",
    currency: "eur",
    amount: 2500,
    buttonLabel: "Pay €25.00",
    onSubmit: () => {
      alert("Payment submitted");
    },
  },
};

export const GBPCurrency: Story = {
  args: {
    elementId: "payment-gbp",
    inputId: "payment-input-gbp",
    headline: "Complete your payment",
    currency: "gbp",
    amount: 1500,
    buttonLabel: "Pay £15.00",
    onSubmit: () => {
      alert("Payment submitted");
    },
  },
};

export const ProcessingState: Story = {
  args: {
    elementId: "payment-processing",
    inputId: "payment-input-processing",
    headline: "Processing payment",
    currency: "usd",
    amount: 1000,
    buttonLabel: "Pay $10.00",
    isProcessing: true,
    onSubmit: () => {},
  },
};

export const SuccessState: Story = {
  args: {
    elementId: "payment-success",
    inputId: "payment-input-success",
    headline: "Payment complete",
    currency: "usd",
    amount: 1000,
    buttonLabel: "Pay $10.00",
    isSuccess: true,
    onSubmit: () => {},
  },
};

export const ErrorState: Story = {
  args: {
    elementId: "payment-error",
    inputId: "payment-input-error",
    headline: "Complete your payment",
    currency: "usd",
    amount: 1000,
    buttonLabel: "Pay $10.00",
    errorMessage: "Your card was declined. Please try again.",
    onSubmit: () => {
      alert("Payment submitted");
    },
  },
};

export const Disabled: Story = {
  args: {
    elementId: "payment-disabled",
    inputId: "payment-input-disabled",
    headline: "Complete your payment",
    currency: "usd",
    amount: 1000,
    buttonLabel: "Pay $10.00",
    disabled: true,
    onSubmit: () => {},
  },
};

export const RTL: Story = {
  args: {
    elementId: "payment-rtl",
    inputId: "payment-input-rtl",
    headline: "أكمل الدفع",
    description: "أدخل تفاصيل بطاقتك",
    currency: "usd",
    amount: 1000,
    buttonLabel: "ادفع",
    dir: "rtl",
    onSubmit: () => {
      alert("Payment submitted");
    },
  },
};

export const WithCardSlot: Story = {
  render: (args: StoryProps) => (
    <Payment {...args}>
      <div className="rounded-md border border-gray-300 bg-white p-3 text-sm text-gray-500">
        Mock Card Input (Stripe Elements slot)
      </div>
    </Payment>
  ),
  args: {
    elementId: "payment-slot",
    inputId: "payment-input-slot",
    headline: "Complete your payment",
    currency: "usd",
    amount: 2000,
    buttonLabel: "Pay $20.00",
    onSubmit: () => {
      alert("Payment submitted");
    },
  },
};
