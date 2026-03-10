import { useEffect, useRef } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
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
  if (ws.serverUrl) {
    useCapabilitiesStore.getState().setServerAvailable(true);
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
  const rehydrated = useRef(false);

  // Rehydrate workspace singletons on first render (page reload case)
  if (!rehydrated.current && isAuthenticated && hasActiveWorkspace) {
    rehydrated.current = rehydrateWorkspace();
  }

  useEffect(() => {
    if (!isAuthenticated || !serverAvailable) return;
    meApi.getMe()
      .then((me) => useSleepScoringStore.getState().setIsAdmin(me.is_admin))
      .catch(() => { /* Backend unreachable — keep default isAdmin=false */ });
  }, [isAuthenticated, serverAvailable]);

  if (!isAuthenticated || !hasActiveWorkspace || !rehydrated.current) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

/**
 * Main App component with routing
 */
function App() {
  return (
    <BrowserRouter basename={config.basePath}>
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
    </BrowserRouter>
  );
}

export default App;
