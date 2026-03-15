/**
 * Tests for workspace-store.
 *
 * Tests the Zustand store actions for workspace CRUD.
 *
 * NOTE: user-state.test.ts uses mock.module to replace @/store/workspace-store
 * functions (getActiveWorkspaceId, etc.), which contaminates imports when running
 * the full suite. Tests that depend on getActiveWorkspaceId/setActiveWorkspaceId
 * are written to be resilient to this by testing the store directly.
 */
import { describe, it, expect, beforeEach } from "bun:test";
import { useWorkspaceStore } from "./workspace-store";

describe("WorkspaceStore", () => {
  beforeEach(() => {
    // Reset store to empty
    useWorkspaceStore.setState({ workspaces: [] });
  });

  describe("createWorkspace", () => {
    it("should create a workspace with generated id and dbName", () => {
      const ws = useWorkspaceStore.getState().createWorkspace("http://localhost:8500", "Test Server");

      expect(ws.id).toBeTruthy();
      expect(ws.displayName).toBe("Test Server");
      expect(ws.serverUrl).toBe("http://localhost:8500");
      expect(ws.dbName).toBe(`SleepScoringDB-${ws.id}`);
      expect(ws.createdAt).toBeTruthy();
      expect(ws.lastAccessedAt).toBeTruthy();
    });

    it("should strip trailing slashes from serverUrl", () => {
      const ws = useWorkspaceStore.getState().createWorkspace("http://localhost:8500///", "Test");
      expect(ws.serverUrl).toBe("http://localhost:8500");
    });

    it("should add workspace to the store", () => {
      // Use createWorkspaceWithId to avoid issues when generateId is mocked
      useWorkspaceStore.getState().createWorkspaceWithId({
        id: "add-test-1",
        displayName: "A",
        serverUrl: "http://a.com",
        dbName: "SleepScoringDB-add-test-1",
        createdAt: new Date().toISOString(),
        lastAccessedAt: new Date().toISOString(),
      });
      useWorkspaceStore.getState().createWorkspaceWithId({
        id: "add-test-2",
        displayName: "B",
        serverUrl: "http://b.com",
        dbName: "SleepScoringDB-add-test-2",
        createdAt: new Date().toISOString(),
        lastAccessedAt: new Date().toISOString(),
      });

      const workspaces = useWorkspaceStore.getState().workspaces;
      expect(workspaces).toHaveLength(2);
      expect(workspaces[0]!.displayName).toBe("A");
      expect(workspaces[1]!.displayName).toBe("B");
    });

    it("should support local-only workspace with empty serverUrl", () => {
      const ws = useWorkspaceStore.getState().createWorkspace("", "Local Only");
      expect(ws.serverUrl).toBe("");
    });
  });

  describe("createWorkspaceWithId", () => {
    it("should add a workspace with a specific ID", () => {
      const entry = {
        id: "custom-id-123",
        displayName: "Migrated",
        serverUrl: "http://example.com",
        dbName: "SleepScoringDB-custom-id-123",
        createdAt: "2024-01-01T00:00:00.000Z",
        lastAccessedAt: "2024-01-01T00:00:00.000Z",
      };

      useWorkspaceStore.getState().createWorkspaceWithId(entry);

      const workspaces = useWorkspaceStore.getState().workspaces;
      expect(workspaces).toHaveLength(1);
      expect(workspaces[0]!.id).toBe("custom-id-123");
    });
  });

  describe("getWorkspace", () => {
    it("should find workspace by id", () => {
      const entry = {
        id: "find-test-1",
        displayName: "Test",
        serverUrl: "http://test.com",
        dbName: "SleepScoringDB-find-test-1",
        createdAt: new Date().toISOString(),
        lastAccessedAt: new Date().toISOString(),
      };
      useWorkspaceStore.getState().createWorkspaceWithId(entry);
      const found = useWorkspaceStore.getState().getWorkspace("find-test-1");
      expect(found).toBeDefined();
      expect(found!.displayName).toBe("Test");
    });

    it("should return undefined for unknown id", () => {
      const found = useWorkspaceStore.getState().getWorkspace("nonexistent");
      expect(found).toBeUndefined();
    });
  });

  describe("updateLastAccessed", () => {
    it("should update lastAccessedAt for the workspace", () => {
      const entry = {
        id: "access-test-1",
        displayName: "Test",
        serverUrl: "http://test.com",
        dbName: "SleepScoringDB-access-test-1",
        createdAt: new Date().toISOString(),
        lastAccessedAt: "2020-01-01T00:00:00.000Z",
      };
      useWorkspaceStore.getState().createWorkspaceWithId(entry);

      useWorkspaceStore.getState().updateLastAccessed("access-test-1");

      const updated = useWorkspaceStore.getState().getWorkspace("access-test-1");
      expect(updated).toBeDefined();
      expect(updated!.lastAccessedAt).toBeTruthy();
      // Should be more recent than the initial value
      expect(new Date(updated!.lastAccessedAt).getTime()).toBeGreaterThan(
        new Date("2020-01-01T00:00:00.000Z").getTime()
      );
    });
  });

  describe("deleteWorkspace", () => {
    it("should refuse to delete the currently active workspace", () => {
      // Import the real setActiveWorkspaceId/getActiveWorkspaceId.
      // NOTE: When user-state.test.ts mocks workspace-store, getActiveWorkspaceId
      // may be replaced. We use the internal store's getActiveWorkspaceId which
      // deleteWorkspace calls. Test by verifying behavior indirectly:
      // create two workspaces, mark neither as active (activeId=null from sessionStorage
      // or "ws-test-123" from mock), and verify delete works for non-matching IDs.
      //
      // We test the "refuse" behavior by checking that deleteWorkspace is a no-op
      // when the workspace ID matches the active ID. Since the active ID in test env
      // is either null or "ws-test-123" (from mock), we test both directions.
      const { setActiveWorkspaceId, getActiveWorkspaceId } = require("./workspace-store");
      const activeId = getActiveWorkspaceId();

      if (activeId) {
        // Mock scenario: activeId is "ws-test-123"
        const entry = {
          id: activeId,
          displayName: "Active",
          serverUrl: "http://test.com",
          dbName: `SleepScoringDB-${activeId}`,
          createdAt: new Date().toISOString(),
          lastAccessedAt: new Date().toISOString(),
        };
        useWorkspaceStore.getState().createWorkspaceWithId(entry);
        useWorkspaceStore.getState().deleteWorkspace(activeId);
        // Should refuse — still exists
        expect(useWorkspaceStore.getState().workspaces).toHaveLength(1);
      } else {
        // Real scenario: no active workspace, so set one
        setActiveWorkspaceId("ws-active-refuse");
        const entry = {
          id: "ws-active-refuse",
          displayName: "Active",
          serverUrl: "http://test.com",
          dbName: "SleepScoringDB-ws-active-refuse",
          createdAt: new Date().toISOString(),
          lastAccessedAt: new Date().toISOString(),
        };
        useWorkspaceStore.getState().createWorkspaceWithId(entry);
        useWorkspaceStore.getState().deleteWorkspace("ws-active-refuse");
        // Should refuse — still exists
        expect(useWorkspaceStore.getState().workspaces).toHaveLength(1);
      }
    });

    it("should delete a workspace that is not active", () => {
      const ws = {
        id: "ws-delete-non-active",
        displayName: "B",
        serverUrl: "http://b.com",
        dbName: "SleepScoringDB-ws-delete-non-active",
        createdAt: new Date().toISOString(),
        lastAccessedAt: new Date().toISOString(),
      };
      useWorkspaceStore.getState().createWorkspaceWithId(ws);

      // This ID does not match any plausible active workspace ID
      useWorkspaceStore.getState().deleteWorkspace("ws-delete-non-active");

      const workspaces = useWorkspaceStore.getState().workspaces;
      expect(workspaces).toHaveLength(0);
    });
  });
});
