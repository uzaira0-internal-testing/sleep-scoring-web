import type { Meta, StoryObj } from "@storybook/react-vite";
import { ThemeProvider, useTheme } from "./theme-provider";

/** Demo component that displays the current theme state. */
function ThemeDisplay() {
  const { theme, resolvedTheme, setTheme } = useTheme();
  return (
    <div className="p-6 space-y-4 rounded-lg border bg-background text-foreground">
      <div>
        <span className="text-sm font-medium">Theme setting:</span>{" "}
        <span className="font-mono text-sm">{theme}</span>
      </div>
      <div>
        <span className="text-sm font-medium">Resolved theme:</span>{" "}
        <span className="font-mono text-sm">{resolvedTheme}</span>
      </div>
      <div className="flex gap-2">
        <button
          className="px-3 py-1.5 text-sm rounded border hover:bg-accent"
          onClick={() => setTheme("light")}
        >
          Light
        </button>
        <button
          className="px-3 py-1.5 text-sm rounded border hover:bg-accent"
          onClick={() => setTheme("dark")}
        >
          Dark
        </button>
        <button
          className="px-3 py-1.5 text-sm rounded border hover:bg-accent"
          onClick={() => setTheme("system")}
        >
          System
        </button>
      </div>
    </div>
  );
}

const meta = {
  title: "Components/ThemeProvider",
  component: ThemeProvider,
  parameters: {
    layout: "centered",
    docs: {
      description: {
        component:
          "Context provider for light/dark/system theme switching. " +
          "Manages theme state, persists to localStorage, and applies " +
          "the resolved theme class to the document root element.",
      },
    },
  },
  tags: ["autodocs"],
} satisfies Meta<typeof ThemeProvider>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Light theme (default). */
export const Light: Story = {
  render: () => (
    <ThemeProvider defaultTheme="light" storageKey="storybook-theme-light">
      <ThemeDisplay />
    </ThemeProvider>
  ),
};

/** Dark theme. */
export const Dark: Story = {
  render: () => (
    <ThemeProvider defaultTheme="dark" storageKey="storybook-theme-dark">
      <ThemeDisplay />
    </ThemeProvider>
  ),
};

/** System theme -- resolves based on OS preference. */
export const System: Story = {
  render: () => (
    <ThemeProvider defaultTheme="system" storageKey="storybook-theme-system">
      <ThemeDisplay />
    </ThemeProvider>
  ),
};
