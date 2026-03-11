import { useState, useEffect } from "react";
import { BrowserRouter, HashRouter, Routes, Route, Navigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useSleepScoringStore } from "@/store";
import { meApi } from "@/api/client";
import { useCapabilitiesStore } from "@/store/capabilities-store";
import { Layout } from "@/components/layout";
import { LoginPage } from "@/pages/login";
import { ScoringPage } from "@/pages/scoring";
import { StudySettingsPage } from "@/pages/study-settings";
import { DataSettingsPage } from "@/pages/data-settings";
import { AnalysisPage } from "@/pages/analysis";
import { ExportPage } from "@/pages/export";
import { AdminAssignmentsPage } from "@/pages/admin-assignments";
import { config } from "@/config";
import { isTauri } from "@/lib/tauri";
import { getActiveWorkspaceId, useWorkspaceStore } from "@/store/workspace-store";
import { switchDb, getDb } from "@/lib/workspace-db";
import { switchApi } from "@/lib/workspace-api";
import { DataSourceProvider } from "@/contexts/data-source-context";

/**
 * Rehydrate workspace-scoped singletons (Dexie DB, API client) after page reload.
 * sessionStorage preserves the active workspace ID, but the module-level
 * singletons in workspace-db.ts and workspace-api.ts are lost on reload.
 * Returns true if a workspace was successfully rehydrated.
 */
function rehydrateWorkspace(): boolean {
  // Already initialized (not a reload)
  try { getDb(); return true; } catch { /* needs rehydration */ }

  const wsId = getActiveWorkspaceId();
  if (!wsId) return false;

  const ws = useWorkspaceStore.getState().getWorkspace(wsId);
  if (!ws) return false;

  switchDb(ws.dbName);
  switchApi(ws.serverUrl);

  // Restore serverAvailable based on workspace type so DataSourceProvider
  // picks the correct mode immediately (before the async probe completes).
  // Mark serverChecked=true for both cases to prevent probeServer() from
  // re-running — in Tauri local mode there's no server to probe, and for
  // server workspaces we optimistically set available (the probe will correct
  // if the server went offline).
  if (ws.serverUrl) {
    useCapabilitiesStore.getState().setServerAvailable(true);
  } else {
    useCapabilitiesStore.getState().setServerAvailable(false);
  }

  return true;
}

/**
 * Protected route wrapper - redirects to login if not authenticated or no active workspace.
 * Re-fetches admin status on mount only when server is available.
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useSleepScoringStore((state) => state.isAuthenticated);
  const serverAvailable = useCapabilitiesStore((s) => s.serverAvailable);
  const hasActiveWorkspace = getActiveWorkspaceId() !== null;

  // Wait for BOTH stores to hydrate before deciding to redirect.
  // Without this, the first render sees isAuthenticated=false (default)
  // and redirects to /login before localStorage state is restored.
  // The workspace store must also be hydrated so rehydrateWorkspace()
  // can find the workspace record.
  const [hydrated, setHydrated] = useState(
    useSleepScoringStore.persist.hasHydrated() && useWorkspaceStore.persist.hasHydrated()
  );
  const [rehydrated, setRehydrated] = useState(false);

  useEffect(() => {
    if (hydrated) return;
    let mainDone = useSleepScoringStore.persist.hasHydrated();
    let wsDone = useWorkspaceStore.persist.hasHydrated();
    const check = () => { if (mainDone && wsDone) setHydrated(true); };
    const unsub1 = mainDone ? undefined : useSleepScoringStore.persist.onFinishHydration(() => { mainDone = true; check(); });
    const unsub2 = wsDone ? undefined : useWorkspaceStore.persist.onFinishHydration(() => { wsDone = true; check(); });
    return () => { unsub1?.(); unsub2?.(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Rehydrate workspace singletons (page reload case).
  // Runs asynchronously via microtask to satisfy set-state-in-effect rule
  // while still executing before paint (no flicker).
  useEffect(() => {
    if (!hydrated || rehydrated || !isAuthenticated || !hasActiveWorkspace) return;
    // queueMicrotask defers setState so it's no longer synchronous within the effect body
    queueMicrotask(() => setRehydrated(rehydrateWorkspace()));
  }, [hydrated, rehydrated, isAuthenticated, hasActiveWorkspace]);

  useEffect(() => {
    if (!isAuthenticated || !serverAvailable) return;
    meApi.getMe()
      .then((me) => useSleepScoringStore.getState().setIsAdmin(me.is_admin))
      .catch(() => { /* Backend unreachable — keep default isAdmin=false */ });
  }, [isAuthenticated, serverAvailable]);

  // Show loading spinner until persist hydration completes
  if (!hydrated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!isAuthenticated || !hasActiveWorkspace || !rehydrated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

/**
 * Main App component with routing
 */
/**
 * Use HashRouter in Tauri — the asset server always serves index.html for all paths,
 * so BrowserRouter paths are lost on hard refresh (Ctrl+Shift+R). HashRouter persists
 * the route in the URL hash fragment which survives refresh.
 */
const Router = isTauri() ? HashRouter : BrowserRouter;

function App() {
  return (
    <Router {...(isTauri() ? {} : { basename: config.basePath })}>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<LoginPage />} />

        {/* Protected routes with layout */}
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <DataSourceProvider>
                <Layout />
              </DataSourceProvider>
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/scoring" replace />} />
          <Route path="scoring" element={<ScoringPage />} />
          <Route path="analysis" element={<AnalysisPage />} />
          <Route path="export" element={<ExportPage />} />
          <Route path="settings/study" element={<StudySettingsPage />} />
          <Route path="settings/data" element={<DataSettingsPage />} />
          <Route path="admin/assignments" element={<AdminAssignmentsPage />} />
        </Route>

        {/* Catch-all redirect */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
