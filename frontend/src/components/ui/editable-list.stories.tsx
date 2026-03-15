import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { useState } from "react";
import { EditableList } from "./editable-list";

const meta = {
  title: "UI/EditableList",
  component: EditableList,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Editable tag list with input and add button. " +
          "Items appear as removable badges. Supports maxItems limit, " +
          "duplicate prevention, and Enter key to add.",
      },
    },
  },
  argTypes: {
    placeholder: {
      control: "text",
      description: "Placeholder text for the input",
    },
    maxItems: {
      control: { type: "number", min: 1, max: 50 },
      description: "Maximum number of items allowed",
    },
  },
  decorators: [
    (Story) => (
      <div style={{ width: 350 }}>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof EditableList>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Empty list -- shows input with add button. */
export const Empty: Story = {
  args: {
    items: [],
    onChange: fn(),
    placeholder: "Add group...",
  },
};

/** List with existing items. */
export const WithItems: Story = {
  args: {
    items: ["Control", "Treatment A", "Treatment B"],
    onChange: fn(),
    placeholder: "Add group...",
  },
};

/** At maximum capacity (3 items, maxItems=3). */
export const AtMaxItems: Story = {
  args: {
    items: ["Morning", "Afternoon", "Evening"],
    onChange: fn(),
    placeholder: "Add timepoint...",
    maxItems: 3,
  },
};

/** Interactive demo with state management. */
export const Interactive: Story = {
  render: () => {
    const [items, setItems] = useState(["Baseline", "Week 4"]);
    return (
      <EditableList
        items={items}
        onChange={setItems}
        placeholder="Add timepoint..."
        maxItems={10}
      />
    );
  },
};
