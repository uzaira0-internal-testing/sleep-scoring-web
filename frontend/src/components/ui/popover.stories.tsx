import type { Meta, StoryObj } from "@storybook/react-vite";
import { Popover, PopoverTrigger, PopoverContent } from "./popover";
import { Button } from "./button";

const meta = {
  title: "UI/Popover",
  component: Popover,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Popover component with trigger and content. " +
          "Supports alignment (start, center, end), closes on outside click and Escape key.",
      },
    },
  },
  decorators: [
    (Story) => (
      <div style={{ minHeight: 300, display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: 40 }}>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof Popover>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default popover -- click the button to open. */
export const Default: Story = {
  render: () => (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline">Open Popover</Button>
      </PopoverTrigger>
      <PopoverContent className="w-64">
        <div className="space-y-2">
          <h4 className="font-medium text-sm">Popover Content</h4>
          <p className="text-sm text-muted-foreground">
            This is the popover content area. It can contain any elements.
          </p>
        </div>
      </PopoverContent>
    </Popover>
  ),
};

/** Aligned to start (left). */
export const AlignStart: Story = {
  render: () => (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline">Align Start</Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-48">
        <p className="text-sm">Aligned to the start (left edge).</p>
      </PopoverContent>
    </Popover>
  ),
};

/** Aligned to end (right). */
export const AlignEnd: Story = {
  render: () => (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline">Align End</Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-48">
        <p className="text-sm">Aligned to the end (right edge).</p>
      </PopoverContent>
    </Popover>
  ),
};

/** With rich content inside. */
export const WithForm: Story = {
  render: () => (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline">Settings</Button>
      </PopoverTrigger>
      <PopoverContent className="w-72">
        <div className="space-y-3">
          <h4 className="font-medium text-sm">Display Settings</h4>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Epoch size</label>
            <select className="w-full h-8 rounded border text-sm px-2">
              <option>60 seconds</option>
              <option>30 seconds</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground">Algorithm</label>
            <select className="w-full h-8 rounded border text-sm px-2">
              <option>Sadeh 1994</option>
              <option>Cole-Kripke 1992</option>
            </select>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  ),
};
