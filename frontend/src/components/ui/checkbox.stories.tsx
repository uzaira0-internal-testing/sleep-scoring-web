import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { Checkbox } from "./checkbox";
import { Label } from "./label";

const meta = {
  title: "UI/Checkbox",
  component: Checkbox,
  parameters: {
    layout: "centered",
  },
  args: {
    onCheckedChange: fn(),
  },
  argTypes: {
    checked: {
      control: "boolean",
      description: "Whether the checkbox is checked",
    },
    disabled: {
      control: "boolean",
      description: "Whether the checkbox is disabled",
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Checkbox>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Unchecked state. */
export const Default: Story = {
  args: {
    checked: false,
  },
};

/** Checked state. */
export const Checked: Story = {
  args: {
    checked: true,
  },
};

/** Disabled unchecked. */
export const Disabled: Story = {
  args: {
    disabled: true,
    checked: false,
  },
};

/** Disabled checked. */
export const DisabledChecked: Story = {
  args: {
    disabled: true,
    checked: true,
  },
};

/** With label text. */
export const WithLabel: Story = {
  render: (args) => (
    <div className="flex items-center gap-2">
      <Checkbox {...args} id="terms" />
      <Label htmlFor="terms">Accept terms and conditions</Label>
    </div>
  ),
};

/** Multiple checkboxes as a group. */
export const Group: Story = {
  render: () => (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Checkbox id="opt1" defaultChecked />
        <Label htmlFor="opt1">Show sleep markers</Label>
      </div>
      <div className="flex items-center gap-2">
        <Checkbox id="opt2" defaultChecked />
        <Label htmlFor="opt2">Show nonwear markers</Label>
      </div>
      <div className="flex items-center gap-2">
        <Checkbox id="opt3" />
        <Label htmlFor="opt3">Show algorithm overlay</Label>
      </div>
    </div>
  ),
};
