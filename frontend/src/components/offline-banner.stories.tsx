import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect } from "react";
import { useSyncStore } from "@/store/sync-store";
import { OfflineBanner } from "./offline-banner";

/** Helper to set sync store state for stories. */
function SyncStoreConfigurator({
  state,
  children,
}: {
  state: Record<string, unknown>;
  children: React.ReactNode;
}) {
  useEffect(() => {
    useSyncStore.setState(state);
    return () => {
      useSyncStore.setState({
        isOnline: true,
        pendingCount: 0,
        syncStatus: "idle",
        lastSyncAt: null,
        syncError: null,
      });
    };
  }, [state]);
  return <>{children}</>;
}

const meta = {
  title: "Components/OfflineBanner",
  component: OfflineBanner,
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Banner showing offline/online status with sync info. " +
          "Shows different states: offline warning, pending sync, syncing, and back-online confirmation.",
      },
    },
  },
  decorators: [
    (Story) => (
      <div style={{ width: 600 }}>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof OfflineBanner>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Online with no pending changes -- renders nothing. */
export const OnlineNoPending: Story = {
  decorators: [
    (Story) => (
      <SyncStoreConfigurator state={{ isOnline: true, pendingCount: 0, syncStatus: "idle" }}>
        <div style={{ border: "1px dashed var(--border)", borderRadius: 8, minHeight: 40, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Story />
          <p style={{ color: "var(--muted-foreground)", fontSize: 12 }}>
            (OfflineBanner returns null when online with no pending changes)
          </p>
        </div>
      </SyncStoreConfigurator>
    ),
  ],
};

/** Offline state -- yellow warning banner. */
export const Offline: Story = {
  decorators: [
    (Story) => (
      <SyncStoreConfigurator state={{ isOnline: false, pendingCount: 0 }}>
        <Story />
      </SyncStoreConfigurator>
    ),
  ],
};

/** Offline with pending changes. */
export const OfflineWithPending: Story = {
  decorators: [
    (Story) => (
      <SyncStoreConfigurator state={{ isOnline: false, pendingCount: 3 }}>
        <Story />
      </SyncStoreConfigurator>
    ),
  ],
};

/** Online with pending changes waiting to sync. */
export const PendingSync: Story = {
  decorators: [
    (Story) => (
      <SyncStoreConfigurator state={{ isOnline: true, pendingCount: 5, syncStatus: "idle", lastSyncAt: Date.now() - 60000 }}>
        <Story />
      </SyncStoreConfigurator>
    ),
  ],
};

/** Online and actively syncing. */
export const Syncing: Story = {
  decorators: [
    (Story) => (
      <SyncStoreConfigurator state={{ isOnline: true, pendingCount: 2, syncStatus: "syncing", lastSyncAt: Date.now() - 30000 }}>
        <Story />
      </SyncStoreConfigurator>
    ),
  ],
};
