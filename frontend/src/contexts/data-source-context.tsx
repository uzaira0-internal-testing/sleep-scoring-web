import { createContext, useContext, useMemo } from "react";
import { useSleepScoringStore } from "@/store";
import { useCapabilitiesStore } from "@/store/capabilities-store";
import { type DataSource, getDataSource } from "@/services/data-source";
import { getActiveWorkspaceId, useWorkspaceStore } from "@/store/workspace-store";

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

  // Select only the active workspace's serverUrl — returns a stable primitive string,
  // so Zustand's shallow equality check prevents re-renders from unrelated workspace
  // mutations (e.g. updateLastAccessed changing lastAccessedAt on another field).
  const activeServerUrl = useWorkspaceStore((s) => {
    const wsId = getActiveWorkspaceId();
    return wsId ? (s.workspaces.find((w) => w.id === wsId)?.serverUrl ?? "") : "";
  });

  // Mode is determined by the WORKSPACE, not the capabilities probe.
  // A local workspace (no serverUrl) stays local even if a co-hosted server is reachable.
  // A server workspace uses the server regardless of transient probe state.
  const value = useMemo((): DataSourceContextValue => {
    const isLocal = !activeServerUrl;
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
