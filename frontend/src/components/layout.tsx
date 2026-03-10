import { useState } from "react";
import { Outlet, Link, useLocation, useNavigate } from "react-router-dom";
import { Settings, Database, Activity, Download, LogOut, Moon, Sun, Monitor, BarChart3, ChevronLeft, ChevronRight, Loader2, Wifi, WifiOff, FolderOpen, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/components/theme-provider";
import { useSleepScoringStore } from "@/store";
import { cn } from "@/lib/utils";
import { OfflineBanner } from "@/components/offline-banner";
import { useConnectivity } from "@/hooks/useConnectivity";
import { useAppCapabilities } from "@/hooks/useAppCapabilities";
import { useWorkspaceStore, getActiveWorkspaceId, clearActiveWorkspaceId } from "@/store/workspace-store";
import { closeDb } from "@/lib/workspace-db";

/**
 * Main application layout with collapsible sidebar navigation
 */
export function Layout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { theme, setTheme } = useTheme();
  const username = useSleepScoringStore((state) => state.username);
  const clearAuth = useSleepScoringStore((state) => state.clearAuth);
  const uploadProgress = useSleepScoringStore((state) => state.uploadProgress);
  const caps = useAppCapabilities();

  // Get active workspace name
  const wsId = getActiveWorkspaceId();
  const workspace = useWorkspaceStore((s) => s.workspaces.find((w) => w.id === wsId));

  useConnectivity(caps.server);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    try {
      return localStorage.getItem("sidebar-collapsed") === "true";
    } catch {
      return false;
    }
  });

  const toggleSidebar = () => {
    const next = !sidebarCollapsed;
    setSidebarCollapsed(next);
    try {
      localStorage.setItem("sidebar-collapsed", String(next));
    } catch {
      // Ignore localStorage errors
    }
  };

  const cycleTheme = () => {
    if (theme === "light") setTheme("dark");
    else if (theme === "dark") setTheme("system");
    else setTheme("light");
  };

  const handleSignOut = () => {
    // clearAuth() already saves user preferences and clears queryClient
    clearAuth();

    // Workspace-specific cleanup
    closeDb();
    clearActiveWorkspaceId();

    navigate("/login");
  };

  const themeIcon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;
  const ThemeIcon = themeIcon;

  const isAdmin = useSleepScoringStore((state) => state.isAdmin);

  const navItems = [
    { path: "/scoring", label: "Scoring", icon: Activity, description: "Score sleep data" },
    { path: "/analysis", label: "Analysis", icon: BarChart3, description: "Summary & progress" },
    { path: "/settings/study", label: "Study", icon: Settings, description: "Algorithm & rules" },
    { path: "/settings/data", label: caps.server ? "Data" : "Files", icon: caps.server ? Database : FolderOpen, description: caps.server ? "Import settings" : "Open & manage files" },
    { path: "/export", label: "Export", icon: Download, description: caps.server ? "Download results" : "Save results" },
    ...(isAdmin && caps.server ? [{ path: "/admin/assignments", label: "Assignments", icon: Users, description: "Manage file assignments" }] : []),
  ];

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className={cn(
        "border-r border-border/60 bg-sidebar flex flex-col transition-all duration-200",
        sidebarCollapsed ? "w-0 overflow-hidden" : "w-60"
      )}>
        {/* Brand */}
        <div className="h-14 border-b border-border/60 flex items-center px-5 gap-3">
          <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center flex-none">
            <Activity className="h-4.5 w-4.5 text-primary" />
          </div>
          <div className="flex flex-col min-w-0">
            <span className="font-semibold text-sm leading-tight tracking-tight whitespace-nowrap">Sleep Scoring</span>
            <span className="text-xs text-muted-foreground leading-tight whitespace-nowrap truncate">
              {workspace?.displayName ?? "Research Tool"}
            </span>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={cn(
                  "group flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150",
                  isActive
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-sidebar-foreground hover:bg-sidebar-accent"
                )}
              >
                <Icon className={cn("h-4 w-4 shrink-0", isActive ? "" : "opacity-60 group-hover:opacity-100")} />
                <div className="flex flex-col min-w-0">
                  <span className="truncate">{item.label}</span>
                  {!isActive && (
                    <span className="text-xs text-muted-foreground truncate leading-tight">
                      {item.description}
                    </span>
                  )}
                </div>
              </Link>
            );
          })}
        </nav>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-border/60 space-y-3">
          {/* Mode indicator */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            {caps.server ? (
              <><Wifi className="h-3.5 w-3.5 text-green-500" /><span>Connected</span></>
            ) : (
              <><WifiOff className="h-3.5 w-3.5 text-yellow-500" /><span>Local Mode</span></>
            )}
          </div>
          {/* User */}
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center text-xs font-medium text-primary flex-none">
              {(username || "A").charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-xs font-medium truncate">
                {username || "Anonymous"}
              </div>
              <div className="text-xs text-muted-foreground">Scorer</div>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 flex-1 justify-start gap-2 text-xs text-muted-foreground"
              onClick={cycleTheme}
              title={`Theme: ${theme}`}
            >
              <ThemeIcon className="h-3.5 w-3.5" />
              {theme === "light" ? "Light" : theme === "dark" ? "Dark" : "Auto"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 px-2 text-muted-foreground hover:text-destructive"
              onClick={handleSignOut}
              title="Sign out"
            >
              <LogOut className="h-3.5 w-3.5" />
            </Button>
          </div>

          {/* Collapse button */}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-full justify-center text-xs text-muted-foreground"
            onClick={toggleSidebar}
            title="Collapse sidebar"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </Button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden relative">
        {sidebarCollapsed && (
          <button
            onClick={toggleSidebar}
            className="absolute left-0 top-3 z-50 h-8 w-5 flex items-center justify-center bg-muted/80 hover:bg-muted border border-l-0 border-border/60 rounded-r-md transition-colors"
            title="Expand sidebar"
          >
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
          </button>
        )}
        {caps.server && <OfflineBanner />}
        {uploadProgress && (
          <div className="flex items-center gap-2 px-4 py-1.5 bg-primary/10 border-b border-primary/20 text-sm text-primary">
            <Loader2 className="h-3.5 w-3.5 animate-spin flex-shrink-0" />
            <span className="truncate">{uploadProgress}</span>
          </div>
        )}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
