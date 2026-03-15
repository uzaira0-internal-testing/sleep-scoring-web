import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import { ThemeProvider } from "@/components/theme-provider";
import { KeyboardShortcutsDialog, KeyboardShortcutsButton } from "./keyboard-shortcuts-dialog";

const meta = {
  title: "Components/KeyboardShortcutsDialog",
  component: KeyboardShortcutsDialog,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Keyboard shortcuts reference dialog. Shows all available shortcuts organized " +
          "by category: marker placement, marker editing, navigation, and view controls.",
      },
    },
  },
  args: {
    onOpenChange: fn(),
  },
  decorators: [
    (Story) => (
      <ThemeProvider defaultTheme="light" storageKey="storybook-kbd-shortcuts">
        <Story />
      </ThemeProvider>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof KeyboardShortcutsDialog>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Dialog open showing all shortcut sections. */
export const Open: Story = {
  args: {
    open: true,
  },
};

/** Dialog closed (renders nothing). */
export const Closed: Story = {
  args: {
    open: false,
  },
};

/** The trigger button that opens the dialog. */
export const TriggerButton: Story = {
  render: () => <KeyboardShortcutsButton onClick={fn()} />,
};
