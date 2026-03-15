import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { ConfirmDialog, AlertDialog } from "./confirm-dialog";

const meta = {
  title: "UI/ConfirmDialog",
  component: ConfirmDialog,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Styled confirmation dialog that replaces native browser confirm(). " +
          "Also includes an AlertDialog for simple messages with OK button. " +
          "Used via the useConfirmDialog() and useAlertDialog() hooks.",
      },
    },
  },
  args: {
    onConfirm: fn(),
    onCancel: fn(),
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ConfirmDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default confirmation dialog. */
export const Default: Story = {
  args: {
    open: true,
    title: "Save Changes?",
    description: "You have unsaved changes. Do you want to save before leaving?",
    confirmLabel: "Save",
    cancelLabel: "Discard",
    variant: "default",
  },
};

/** Destructive variant -- red confirm button. */
export const Destructive: Story = {
  args: {
    open: true,
    title: "Delete Markers?",
    description: "This will permanently delete all markers for this date. This action cannot be undone.",
    confirmLabel: "Delete",
    cancelLabel: "Cancel",
    variant: "destructive",
  },
};

/** Title only (no description). */
export const TitleOnly: Story = {
  args: {
    open: true,
    title: "Are you sure?",
    variant: "default",
  },
};

/** Closed state (renders nothing). */
export const Closed: Story = {
  args: {
    open: false,
    title: "Hidden Dialog",
  },
};

/** Alert dialog variant -- single OK button. */
export const Alert: Story = {
  render: () => (
    <AlertDialog
      open={true}
      onClose={fn()}
      title="Resolution Failed"
      description="Could not resolve consensus: server returned an error."
    />
  ),
};

/** Alert dialog with title only. */
export const AlertTitleOnly: Story = {
  render: () => (
    <AlertDialog
      open={true}
      onClose={fn()}
      title="Operation complete"
    />
  ),
};
