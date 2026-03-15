import type { Meta, StoryObj } from "@storybook/react-vite";
import { UpdateBanner } from "./update-banner";

/**
 * UpdateBanner only renders in Tauri desktop mode (isTauri() returns true).
 * In web/Storybook mode it returns null.
 * This story documents the component and its various visual states.
 */
const meta = {
  title: "Components/UpdateBanner",
  component: UpdateBanner,
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Auto-update banner for the Tauri desktop app. " +
          "Shows different states: update available, downloading with progress bar, " +
          "ready to restart, and error with retry. " +
          "Only renders in Tauri mode -- returns null in web browsers.",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof UpdateBanner>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default state -- returns null outside Tauri. */
export const Default: Story = {
  render: () => (
    <div style={{ width: 600, border: "1px dashed var(--border)", borderRadius: 8, padding: 16 }}>
      <UpdateBanner />
      <p style={{ color: "var(--muted-foreground)", fontSize: 12, textAlign: "center" }}>
        (UpdateBanner returns null outside Tauri desktop mode)
      </p>
    </div>
  ),
};
