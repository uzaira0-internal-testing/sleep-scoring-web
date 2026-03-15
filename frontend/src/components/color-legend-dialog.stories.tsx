import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { ThemeProvider } from "@/components/theme-provider";
import { ColorLegendDialog, ColorLegendButton } from "./color-legend-dialog";

const meta = {
  title: "Components/ColorLegendDialog",
  component: ColorLegendDialog,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Dialog showing the color legend for marker colors and algorithm meanings in the activity plot.",
      },
    },
  },
  args: {
    onOpenChange: fn(),
  },
  decorators: [
    (Story) => (
      <ThemeProvider defaultTheme="light" storageKey="storybook-color-legend">
        <Story />
      </ThemeProvider>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof ColorLegendDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Dialog in its open state showing all color legend sections. */
export const Open: Story = {
  args: {
    open: true,
  },
};

/** Dialog in its closed state (renders nothing). */
export const Closed: Story = {
  args: {
    open: false,
  },
};

/** The trigger button that opens the dialog. */
export const TriggerButton: Story = {
  render: () => <ColorLegendButton onClick={fn()} />,
};
