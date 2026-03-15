import type { Meta, StoryObj } from "@storybook/react-vite";
import { ThemeProvider } from "@/components/theme-provider";
import { ConsensusPanel } from "./consensus-panel";

/**
 * The ConsensusPanel fetches data from the API and only renders when 2+
 * annotations exist. In Storybook without a real backend, it renders null.
 * This story documents the component's existence and props.
 */
const meta = {
  title: "Components/ConsensusPanel",
  component: ConsensusPanel,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Consensus panel showing multiple scorer annotations for comparison and admin resolution. " +
          "Renders only when 2+ submitted annotations exist for the current file/date. " +
          "Requires a live backend connection to display data.",
      },
    },
  },
  argTypes: {
    compact: {
      control: "boolean",
      description: "Compact layout for sidebar embedding",
    },
  },
  decorators: [
    (Story) => (
      <ThemeProvider defaultTheme="light" storageKey="storybook-consensus-panel">
        <div style={{ width: 320, minHeight: 200 }}>
          <Story />
        </div>
      </ThemeProvider>
    ),
  ],
  tags: ["autodocs"],
} satisfies Meta<typeof ConsensusPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Default state -- without a backend the panel renders nothing (null). */
export const Default: Story = {
  args: {
    compact: false,
  },
};

/** Compact variant for sidebar embedding. */
export const Compact: Story = {
  args: {
    compact: true,
  },
};
