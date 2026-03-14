import type { Meta, StoryObj } from "@storybook/react-vite";
import type { SleepMetrics } from "@/api/types";
import { MetricsPanel } from "./metrics-panel";

// ---------------------------------------------------------------------------
// Mock data
// ---------------------------------------------------------------------------

/** Realistic metrics for a good night of sleep (~8 hours). */
const GOOD_SLEEP_METRICS: SleepMetrics = {
  in_bed_time: "22:30",
  out_bed_time: "06:45",
  sleep_onset: "22:45",
  sleep_offset: "06:30",
  time_in_bed_minutes: 495,
  total_sleep_time_minutes: 465,
  sleep_onset_latency_minutes: 15,
  waso_minutes: 15,
  number_of_awakenings: 3,
  average_awakening_length_minutes: 5,
  sleep_efficiency: 93.9,
  movement_index: 8.2,
  fragmentation_index: 4.1,
  sleep_fragmentation_index: 12.3,
  total_activity: 2450,
  nonzero_epochs: 38,
};

/** Metrics with warning-level values (short TST, low SE, high WASO). */
const WARNING_METRICS: SleepMetrics = {
  in_bed_time: "23:00",
  out_bed_time: "04:30",
  sleep_onset: "01:15",
  sleep_offset: "04:00",
  time_in_bed_minutes: 330,
  total_sleep_time_minutes: 100, // Below 120m threshold
  sleep_onset_latency_minutes: 135, // Above 120m threshold
  waso_minutes: 195, // Above 180m threshold
  number_of_awakenings: 12,
  average_awakening_length_minutes: 16.25,
  sleep_efficiency: 30.3, // Below 50% threshold
  movement_index: 22.5,
  fragmentation_index: 18.7,
  sleep_fragmentation_index: 41.2,
  total_activity: 8900,
  nonzero_epochs: 95,
};

/** Minimal nap metrics. */
const NAP_METRICS: SleepMetrics = {
  in_bed_time: "14:00",
  out_bed_time: "15:30",
  sleep_onset: "14:10",
  sleep_offset: "15:20",
  time_in_bed_minutes: 90,
  total_sleep_time_minutes: 70,
  sleep_onset_latency_minutes: 10,
  waso_minutes: 10,
  number_of_awakenings: 1,
  average_awakening_length_minutes: 10,
  sleep_efficiency: 77.8,
  movement_index: 5.0,
  fragmentation_index: 3.0,
  sleep_fragmentation_index: 8.0,
  total_activity: 450,
  nonzero_epochs: 12,
};

// ---------------------------------------------------------------------------
// Meta
// ---------------------------------------------------------------------------

const meta = {
  title: "Components/MetricsPanel",
  component: MetricsPanel,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Displays Tudor-Locke sleep quality metrics for the selected sleep period. " +
          "Shows duration (TST, TIB, WASO, SOL), quality (SE, MI, FI), and awakening metrics. " +
          "Highlights metric values that exceed physiological warning thresholds in amber.",
      },
    },
  },
  argTypes: {
    selectedPeriodIndex: {
      control: { type: "number", min: 0, max: 2 },
      description: "Index of the selected sleep period",
    },
    compact: {
      control: "boolean",
      description: "Compact layout for sidebar panels",
    },
  },
  tags: ["autodocs"],
  decorators: [
    (Story) => (
      <div style={{ width: 320, minHeight: 400, border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof MetricsPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

// ---------------------------------------------------------------------------
// Stories
// ---------------------------------------------------------------------------

/** Full metrics display for a healthy night of sleep. */
export const WithFullMetrics: Story = {
  args: {
    metrics: [GOOD_SLEEP_METRICS],
    selectedPeriodIndex: 0,
    compact: false,
  },
};

/** Compact mode -- used in sidebar panels with abbreviated labels. */
export const Compact: Story = {
  args: {
    metrics: [GOOD_SLEEP_METRICS],
    selectedPeriodIndex: 0,
    compact: true,
  },
};

/** No period selected -- shows "Select a sleep marker" prompt. */
export const NoPeriodSelected: Story = {
  args: {
    metrics: [GOOD_SLEEP_METRICS],
    selectedPeriodIndex: null,
    compact: false,
  },
};

/** Empty metrics array (no markers placed yet). */
export const EmptyMetrics: Story = {
  args: {
    metrics: [],
    selectedPeriodIndex: null,
    compact: false,
  },
};

/** Metrics with warning thresholds triggered (amber highlighting). */
export const WithWarnings: Story = {
  args: {
    metrics: [WARNING_METRICS],
    selectedPeriodIndex: 0,
    compact: false,
  },
};

/** Compact mode with warnings. */
export const CompactWithWarnings: Story = {
  args: {
    metrics: [WARNING_METRICS],
    selectedPeriodIndex: 0,
    compact: true,
  },
};

/** Multiple sleep periods -- main sleep + nap. Selecting period 0 shows main sleep. */
export const MultiplePeriods: Story = {
  args: {
    metrics: [GOOD_SLEEP_METRICS, NAP_METRICS],
    selectedPeriodIndex: 0,
    compact: false,
  },
};

/** Multiple sleep periods -- selecting the nap (period 1). */
export const NapSelected: Story = {
  args: {
    metrics: [GOOD_SLEEP_METRICS, NAP_METRICS],
    selectedPeriodIndex: 1,
    compact: false,
  },
};

/** Compact panel with no period selected. */
export const CompactEmpty: Story = {
  args: {
    metrics: [],
    selectedPeriodIndex: null,
    compact: true,
  },
};
