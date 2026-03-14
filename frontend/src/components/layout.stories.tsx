import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ThemeProvider } from "@/components/theme-provider";
import { useSleepScoringStore } from "@/store";
import { Layout } from "./layout";

/**
 * The main application layout with a collapsible sidebar, navigation,
 * user info, and theme toggle. Stories mock the Zustand stores and
 * router context so the component renders in isolation.
 *
 * Note: The Layout component reads from multiple Zustand stores
 * (useSleepScoringStore, useWorkspaceStore, useCapabilitiesStore)
 * and hooks (useConnectivity, useAppCapabilities). In Storybook,
 * these use their default/initial state unless overridden via
 * Zustand's setState before rendering.
 */

/** Placeholder content rendered inside the Layout's <Outlet />. */
function PageContent({ title, description }: { title: string; description: string }) {
  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-2">{title}</h1>
      <p className="text-muted-foreground">{description}</p>
    </div>
  );
}

/** Decorator factory that wraps Layout in MemoryRouter + ThemeProvider. */
function withProviders(initialPath: string, theme: "light" | "dark" | "system" = "light") {
  return function Decorator(Story: React.ComponentType) {
    return (
      <ThemeProvider defaultTheme={theme} storageKey={`storybook-theme-${theme}`}>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route element={<Story />}>
              <Route
                path="*"
                element={
                  <PageContent
                    title="Page Content"
                    description={'This area is rendered by the <Outlet /> inside the Layout. In the real app, this would be a scoring page, analysis page, etc.'}
                  />
                }
              />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>
    );
  };
}

/** Helper component that sets Zustand store state on mount and cleans up on unmount. */
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
      // Reset the fields we touched
      const resetState: Record<string, unknown> = {};
      for (const key of Object.keys(state)) {
        resetState[key] = key === "username" ? "" : key === "isAuthenticated" ? false : null;
      }
      useSleepScoringStore.setState(resetState);
    };
  }, [state]);
  return <>{children}</>;
}

const meta = {
  title: "Layout/AppLayout",
  component: Layout,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Layout>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Default state with sidebar expanded, on the Scoring page.
 * The sidebar shows navigation items, user avatar, theme toggle,
 * and connection status.
 */
export const Default: Story = {
  decorators: [withProviders("/scoring")],
};

/**
 * Layout when viewing the Analysis page -- the Analysis nav item
 * should appear as active/highlighted.
 */
export const AnalysisActive: Story = {
  name: "Analysis Page Active",
  decorators: [withProviders("/analysis")],
};

/**
 * Layout when viewing the Study settings page.
 */
export const SettingsActive: Story = {
  name: "Settings Page Active",
  decorators: [withProviders("/settings/study")],
};

/**
 * Layout when viewing the Export page.
 */
export const ExportActive: Story = {
  name: "Export Page Active",
  decorators: [withProviders("/export")],
};

/**
 * Layout when viewing the Data/Files page.
 */
export const DataActive: Story = {
  name: "Data Page Active",
  decorators: [withProviders("/settings/data")],
};

/**
 * Sidebar collapsed state. The sidebar width goes to 0 and a small
 * expand button appears on the left edge of the content area.
 *
 * This story sets localStorage to simulate the collapsed state,
 * since the Layout reads the initial collapsed value from localStorage.
 */
export const SidebarCollapsed: Story = {
  decorators: [
    (Story: React.ComponentType) => {
      useEffect(() => {
        try {
          localStorage.setItem("sidebar-collapsed", "true");
        } catch {
          // ignore
        }
        return () => {
          try {
            localStorage.removeItem("sidebar-collapsed");
          } catch {
            // ignore
          }
        };
      }, []);

      return (
        <ThemeProvider defaultTheme="light" storageKey="storybook-theme">
          <MemoryRouter initialEntries={["/scoring"]}>
            <Routes>
              <Route element={<Story />}>
                <Route
                  path="*"
                  element={
                    <PageContent
                      title="Collapsed Sidebar"
                      description="The sidebar is collapsed. Click the expand button on the left edge to open it."
                    />
                  }
                />
              </Route>
            </Routes>
          </MemoryRouter>
        </ThemeProvider>
      );
    },
  ],
};

/**
 * Dark theme variant. The ThemeProvider is initialized with "dark"
 * so the entire layout renders in dark mode.
 */
export const DarkTheme: Story = {
  decorators: [withProviders("/scoring", "dark")],
};

/**
 * Shows the layout with upload progress visible -- the progress
 * bar appears between the banners and the main content area.
 */
export const WithUploadProgress: Story = {
  decorators: [
    (Story: React.ComponentType) => (
      <StoreConfigurator state={{ uploadProgress: "Uploading participant_001.csv... 45%" }}>
        {withProviders("/scoring")(Story)}
      </StoreConfigurator>
    ),
  ],
};

/**
 * Layout with a logged-in user whose name is displayed in the
 * sidebar footer avatar and username area.
 */
export const WithUsername: Story = {
  decorators: [
    (Story: React.ComponentType) => (
      <StoreConfigurator state={{ username: "Dr. Smith", isAuthenticated: true }}>
        {withProviders("/scoring")(Story)}
      </StoreConfigurator>
    ),
  ],
};
