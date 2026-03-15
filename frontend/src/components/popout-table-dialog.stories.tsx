import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { PopoutTableDialog } from "./popout-table-dialog";

/**
 * PopoutTableDialog opens a real browser popup window via WindowPortal.
 * In Storybook, popup windows may be blocked by the browser.
 * This story documents the component's props and interface.
 */
const meta = {
  title: "Components/PopoutTableDialog",
  component: PopoutTableDialog,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Full 48h data table rendered in a separate browser popup window via React portal. " +
          "Supports click-to-move marker placement and auto-scrolls to the current marker row. " +
          "Each highlightType (onset/offset) opens its own independent window. " +
          "Note: In Storybook, popup windows may be blocked by the browser.",
      },
    },
  },
  argTypes: {
    open: {
      control: "boolean",
      description: "Whether the popup window is open",
    },
    highlightType: {
      control: "select",
      options: ["onset", "offset"],
      description: "Which marker boundary to highlight and allow editing",
    },
  },
  args: {
    onOpenChange: fn(),
  },
  tags: ["autodocs"],
} satisfies Meta<typeof PopoutTableDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Closed state (renders nothing visible). */
export const Closed: Story = {
  args: {
    open: false,
    highlightType: "onset",
  },
};

/** Onset highlight type. Opening this will attempt to open a popup window. */
export const OnsetHighlight: Story = {
  args: {
    open: false,
    highlightType: "onset",
  },
};

/** Offset highlight type. */
export const OffsetHighlight: Story = {
  args: {
    open: false,
    highlightType: "offset",
  },
};
