import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";
import type { TusProgress } from "@/hooks/useTusUpload";
import { UploadProgress } from "./upload-progress";

const meta = {
  title: "Components/UploadProgress",
  component: UploadProgress,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Upload progress indicator for TUS resumable uploads. " +
          "Shows compression, upload, and server-side processing phases " +
          "with progress bar, speed, ETA, and pause/cancel controls.",
      },
    },
  },
  args: {
    onPause: fn(),
    onResume: fn(),
    onCancel: fn(),
    onDismiss: fn(),
    isPaused: false,
  },
  decorators: [
    (Story) => (
      <div style={{ width: 400 }}>
        <Story />
      </div>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof UploadProgress>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Idle state -- renders nothing. */
export const Idle: Story = {
  args: {
    progress: {
      phase: "idle",
      percent: 0,
      bytesUploaded: 0,
      bytesTotal: 0,
      speed: 0,
      eta: 0,
      fileName: "participant_001.csv",
      error: null,
    } satisfies TusProgress,
  },
};

/** Compressing phase. */
export const Compressing: Story = {
  args: {
    progress: {
      phase: "compressing",
      percent: 45,
      bytesUploaded: 0,
      bytesTotal: 0,
      speed: 0,
      eta: 0,
      fileName: "participant_001.csv",
      error: null,
    } satisfies TusProgress,
  },
};

/** Uploading phase with progress, speed, and ETA. */
export const Uploading: Story = {
  args: {
    progress: {
      phase: "uploading",
      percent: 65,
      bytesUploaded: 15_728_640,
      bytesTotal: 24_117_248,
      speed: 2_097_152,
      eta: 4,
      fileName: "participant_001.csv",
      error: null,
    } satisfies TusProgress,
  },
};

/** Uploading phase while paused. */
export const Paused: Story = {
  args: {
    isPaused: true,
    progress: {
      phase: "uploading",
      percent: 40,
      bytesUploaded: 9_437_184,
      bytesTotal: 24_117_248,
      speed: 0,
      eta: 0,
      fileName: "participant_001.csv",
      error: null,
    } satisfies TusProgress,
  },
};

/** Upload complete. */
export const Done: Story = {
  args: {
    progress: {
      phase: "done",
      percent: 100,
      bytesUploaded: 24_117_248,
      bytesTotal: 24_117_248,
      speed: 0,
      eta: 0,
      fileName: "participant_001.csv",
      error: null,
    } satisfies TusProgress,
  },
};

/** Error state. */
export const Error: Story = {
  args: {
    progress: {
      phase: "error",
      percent: 40,
      bytesUploaded: 9_437_184,
      bytesTotal: 24_117_248,
      speed: 0,
      eta: 0,
      fileName: "participant_001.csv",
      error: "Network connection lost. Please try again.",
    } satisfies TusProgress,
  },
};
