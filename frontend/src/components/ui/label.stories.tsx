import type { Meta, StoryObj } from "@storybook/react-vite";
import { Label } from "./label";
import { Input } from "./input";
import { Checkbox } from "./checkbox";

const meta = {
  title: "UI/Label",
  component: Label,
  parameters: {
    layout: "centered",
  },
  argTypes: {
    children: {
      control: "text",
      description: "Label text content",
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Label>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default label. */
export const Default: Story = {
  args: {
    children: "Label Text",
  },
};

/** Label paired with an input. */
export const WithInput: Story = {
  render: () => (
    <div className="space-y-2" style={{ width: 300 }}>
      <Label htmlFor="email">Email address</Label>
      <Input id="email" type="email" placeholder="you@example.com" />
    </div>
  ),
};

/** Label paired with a checkbox. */
export const WithCheckbox: Story = {
  render: () => (
    <div className="flex items-center gap-2">
      <Checkbox id="agree" />
      <Label htmlFor="agree">I agree to the terms</Label>
    </div>
  ),
};

/** Disabled state -- the label reduces opacity when its peer is disabled. */
export const Disabled: Story = {
  render: () => (
    <div className="space-y-2" style={{ width: 300 }}>
      <Label htmlFor="disabled-input">Disabled field</Label>
      <Input id="disabled-input" disabled defaultValue="Cannot edit" />
    </div>
  ),
};

/** Multiple labeled fields in a form layout. */
export const FormLayout: Story = {
  render: () => (
    <div className="space-y-4" style={{ width: 300 }}>
      <div className="space-y-2">
        <Label htmlFor="study-name">Study Name</Label>
        <Input id="study-name" placeholder="Enter study name" />
      </div>
      <div className="space-y-2">
        <Label htmlFor="participant-id">Participant ID</Label>
        <Input id="participant-id" placeholder="e.g., P001" />
      </div>
    </div>
  ),
};
