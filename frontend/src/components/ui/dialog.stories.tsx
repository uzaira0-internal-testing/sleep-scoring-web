import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "./dialog";
import { Button } from "./button";

const meta = {
  title: "UI/Dialog",
  component: Dialog,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Modal dialog component with overlay, header, content area, and footer. " +
          "Supports escape key to close, body scroll lock, and click-outside-to-close.",
      },
    },
  },
  args: {
    onOpenChange: fn(),
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Dialog>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Open dialog with all sub-components. */
export const Open: Story = {
  args: {
    open: true,
  },
  render: (args) => (
    <Dialog {...args}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Dialog Title</DialogTitle>
          <DialogDescription>
            This is a dialog description providing context about the dialog content.
          </DialogDescription>
        </DialogHeader>
        <div className="py-4">
          <p className="text-sm text-muted-foreground">
            Dialog body content goes here. This can contain forms, tables, or any other content.
          </p>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => args.onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => args.onOpenChange(false)}>
            Confirm
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  ),
};

/** Closed state (renders nothing). */
export const Closed: Story = {
  args: {
    open: false,
    children: null,
  },
};

/** Dialog with long scrollable content. */
export const LongContent: Story = {
  args: {
    open: true,
  },
  render: (args) => (
    <Dialog {...args}>
      <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Long Content Dialog</DialogTitle>
          <DialogDescription>
            This dialog has a lot of content that overflows.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          {Array.from({ length: 15 }, (_, i) => (
            <p key={i} className="text-sm text-muted-foreground">
              Paragraph {i + 1}: Lorem ipsum dolor sit amet, consectetur adipiscing elit.
              Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.
            </p>
          ))}
        </div>
        <DialogFooter>
          <Button onClick={() => args.onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  ),
};

/** Minimal dialog with just a title and a button. */
export const Minimal: Story = {
  args: {
    open: true,
  },
  render: (args) => (
    <Dialog {...args}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>Confirm Action</DialogTitle>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => args.onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => args.onOpenChange(false)}>OK</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  ),
};
