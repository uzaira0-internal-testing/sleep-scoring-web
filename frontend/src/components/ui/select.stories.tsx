import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { Select } from "./select";
import { Label } from "./label";

const ALGORITHM_OPTIONS = [
  { value: "sadeh_1994_actilife", label: "Sadeh 1994 (ActiLife)" },
  { value: "sadeh_1994_original", label: "Sadeh 1994 (Original)" },
  { value: "cole_kripke_1992_actilife", label: "Cole-Kripke 1992 (ActiLife)" },
] as const;

const meta = {
  title: "UI/Select",
  component: Select,
  parameters: {
    layout: "centered",
  },
  args: {
    onChange: fn(),
  },
  argTypes: {
    disabled: {
      control: "boolean",
      description: "Whether the select is disabled",
    },
    placeholder: {
      control: "text",
      description: "Placeholder option text",
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
} satisfies Meta<typeof Select>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default select with options. */
export const Default: Story = {
  args: {
    options: ALGORITHM_OPTIONS,
    defaultValue: "sadeh_1994_actilife",
  },
};

/** With placeholder. */
export const WithPlaceholder: Story = {
  args: {
    options: ALGORITHM_OPTIONS,
    placeholder: "Choose an algorithm...",
    defaultValue: "",
  },
};

/** Disabled state. */
export const Disabled: Story = {
  args: {
    options: ALGORITHM_OPTIONS,
    defaultValue: "sadeh_1994_actilife",
    disabled: true,
  },
};

/** With disabled options. */
export const DisabledOptions: Story = {
  args: {
    options: [
      { value: "sadeh_1994_actilife", label: "Sadeh 1994 (ActiLife)" },
      { value: "cole_kripke_1992_actilife", label: "Cole-Kripke 1992 (ActiLife)" },
      { value: "custom", label: "Custom Algorithm (coming soon)", disabled: true },
    ],
    defaultValue: "sadeh_1994_actilife",
  },
};

/** With label. */
export const WithLabel: Story = {
  render: () => (
    <div className="space-y-2">
      <Label htmlFor="algo-select">Algorithm</Label>
      <Select
        id="algo-select"
        options={[...ALGORITHM_OPTIONS]}
        defaultValue="sadeh_1994_actilife"
      />
    </div>
  ),
};

/** Multiple selects in a form. */
export const FormLayout: Story = {
  render: () => (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="algo">Algorithm</Label>
        <Select
          id="algo"
          options={[...ALGORITHM_OPTIONS]}
          defaultValue="sadeh_1994_actilife"
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="display">Display Column</Label>
        <Select
          id="display"
          options={[
            { value: "axis_y", label: "Axis Y" },
            { value: "vector_magnitude", label: "Vector Magnitude" },
          ]}
          defaultValue="axis_y"
        />
      </div>
    </div>
  ),
};
