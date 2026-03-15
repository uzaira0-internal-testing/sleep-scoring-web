import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ProcessingProgress } from "@/services/local-processing";
import { LocalProcessingProgress } from "./local-processing-progress";

const meta = {
  title: "Components/LocalProcessingProgress",
  component: LocalProcessingProgress,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Progress indicator for the local file processing pipeline. " +
          "Shows phase icons, progress bar, and messages as files are read, " +
          "parsed, epoched, scored, and stored locally via WASM.",
      },
    },
  },
  argTypes: {
    isProcessing: {
      control: "boolean",
      description: "Whether processing is currently active",
    },
  },
  decorators: [
    (Story) => (
      <div style={{ width: 400 }}>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof LocalProcessingProgress>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Reading file phase (initial). */
export const Reading: Story = {
  args: {
    isProcessing: true,
    progress: {
      phase: "reading",
      percent: 25,
      message: "Reading file... 25%",
    } satisfies ProcessingProgress,
  },
};

/** Parsing CSV phase. */
export const Parsing: Story = {
  args: {
    isProcessing: true,
    progress: {
      phase: "parsing",
      percent: 60,
      message: "Parsing CSV data...",
    } satisfies ProcessingProgress,
  },
};

/** Epoching phase. */
export const Epoching: Story = {
  args: {
    isProcessing: true,
    progress: {
      phase: "epoching",
      percent: 40,
      message: "Converting raw data to 60-second epochs...",
    } satisfies ProcessingProgress,
  },
};

/** Scoring phase. */
export const Scoring: Story = {
  args: {
    isProcessing: true,
    progress: {
      phase: "scoring",
      percent: 80,
      message: "Running Sadeh 1994 algorithm...",
    } satisfies ProcessingProgress,
  },
};

/** Storing results phase. */
export const Storing: Story = {
  args: {
    isProcessing: true,
    progress: {
      phase: "storing",
      percent: 90,
      message: "Saving results to local database...",
    } satisfies ProcessingProgress,
  },
};

/** Complete phase. */
export const Complete: Story = {
  args: {
    isProcessing: false,
    progress: {
      phase: "complete",
      percent: 100,
      message: "Done",
    } satisfies ProcessingProgress,
  },
};

/** Not processing and not complete (renders nothing). */
export const Idle: Story = {
  args: {
    isProcessing: false,
    progress: {
      phase: "reading",
      percent: 0,
      message: "",
    } satisfies ProcessingProgress,
  },
};
