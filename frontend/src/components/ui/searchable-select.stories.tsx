import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { useState } from "react";
import { SearchableSelect } from "./searchable-select";

const SAMPLE_OPTIONS = [
  { value: "1", label: "participant_001_actigraph.csv" },
  { value: "2", label: "participant_002_actigraph.csv" },
  { value: "3", label: "participant_003_geneactiv.csv" },
  { value: "4", label: "participant_004_actigraph.csv" },
  { value: "5", label: "participant_005_geneactiv.csv" },
  { value: "6", label: "control_group_subject_10.csv" },
  { value: "7", label: "control_group_subject_11.csv" },
  { value: "8", label: "treatment_arm_a_p001.csv" },
];

const meta = {
  title: "UI/SearchableSelect",
  component: SearchableSelect,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Select with search/filter input. Opens a dropdown list filtered by typed text. " +
          "Used for file selection where there may be many options to filter through.",
      },
    },
  },
  args: {
    onChange: fn(),
  },
  argTypes: {
    placeholder: {
      control: "text",
      description: "Placeholder text when no value is selected",
    },
    disabled: {
      control: "boolean",
      description: "Whether the select is disabled",
    },
  },
  decorators: [
    (Story) => (
      <div style={{ width: 350, minHeight: 400 }}>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof SearchableSelect>;

export default meta;
type Story = StoryObj<typeof meta>;

/** No value selected -- shows placeholder. */
export const Default: Story = {
  args: {
    options: SAMPLE_OPTIONS,
    value: "",
    placeholder: "Select a file...",
  },
};

/** With a value selected. */
export const WithValue: Story = {
  args: {
    options: SAMPLE_OPTIONS,
    value: "3",
    placeholder: "Select a file...",
  },
};

/** Disabled state. */
export const Disabled: Story = {
  args: {
    options: SAMPLE_OPTIONS,
    value: "1",
    disabled: true,
    placeholder: "Select a file...",
  },
};

/** With some disabled options. */
export const DisabledOptions: Story = {
  args: {
    options: [
      { value: "1", label: "Available file.csv" },
      { value: "2", label: "Processing... (disabled)", disabled: true },
      { value: "3", label: "Another available file.csv" },
      { value: "4", label: "Error file (disabled)", disabled: true },
    ],
    value: "",
    placeholder: "Select a file...",
  },
};

/** Few options. */
export const FewOptions: Story = {
  args: {
    options: [
      { value: "1", label: "File A.csv" },
      { value: "2", label: "File B.csv" },
    ],
    value: "",
    placeholder: "Select...",
  },
};

/** Interactive demo with state. */
export const Interactive: Story = {
  render: () => {
    const [value, setValue] = useState("");
    return (
      <SearchableSelect
        options={SAMPLE_OPTIONS}
        value={value}
        onChange={setValue}
        placeholder="Search and select a file..."
      />
    );
  },
};
