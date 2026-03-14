import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect, useMemo } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme-provider";
import { DataSourceProvider } from "@/contexts/data-source-context";
import { useSleepScoringStore } from "@/store";
import type { DiaryEntryResponse } from "@/api/types";
import { DiaryPanel } from "./diary-panel";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a fresh QueryClient pre-seeded with diary data for stories. */
function createSeededQueryClient(fileId: number, entries: DiaryEntryResponse[]): QueryClient {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
    },
  });
  // Pre-populate the diary query cache so the component renders immediately
  client.setQueryData(["diary", fileId, "server"], entries);
  return client;
}

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
      });
    };
  }, [state]);
  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// Mock diary entries
// ---------------------------------------------------------------------------

const DIARY_ENTRIES: DiaryEntryResponse[] = [
  {
    id: 1,
    file_id: 1,
    analysis_date: "2025-01-13",
    bed_time: "10:15 PM",
    lights_out: "10:30 PM",
    wake_time: "6:45 AM",
    got_up: "7:00 AM",
    sleep_quality: 4,
    time_to_fall_asleep_minutes: 15,
    number_of_awakenings: 2,
    notes: null,
    nap_1_start: null,
    nap_1_end: null,
    nap_2_start: null,
    nap_2_end: null,
    nap_3_start: null,
    nap_3_end: null,
    nonwear_1_start: null,
    nonwear_1_end: null,
    nonwear_1_reason: null,
    nonwear_2_start: null,
    nonwear_2_end: null,
    nonwear_2_reason: null,
    nonwear_3_start: null,
    nonwear_3_end: null,
    nonwear_3_reason: null,
  },
  {
    id: 2,
    file_id: 1,
    analysis_date: "2025-01-14",
    bed_time: "11:00 PM",
    lights_out: "11:15 PM",
    wake_time: "7:30 AM",
    got_up: "7:45 AM",
    sleep_quality: 3,
    time_to_fall_asleep_minutes: 20,
    number_of_awakenings: 4,
    notes: "Restless night",
    nap_1_start: "2:00 PM",
    nap_1_end: "3:00 PM",
    nap_2_start: null,
    nap_2_end: null,
    nap_3_start: null,
    nap_3_end: null,
    nonwear_1_start: null,
    nonwear_1_end: null,
    nonwear_1_reason: null,
    nonwear_2_start: null,
    nonwear_2_end: null,
    nonwear_2_reason: null,
    nonwear_3_start: null,
    nonwear_3_end: null,
    nonwear_3_reason: null,
  },
  {
    id: 3,
    file_id: 1,
    analysis_date: "2025-01-15",
    bed_time: "9:30 PM",
    lights_out: "10:00 PM",
    wake_time: "6:00 AM",
    got_up: "6:15 AM",
    sleep_quality: 5,
    time_to_fall_asleep_minutes: 10,
    number_of_awakenings: 1,
    notes: null,
    nap_1_start: "1:30 PM",
    nap_1_end: "2:15 PM",
    nap_2_start: "4:00 PM",
    nap_2_end: "4:30 PM",
    nap_3_start: null,
    nap_3_end: null,
    nonwear_1_start: "5:00 PM",
    nonwear_1_end: "6:00 PM",
    nonwear_1_reason: "Shower",
    nonwear_2_start: null,
    nonwear_2_end: null,
    nonwear_2_reason: null,
    nonwear_3_start: null,
    nonwear_3_end: null,
    nonwear_3_reason: null,
  },
];

/** Entry with AM/PM error: "10:30 AM" onset should be PM for a bedtime. */
const AMPM_ERROR_ENTRY: DiaryEntryResponse = {
  id: 10,
  file_id: 1,
  analysis_date: "2025-01-16",
  bed_time: "10:00 AM", // Likely an AM/PM error
  lights_out: "10:30 AM", // Likely an AM/PM error
  wake_time: "6:45 AM",
  got_up: "7:00 AM",
  sleep_quality: 3,
  time_to_fall_asleep_minutes: 15,
  number_of_awakenings: 2,
  notes: null,
  nap_1_start: null,
  nap_1_end: null,
  nap_2_start: null,
  nap_2_end: null,
  nap_3_start: null,
  nap_3_end: null,
  nonwear_1_start: null,
  nonwear_1_end: null,
  nonwear_1_reason: null,
  nonwear_2_start: null,
  nonwear_2_end: null,
  nonwear_2_reason: null,
  nonwear_3_start: null,
  nonwear_3_end: null,
  nonwear_3_reason: null,
};

// ---------------------------------------------------------------------------
// Provider wrapper
// ---------------------------------------------------------------------------

function DiaryProviders({
  fileId,
  entries,
  storeState,
  children,
}: {
  fileId: number;
  entries: DiaryEntryResponse[];
  storeState: Record<string, unknown>;
  children: React.ReactNode;
}) {
  const queryClient = useMemo(() => createSeededQueryClient(fileId, entries), [fileId, entries]);

  return (
    <ThemeProvider defaultTheme="light" storageKey="storybook-diary">
      <QueryClientProvider client={queryClient}>
        <DataSourceProvider>
          <StoreConfigurator state={storeState}>
            {children}
          </StoreConfigurator>
        </DataSourceProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
}

const BASE_STORE_STATE = {
  currentFileId: 1,
  currentDateIndex: 2, // 2025-01-15 -- third entry
  availableDates: ["2025-01-13", "2025-01-14", "2025-01-15"],
  currentFileSource: "server" as const,
  isAuthenticated: true,
  sitePassword: null,
  username: "storybook",
};

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

const meta = {
  title: "Components/DiaryPanel",
  component: DiaryPanel,
  parameters: {
    layout: "padded",
    docs: {
      description: {
        component:
          "Read-only table showing all sleep diary entries for the current file. " +
          "Displays bed time, onset, offset, nap times, and nonwear periods. " +
          "The current date's row is highlighted. Clicking onset/offset cells places markers from diary times. " +
          "Automatically detects and highlights AM/PM errors in diary times.",
      },
    },
  },
  argTypes: {
    compact: {
      control: "boolean",
      description: "Compact layout for embedding in panels",
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof DiaryPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

/** Full diary with multiple entries, naps, and nonwear periods. The current date (2025-01-15) is highlighted. */
export const WithDiaryData: Story = {
  args: { compact: false },
  decorators: [
    (Story) => (
      <DiaryProviders fileId={1} entries={DIARY_ENTRIES} storeState={BASE_STORE_STATE}>
        <div style={{ maxWidth: 900 }}>
          <Story />
        </div>
      </DiaryProviders>
    ),
  ],
};

/** Compact mode for sidebar embedding. */
export const Compact: Story = {
  args: { compact: true },
  decorators: [
    (Story) => (
      <DiaryProviders fileId={1} entries={DIARY_ENTRIES} storeState={BASE_STORE_STATE}>
        <div style={{ width: 600, height: 300, overflow: "hidden" }}>
          <Story />
        </div>
      </DiaryProviders>
    ),
  ],
};

/** No diary data -- the panel renders nothing (returns null). */
export const NoDiaryData: Story = {
  args: { compact: false },
  decorators: [
    (Story) => (
      <DiaryProviders fileId={1} entries={[]} storeState={BASE_STORE_STATE}>
        <div style={{ maxWidth: 900, minHeight: 100, border: "1px dashed var(--border)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Story />
          <p style={{ color: "var(--muted-foreground)", fontSize: 12 }}>
            (DiaryPanel returns null when no entries exist)
          </p>
        </div>
      </DiaryProviders>
    ),
  ],
};

/** Single entry -- minimal table with one row. */
export const SingleEntry: Story = {
  args: { compact: false },
  decorators: [
    (Story) => (
      <DiaryProviders
        fileId={1}
        entries={[DIARY_ENTRIES[0]!]}
        storeState={{ ...BASE_STORE_STATE, currentDateIndex: 0, availableDates: ["2025-01-13"] }}
      >
        <div style={{ maxWidth: 900 }}>
          <Story />
        </div>
      </DiaryProviders>
    ),
  ],
};

/** Entry with a suspected AM/PM error -- onset time highlighted in amber/red. */
export const WithAmPmError: Story = {
  args: { compact: false },
  decorators: [
    (Story) => (
      <DiaryProviders
        fileId={1}
        entries={[...DIARY_ENTRIES, AMPM_ERROR_ENTRY]}
        storeState={{
          ...BASE_STORE_STATE,
          currentDateIndex: 3,
          availableDates: ["2025-01-13", "2025-01-14", "2025-01-15", "2025-01-16"],
        }}
      >
        <div style={{ maxWidth: 900 }}>
          <Story />
        </div>
      </DiaryProviders>
    ),
  ],
};

/** Entry with naps and nonwear -- columns expand to show all data groups. */
export const WithNapsAndNonwear: Story = {
  args: { compact: false },
  decorators: [
    (Story) => (
      <DiaryProviders
        fileId={1}
        entries={DIARY_ENTRIES}
        storeState={{ ...BASE_STORE_STATE, currentDateIndex: 2 }}
      >
        <div style={{ maxWidth: 1100, overflowX: "auto" }}>
          <Story />
        </div>
      </DiaryProviders>
    ),
  ],
};
