import type { Meta, StoryObj } from "@storybook/react-vite";
import { ErrorBoundary } from "./error-boundary";

/** Component that always throws to trigger the ErrorBoundary. */
function ThrowingChild(): never {
  throw new Error("Test error: Something went wrong in a child component");
}

/** Component that renders normally. */
function HappyChild() {
  return (
    <div className="p-8 text-center">
      <h1 className="text-lg font-bold">Everything is fine</h1>
      <p className="text-muted-foreground">No errors here.</p>
    </div>
  );
}

const meta = {
  title: "Components/ErrorBoundary",
  component: ErrorBoundary,
  parameters: {
    layout: "fullscreen",
    docs: {
      description: {
        component:
          "Global error boundary that catches React render errors and shows a recovery UI " +
          "with reload, reset, and copy-error-details actions instead of a blank white screen.",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ErrorBoundary>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Error state -- the boundary catches a thrown error and shows recovery UI. */
export const WithError: Story = {
  render: () => (
    <ErrorBoundary>
      <ThrowingChild />
    </ErrorBoundary>
  ),
};

/** Normal state -- children render without errors. */
export const NoError: Story = {
  render: () => (
    <ErrorBoundary>
      <HappyChild />
    </ErrorBoundary>
  ),
};
