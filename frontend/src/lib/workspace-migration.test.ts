import { describe, it, expect, beforeEach } from "bun:test";
import { migrateFromLegacy } from "./workspace-migration";
import { useWorkspaceStore } from "@/store/workspace-store";

const MIGRATION_KEY = "sleep-scoring-workspace-migration-done";

describe("workspace-migration", () => {
  beforeEach(() => {
    // Reset store and clear localStorage
    useWorkspaceStore.setState({ workspaces: [] });
    localStorage.clear();
  });

  it("sets migration done key on first run with no legacy data", () => {
    migrateFromLegacy();
    expect(localStorage.getItem(MIGRATION_KEY)).toBe("1");
  });

  it("is idempotent — does not run twice", () => {
    localStorage.setItem(MIGRATION_KEY, "1");
    // Should be a no-op
    migrateFromLegacy();
    expect(useWorkspaceStore.getState().workspaces).toHaveLength(0);
  });

  it("skips if workspaces already exist", () => {
    useWorkspaceStore.getState().createWorkspaceWithId({
      id: "existing",
      displayName: "Existing",
      serverUrl: "",
      dbName: "SleepScoringDB-existing",
      createdAt: new Date().toISOString(),
      lastAccessedAt: new Date().toISOString(),
    });

    migrateFromLegacy();

    expect(localStorage.getItem(MIGRATION_KEY)).toBe("1");
    // Should not add another workspace
    expect(useWorkspaceStore.getState().workspaces).toHaveLength(1);
  });

  it("creates a workspace from legacy data", () => {
    localStorage.setItem("sleep-scoring-storage", JSON.stringify({ state: {} }));

    migrateFromLegacy();

    const workspaces = useWorkspaceStore.getState().workspaces;
    expect(workspaces).toHaveLength(1);
    expect(workspaces[0]!.dbName).toBe("SleepScoringDB");
    expect(workspaces[0]!.displayName).toBe("Default");
  });

  it("reads legacy server URL from localStorage", () => {
    localStorage.setItem("sleep-scoring-storage", JSON.stringify({ state: {} }));
    localStorage.setItem(
      "sleep-scoring-server-settings",
      JSON.stringify({ state: { serverUrl: "http://server:8500" } }),
    );

    migrateFromLegacy();

    const workspaces = useWorkspaceStore.getState().workspaces;
    expect(workspaces[0]!.serverUrl).toBe("http://server:8500");
    expect(workspaces[0]!.displayName).toBe("Default Server");
  });

  it("copies legacy storage to workspace-scoped key", () => {
    const legacyData = JSON.stringify({ state: { key: "value" } });
    localStorage.setItem("sleep-scoring-storage", legacyData);

    migrateFromLegacy();

    const workspaces = useWorkspaceStore.getState().workspaces;
    const id = workspaces[0]!.id;
    expect(localStorage.getItem(`sleep-scoring-storage-${id}`)).toBe(legacyData);
  });

  it("migrates user preference keys", () => {
    // Skip if localStorage.key is not available (e.g., mocked by another test)
    if (typeof localStorage.key !== "function") return;

    localStorage.setItem("sleep-scoring-storage", JSON.stringify({ state: {} }));
    localStorage.setItem("sleep-scoring-user-prefs-alice", JSON.stringify({ theme: "dark" }));

    migrateFromLegacy();

    const workspaces = useWorkspaceStore.getState().workspaces;
    expect(workspaces.length).toBeGreaterThan(0);
    const id = workspaces[0]!.id;
    expect(localStorage.getItem(`sleep-scoring-prefs-${id}-alice`)).toBe(
      JSON.stringify({ theme: "dark" }),
    );
  });

  it("handles malformed server settings JSON gracefully", () => {
    localStorage.setItem("sleep-scoring-storage", JSON.stringify({ state: {} }));
    localStorage.setItem("sleep-scoring-server-settings", "not-json");

    // Should not throw
    migrateFromLegacy();

    const workspaces = useWorkspaceStore.getState().workspaces;
    expect(workspaces).toHaveLength(1);
    expect(workspaces[0]!.serverUrl).toBe("");
  });
});
