import { createContext, useContext, useMemo } from "react";
import { useSleepScoringStore } from "@/store";
import { useCapabilitiesStore } from "@/store/capabilities-store";
import { type DataSource, getDataSource } from "@/services/data-source";
import { useActiveWorkspaceId, useWorkspaceStore } from "@/store/workspace-store";
import { isTauri } from "@/lib/tauri";

interface DataSourceContextValue {
  dataSource: DataSource;
  isLocal: boolean;
  serverAvailable: boolean;
}

const DataSourceContext = createContext<DataSourceContextValue | null>(null);

export function DataSourceProvider({ children }: { children: React.ReactNode }) {
  const sitePassword = useSleepScoringStore((s) => s.sitePassword);
  const username = useSleepScoringStore((s) => s.username);
  const serverAvailable = useCapabilitiesStore((s) => s.serverAvailable);

  // Reactively track the active workspace ID (backed by a small Zustand store).
  const activeWsId = useActiveWorkspaceId();

  // Select only the active workspace's serverUrl — returns a stable primitive string.
  const activeServerUrl = useWorkspaceStore((s) => {
    return activeWsId ? (s.workspaces.find((w) => w.id === activeWsId)?.serverUrl ?? "") : "";
  });

  // In browser (non-Tauri) mode, the backend is always co-hosted at the same origin.
  // An empty serverUrl means "use relative URLs" (co-hosted), NOT "local/offline".
  // Only Tauri desktop apps can truly run in local mode (no server).
  const value = useMemo((): DataSourceContextValue => {
    const isLocal = isTauri() && !activeServerUrl;
    const source = isLocal ? "local" : "server";
    const dataSource = getDataSource(source, sitePassword, username);
    return { dataSource, isLocal, serverAvailable };
  }, [sitePassword, username, serverAvailable, activeServerUrl]);

  return (
    <DataSourceContext.Provider value={value}>
      {children}
    </DataSourceContext.Provider>
  );
}

export function useDataSource(): DataSourceContextValue {
  const ctx = useContext(DataSourceContext);
  if (!ctx) {
    throw new Error("useDataSource must be used within a DataSourceProvider");
  }
  return ctx;
}
