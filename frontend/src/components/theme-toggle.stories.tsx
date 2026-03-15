import type { Meta, StoryObj } from "@storybook/react-vite";
import { ThemeProvider } from "@/components/theme-provider";
import { ThemeToggle } from "./theme-toggle";

const meta = {
  title: "Components/ThemeToggle",
  component: ThemeToggle,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Button that cycles through light -> dark -> system themes. " +
          "Shows a sun icon in light mode and a moon icon in dark mode.",
      },
    },
  },
  decorators: [
    (Story) => (
      <ThemeProvider defaultTheme="light" storageKey="storybook-theme-toggle">
        <Story />
      </ThemeProvider>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof ThemeToggle>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default state in light mode -- shows sun icon. */
export const Default: Story = {};

/** In dark mode -- shows moon icon. */
export const DarkMode: Story = {
  decorators: [
    (Story) => (
      <ThemeProvider defaultTheme="dark" storageKey="storybook-theme-toggle-dark">
        <Story />
      </ThemeProvider>
    ),
  ],
};
