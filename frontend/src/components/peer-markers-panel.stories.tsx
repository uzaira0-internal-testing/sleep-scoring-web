import type { Meta, StoryObj } from "@storybook/react-vite";
import { PeerMarkersPanel } from "./peer-markers-panel";

/**
 * PeerMarkersPanel only renders in Tauri mode (isTauri() returns true).
 * In a web browser / Storybook context it returns null.
 * This story documents the component's existence and interface.
 */
const meta = {
  title: "Components/PeerMarkersPanel",
  component: PeerMarkersPanel,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Panel showing discovered LAN peers and their markers. " +
          "Only renders in Tauri desktop mode. In web/Storybook mode it returns null. " +
          "Provides pull-from-peers functionality for offline marker synchronization.",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof PeerMarkersPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default state -- returns null outside Tauri. */
export const Default: Story = {
  render: () => (
    <div style={{ width: 280, border: "1px dashed var(--border)", borderRadius: 8, padding: 16 }}>
      <PeerMarkersPanel />
      <p style={{ color: "var(--muted-foreground)", fontSize: 12, textAlign: "center" }}>
        (PeerMarkersPanel returns null outside Tauri desktop mode)
      </p>
    </div>
  ),
};
