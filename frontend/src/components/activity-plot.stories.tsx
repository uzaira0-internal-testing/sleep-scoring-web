import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme-provider";
import { DataSourceProvider } from "@/contexts/data-source-context";
import { useSleepScoringStore } from "@/store";
import { ALGORITHM_TYPES } from "@/api/types";
import type { ActivityData } from "@/services/data-source";
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

// ---------------------------------------------------------------------------
// Shared mock data
// ---------------------------------------------------------------------------

const MOCK_TIMESTAMPS = generateMockTimestamps();
const MOCK_ACTIVITY = generateMockActivity();
const MOCK_VM = generateMockActivity(); // separate random vector magnitude
const MOCK_ALGO = generateMockAlgorithmResults();
const MOCK_NW = generateMockNonwearResults();

/** Default activity data seeded into React Query cache. */
const BASE_ACTIVITY_DATA: ActivityData = {
  timestamps: MOCK_TIMESTAMPS,
  axisX: MOCK_ACTIVITY,
  axisY: MOCK_ACTIVITY,
  axisZ: MOCK_ACTIVITY,
  vectorMagnitude: MOCK_VM,
  algorithmResults: MOCK_ALGO,
  nonwearResults: null,
  sensorNonwearPeriods: [],
  viewStart: MOCK_TIMESTAMPS[0]!,
  viewEnd: MOCK_TIMESTAMPS[MOCK_TIMESTAMPS.length - 1]!,
};

/** Store state that does NOT include activity data (kept in React Query cache). */
const BASE_STORE_STATE = {
  currentFileId: 1,
  currentFilename: "participant_001.csv",
  currentDateIndex: 0,
  availableDates: ["2025-01-15"],
  currentFileSource: "server" as const,
  currentAlgorithm: ALGORITHM_TYPES.SADEH_1994_ACTILIFE,
  viewModeHours: 24 as const,
  isAuthenticated: true,
  sitePassword: null,
  username: "storybook",
  preferredDisplayColumn: "axis_y" as const,
  sleepMarkers: [],
  nonwearMarkers: [],
  selectedPeriodIndex: null,
};

/** Build the query key that useActivityData will look up. */
function activityQueryKey(overrides?: { fileId?: number; date?: string; hours?: number; algo?: string }): unknown[] {
  return [
    "activity",
    overrides?.fileId ?? 1,
    overrides?.date ?? "2025-01-15",
    overrides?.hours ?? 24,
    overrides?.algo ?? ALGORITHM_TYPES.SADEH_1994_ACTILIFE,
    "server",
  ];
}

// ---------------------------------------------------------------------------
// Store + Query configurator decorator
// ---------------------------------------------------------------------------

/** Sets Zustand store state AND seeds React Query cache for the story. */
function StoreConfigurator({
  state,
  activityData,
  queryClient,
  children,
}: {
  state: Record<string, unknown>;
  activityData: ActivityData | null;
  queryClient: QueryClient;
  children: React.ReactNode;
}) {
  useEffect(() => {
    useSleepScoringStore.setState(state);
    if (activityData) {
      queryClient.setQueryData(activityQueryKey(), activityData);
    }
    return () => {
      useSleepScoringStore.setState({
        sleepMarkers: [],
        nonwearMarkers: [],
        currentFileId: null,
        currentDateIndex: 0,
        availableDates: [],
        selectedPeriodIndex: null,
      });
      queryClient.clear();
    };
  }, [state, activityData, queryClient]);
  return <>{children}</>;
}

/** Wrap in all providers the ActivityPlot needs. */
function withProviders(storeState: Record<string, unknown>, activityData: ActivityData | null = BASE_ACTIVITY_DATA) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
    },
  });

  return function Decorator(Story: React.ComponentType) {
    return (
      <ThemeProvider defaultTheme="light" storageKey="storybook-activity-plot">
        <QueryClientProvider client={qc}>
          <DataSourceProvider>
            <StoreConfigurator state={storeState} activityData={activityData} queryClient={qc}>
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

/** Loading state -- no activity data in cache, query would be loading. */
export const Loading: Story = {
  decorators: [
    withProviders(BASE_STORE_STATE, null),
  ],
};

/** Empty data state -- file selected but activity data has empty arrays. */
export const EmptyData: Story = {
  decorators: [
    withProviders(BASE_STORE_STATE, {
      ...BASE_ACTIVITY_DATA,
      timestamps: [],
      axisY: [],
      vectorMagnitude: [],
      algorithmResults: null,
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
    withProviders(
      {
        ...BASE_STORE_STATE,
        nonwearMarkers: [
          {
            startTimestamp: MOCK_TIMESTAMPS[300]!, // ~17:00
            endTimestamp: MOCK_TIMESTAMPS[390]!, // ~18:30
            markerIndex: 0,
          },
        ],
      },
      { ...BASE_ACTIVITY_DATA, nonwearResults: MOCK_NW },
    ),
  ],
};

/** With both sleep and nonwear markers overlapping on the same day. */
export const WithSleepAndNonwear: Story = {
  decorators: [
    withProviders(
      {
        ...BASE_STORE_STATE,
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
      },
      { ...BASE_ACTIVITY_DATA, nonwearResults: MOCK_NW },
    ),
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
