/**
 * Dynamic Dexie instance manager.
 * Manages which IndexedDB database is active (one per workspace).
 */
import { SleepScoringDB } from "@/db/schema";

let currentDb: SleepScoringDB | null = null;

/**
 * Get the current workspace's database. Throws if none is active.
 */
export function getDb(): SleepScoringDB {
  if (!currentDb) {
    throw new Error("No workspace database is active. Call switchDb() first.");
  }
  return currentDb;
}

/**
 * Switch to a different workspace database. Closes the previous one.
 */
export function switchDb(dbName: string): void {
  if (currentDb) {
    currentDb.close();
  }
  currentDb = new SleepScoringDB(dbName);
}

/**
 * Close the current database (e.g., on sign-out).
 */
export function closeDb(): void {
  if (currentDb) {
    currentDb.close();
    currentDb = null;
  }
}
