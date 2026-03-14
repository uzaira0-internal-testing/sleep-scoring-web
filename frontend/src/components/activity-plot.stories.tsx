import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme-provider";
import { DataSourceProvider } from "@/contexts/data-source-context";
import { useSleepScoringStore } from "@/store";
import { ActivityPlot } from "./activity-plot";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Generate mock timestamps: 1440 epochs = 24 hours of 60-second epochs.
 *  Starts at noon (12:00 UTC) on 2025-01-15 to mimic a real noon-to-noon day. */
function generateMockTimestamps(count = 1440): number[] {
  const baseTs = new Date("2025-01-15T12:00:00Z").getTime() / 1000;
  return Array.from({ length: count }, (_, i) => baseTs + i * 60);
}

/** Pseudo-random activity counts that look vaguely like a day of actigraphy. */
function generateMockActivity(count = 1440): number[] {
  return Array.from({ length: count }, (_, i) => {
    // Low activity during nighttime (epochs 600-1100 ~ 22:00-06:20)
    const isNight = i >= 600 && i <= 1100;
    const base = isNight ? 5 : 200;
    const noise = Math.floor(Math.random() * (isNight ? 30 : 400));
    return base + noise;
  });
}

/** Generate mock algorithm results (1=sleep, 0=wake). Night hours are mostly sleep. */
function generateMockAlgorithmResults(count = 1440): number[] {
  return Array.from({ length: count }, (_, i) => {
    const isNight = i >= 600 && i <= 1100;
    if (isNight) return Math.random() > 0.1 ? 1 : 0;
    return Math.random() > 0.9 ? 1 : 0;
  });
}

/** Generate mock nonwear results (1=nonwear, 0=wear). Sparse nonwear blocks. */
function generateMockNonwearResults(count = 1440): number[] {
  const results = new Array<number>(count).fill(0);
  // One 90-minute nonwear block around epoch 300 (17:00)
  for (let i = 300; i < 390 && i < count; i++) results[i] = 1;
  return results;
}

const storyQueryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
  },
});

// ---------------------------------------------------------------------------
// Store configurator decorator
// ---------------------------------------------------------------------------

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
        timestamps: [],
        axisY: [],
        vectorMagnitude: [],
        algorithmResults: null,
        nonwearResults: null,
        sleepMarkers: [],
        nonwearMarkers: [],
        isLoading: false,
        currentFileId: null,
        currentDateIndex: 0,
        availableDates: [],
        selectedPeriodIndex: null,
        sensorNonwearPeriods: [],
      });
    };
  }, [state]);
  return <>{children}</>;
}

/** Wrap in all providers the ActivityPlot needs. */
function withProviders(storeState: Record<string, unknown>) {
  return function Decorator(Story: React.ComponentType) {
    return (
      <ThemeProvider defaultTheme="light" storageKey="storybook-activity-plot">
        <QueryClientProvider client={storyQueryClient}>
          <DataSourceProvider>
            <StoreConfigurator state={storeState}>
              <div style={{ width: 900, height: 400, position: "relative" }}>
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
// Shared mock data
// ---------------------------------------------------------------------------

const MOCK_TIMESTAMPS = generateMockTimestamps();
const MOCK_ACTIVITY = generateMockActivity();
const MOCK_VM = generateMockActivity(); // separate random vector magnitude
const MOCK_ALGO = generateMockAlgorithmResults();
const MOCK_NW = generateMockNonwearResults();

const BASE_STORE_STATE = {
  currentFileId: 1,
  currentFilename: "participant_001.csv",
  currentDateIndex: 0,
  availableDates: ["2025-01-15"],
  currentFileSource: "server" as const,
  isAuthenticated: true,
  sitePassword: null,
  username: "storybook",
  timestamps: MOCK_TIMESTAMPS,
  axisY: MOCK_ACTIVITY,
  vectorMagnitude: MOCK_VM,
  algorithmResults: MOCK_ALGO,
  nonwearResults: null,
  sensorNonwearPeriods: [],
  isLoading: false,
  preferredDisplayColumn: "axis_y" as const,
  viewStart: MOCK_TIMESTAMPS[0],
  viewEnd: MOCK_TIMESTAMPS[MOCK_TIMESTAMPS.length - 1],
  sleepMarkers: [],
  nonwearMarkers: [],
  selectedPeriodIndex: null,
};

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

const meta = {
  title: "Components/ActivityPlot",
  component: ActivityPlot,
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "uPlot-based activity plot that renders accelerometer data with sleep/nonwear marker overlays. " +
          "Canvas rendering means interactions (drag-to-create markers, zoom) are not fully testable in Storybook, " +
          "but layout and data population are visible.",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ActivityPlot>;

export default meta;
type Story = StoryObj<typeof meta>;

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

/** Default view with mock activity data for a 24-hour period. */
export const Default: Story = {
  decorators: [withProviders(BASE_STORE_STATE)],
};

/** Loading state -- the store's isLoading flag is true. */
export const Loading: Story = {
  decorators: [
    withProviders({
      ...BASE_STORE_STATE,
      timestamps: [],
      axisY: [],
      vectorMagnitude: [],
      algorithmResults: null,
      isLoading: true,
    }),
  ],
};

/** Empty data state -- file selected but no activity data available. */
export const EmptyData: Story = {
  decorators: [
    withProviders({
      ...BASE_STORE_STATE,
      timestamps: [],
      axisY: [],
      vectorMagnitude: [],
      algorithmResults: null,
      isLoading: false,
    }),
  ],
};

/** With a main sleep marker overlay (onset at 23:00, offset at 07:00). */
export const WithSleepMarkers: Story = {
  decorators: [
    withProviders({
      ...BASE_STORE_STATE,
      sleepMarkers: [
        {
          onsetTimestamp: MOCK_TIMESTAMPS[660]!, // ~23:00
          offsetTimestamp: MOCK_TIMESTAMPS[1140]!, // ~07:00 next day
          markerIndex: 0,
          markerType: "MAIN_SLEEP",
        },
      ],
      selectedPeriodIndex: 0,
    }),
  ],
};

/** With nonwear marker overlay (a 90-minute block). */
export const WithNonwearMarkers: Story = {
  decorators: [
    withProviders({
      ...BASE_STORE_STATE,
      nonwearResults: MOCK_NW,
      nonwearMarkers: [
        {
          startTimestamp: MOCK_TIMESTAMPS[300]!, // ~17:00
          endTimestamp: MOCK_TIMESTAMPS[390]!, // ~18:30
          markerIndex: 0,
        },
      ],
    }),
  ],
};

/** With both sleep and nonwear markers overlapping on the same day. */
export const WithSleepAndNonwear: Story = {
  decorators: [
    withProviders({
      ...BASE_STORE_STATE,
      nonwearResults: MOCK_NW,
      sleepMarkers: [
        {
          onsetTimestamp: MOCK_TIMESTAMPS[660]!,
          offsetTimestamp: MOCK_TIMESTAMPS[1140]!,
          markerIndex: 0,
          markerType: "MAIN_SLEEP",
        },
      ],
      nonwearMarkers: [
        {
          startTimestamp: MOCK_TIMESTAMPS[300]!,
          endTimestamp: MOCK_TIMESTAMPS[390]!,
          markerIndex: 0,
        },
      ],
      selectedPeriodIndex: 0,
    }),
  ],
};

/** Comparison markers mode (used during consensus voting). */
export const ComparisonMarkers: Story = {
  args: {
    showComparisonMarkers: true,
    highlightedCandidateId: null,
  },
  decorators: [
    withProviders({
      ...BASE_STORE_STATE,
      sleepMarkers: [
        {
          onsetTimestamp: MOCK_TIMESTAMPS[660]!,
          offsetTimestamp: MOCK_TIMESTAMPS[1140]!,
          markerIndex: 0,
          markerType: "MAIN_SLEEP",
        },
      ],
      selectedPeriodIndex: 0,
    }),
  ],
};
