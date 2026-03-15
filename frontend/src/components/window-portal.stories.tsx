import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { WindowPortal } from "./window-portal";

/**
 * WindowPortal renders children into a real browser popup window.
 * In Storybook, popup windows may be blocked by the browser.
 * This story documents the component's interface.
 */
const meta = {
  title: "Components/WindowPortal",
  component: WindowPortal,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Renders children into a real browser popup window via React portal. " +
          "Components stay in the same React tree so Zustand store, callbacks, " +
          "and all reactivity work automatically. " +
          "Note: Popup windows may be blocked by the browser in Storybook.",
      },
    },
  },
  argTypes: {
    open: {
      control: "boolean",
      description: "Whether the popup window is open",
    },
    title: {
      control: "text",
      description: "Title for the popup window",
    },
    width: {
      control: { type: "number", min: 200, max: 1200 },
      description: "Width of the popup window",
    },
    height: {
      control: { type: "number", min: 200, max: 1000 },
      description: "Height of the popup window",
    },
  },
  args: {
    onClose: fn(),
  },
  tags: ["autodocs"],
} satisfies Meta<typeof WindowPortal>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Closed state (renders nothing). */
export const Closed: Story = {
  args: {
    open: false,
    title: "Popup Table",
    width: 700,
    height: 800,
    children: <div>Popup content</div>,
  },
};
