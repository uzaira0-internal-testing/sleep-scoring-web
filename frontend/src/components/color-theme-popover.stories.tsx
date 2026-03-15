import type { Meta, StoryObj } from "@storybook/react-vite";
import { ThemeProvider } from "@/components/theme-provider";
import { ColorThemePopover } from "./color-theme-popover";

const meta = {
  title: "Components/ColorThemePopover",
  component: ColorThemePopover,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Popover for customizing the color theme of the activity plot. " +
          "Provides preset selection and individual color pickers for onset, offset, " +
          "sleep overlay, nonwear, and activity line colors.",
      },
    },
  },
  decorators: [
    (Story) => (
      <ThemeProvider defaultTheme="light" storageKey="storybook-color-theme">
        <div style={{ minHeight: 400, display: "flex", alignItems: "flex-start", justifyContent: "center", paddingTop: 20 }}>
          <Story />
        </div>
      </ThemeProvider>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof ColorThemePopover>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default state -- click the palette icon to open the popover. */
export const Default: Story = {};
