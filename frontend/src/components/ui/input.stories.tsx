import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { Input } from "./input";
import { Label } from "./label";

const meta = {
  title: "UI/Input",
  component: Input,
  parameters: {
    layout: "centered",
  },
  args: {
    onChange: fn(),
  },
  argTypes: {
    type: {
      control: "select",
      options: ["text", "password", "email", "number", "search", "url"],
      description: "Input type",
    },
    placeholder: {
      control: "text",
      description: "Placeholder text",
    },
    disabled: {
      control: "boolean",
      description: "Whether the input is disabled",
    },
  },
  decorators: [
    (Story) => (
      <div style={{ width: 300 }}>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof Input>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default text input. */
export const Default: Story = {
  args: {
    type: "text",
    placeholder: "Enter text...",
  },
};

/** With a value. */
export const WithValue: Story = {
  args: {
    type: "text",
    defaultValue: "participant_001.csv",
  },
};

/** Disabled state. */
export const Disabled: Story = {
  args: {
    type: "text",
    disabled: true,
    defaultValue: "Cannot edit this",
  },
};

/** Password input. */
export const Password: Story = {
  args: {
    type: "password",
    placeholder: "Enter password...",
  },
};

/** Number input. */
export const Number: Story = {
  args: {
    type: "number",
    placeholder: "0",
    min: 0,
    max: 100,
  },
};

/** With label. */
export const WithLabel: Story = {
  render: () => (
    <div className="space-y-2">
      <Label htmlFor="username">Username</Label>
      <Input id="username" type="text" placeholder="Enter your username" />
    </div>
  ),
};

/** File input. */
export const File: Story = {
  args: {
    type: "file",
  },
};
