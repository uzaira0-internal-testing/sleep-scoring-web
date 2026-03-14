import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect } from "react";
import { fn } from "storybook/test";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme-provider";
import { DataSourceProvider } from "@/contexts/data-source-context";
import { useSleepScoringStore } from "@/store";
import { MarkerDataTable } from "./marker-data-table";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const storyQueryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
  },
});

/** Sets Zustand store state for the story and resets on unmount. */
function StoreConfigurator({
  state,
  children,
}: {
  state: Record<string, unknown>;
  children: React.ReactNode;
}) {
  useEffect(() => {
    useSleepScoringStore.setState(state);
    return () => {
      useSleepScoringStore.setState({
        currentFileId: null,
        currentDateIndex: 0,
        availableDates: [],
        sleepMarkers: [],
        nonwearMarkers: [],
        selectedPeriodIndex: null,
        markerMode: "sleep",
        isAuthenticated: false,
        currentFileSource: "server",
      });
    };
  }, [state]);
  return <>{children}</>;
}

/** Generate timestamps around 23:00 for onset or 07:00 for offset. */
function generateTableTimestamps(centerHour: number, count = 100): number[] {
  const baseDate = new Date("2025-01-15T00:00:00Z");
  baseDate.setUTCHours(centerHour, 0, 0, 0);
  if (centerHour < 12) baseDate.setUTCDate(baseDate.getUTCDate() + 1);
  const centerTs = baseDate.getTime() / 1000;
  const halfWindow = (count / 2) * 60;
  return Array.from({ length: count }, (_, i) => centerTs - halfWindow + i * 60);
}

/** Wrap stories in all required providers. */
function withProviders(storeState: Record<string, unknown>) {
  return function Decorator(Story: React.ComponentType) {
    return (
      <ThemeProvider defaultTheme="light" storageKey="storybook-marker-table">
        <QueryClientProvider client={storyQueryClient}>
          <DataSourceProvider>
            <StoreConfigurator state={storeState}>
              <div style={{ width: 320, height: 500, border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
                <Story />
              </div>
            </StoreConfigurator>
          </DataSourceProvider>
        </QueryClientProvider>
      </ThemeProvider>
    );
  };
}

// ---------------------------------------------------------------------------
// Shared store state
// ---------------------------------------------------------------------------

const ONSET_TS = new Date("2025-01-15T23:00:00Z").getTime() / 1000;
const OFFSET_TS = new Date("2025-01-16T07:00:00Z").getTime() / 1000;

const BASE_STORE_STATE = {
  currentFileId: 1,
  currentDateIndex: 0,
  availableDates: ["2025-01-15"],
  currentFileSource: "local" as const,
  isAuthenticated: false,
  markerMode: "sleep" as const,
  sleepMarkers: [
    {
      onsetTimestamp: ONSET_TS,
      offsetTimestamp: OFFSET_TS,
      markerIndex: 0,
      markerType: "MAIN_SLEEP" as const,
    },
  ],
  nonwearMarkers: [],
  selectedPeriodIndex: 0,
};

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

const meta = {
  title: "Components/MarkerDataTable",
  component: MarkerDataTable,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Displays columnar activity data around a sleep onset or offset timestamp. " +
          "Rows are clickable to move the marker. Shows sleep/wake algorithm results, " +
          "Choi nonwear, and sensor nonwear columns. " +
          "Data is fetched from the server or built from local IndexedDB depending on mode.",
      },
    },
  },
  argTypes: {
    type: {
      control: "select",
      options: ["onset", "offset"],
      description: "Whether this table shows onset or offset data",
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof MarkerDataTable>;

export default meta;
type Story = StoryObj<typeof meta>;

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

/** No marker selected -- shows a prompt to select a marker. */
export const NoMarkerSelected: Story = {
  args: {
    type: "onset",
    onOpenPopout: fn(),
  },
  decorators: [
    withProviders({
      ...BASE_STORE_STATE,
      selectedPeriodIndex: null,
    }),
  ],
};

/** Onset table with a selected sleep marker (local mode will build from IndexedDB). */
export const OnsetTable: Story = {
  args: {
    type: "onset",
    onOpenPopout: fn(),
  },
  decorators: [withProviders(BASE_STORE_STATE)],
};

/** Offset table with a selected sleep marker. */
export const OffsetTable: Story = {
  args: {
    type: "offset",
    onOpenPopout: fn(),
  },
  decorators: [withProviders(BASE_STORE_STATE)],
};

/** Nonwear mode -- shows NW Start / NW End labels. */
export const NonwearMode: Story = {
  args: {
    type: "onset",
    onOpenPopout: fn(),
  },
  decorators: [
    withProviders({
      ...BASE_STORE_STATE,
      markerMode: "nonwear" as const,
      sleepMarkers: [],
      nonwearMarkers: [
        {
          startTimestamp: new Date("2025-01-15T17:00:00Z").getTime() / 1000,
          endTimestamp: new Date("2025-01-15T18:30:00Z").getTime() / 1000,
          markerIndex: 0,
        },
      ],
      selectedPeriodIndex: 0,
    }),
  ],
};

/** Without the popout button (onOpenPopout not provided). */
export const WithoutPopout: Story = {
  args: {
    type: "onset",
  },
  decorators: [withProviders(BASE_STORE_STATE)],
};
