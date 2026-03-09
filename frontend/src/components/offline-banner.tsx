import { useState, useEffect } from "react";
import { useSyncStore } from "@/store/sync-store";
import { WifiOff, Wifi, RefreshCw } from "lucide-react";

/**
 * Banner showing offline/online status with sync info.
 * Pattern adapted from ios-screenshot app's OfflineBanner.
 */
export function OfflineBanner() {
  const { isOnline, pendingCount, syncStatus, lastSyncAt } = useSyncStore();
  const [showBackOnline, setShowBackOnline] = useState(false);
  const [wasOffline, setWasOffline] = useState(false);

  useEffect(() => {
    if (!isOnline) {
      setWasOffline(true);
    } else if (wasOffline) {
      setShowBackOnline(true);
      setWasOffline(false);
      const timer = setTimeout(() => setShowBackOnline(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [isOnline, wasOffline]);

  if (isOnline && !showBackOnline && pendingCount === 0) {
    return null;
  }

  if (showBackOnline) {
    return (
      <div className="flex items-center gap-2 bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 px-4 py-2 text-sm">
        <Wifi className="h-4 w-4" />
        <span>Back online! Your data will sync...</span>
      </div>
    );
  }

  if (!isOnline) {
    return (
      <div className="flex items-center gap-2 bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200 px-4 py-2 text-sm">
        <WifiOff className="h-4 w-4" />
        <span>You&apos;re offline. App works in local mode.</span>
        {pendingCount > 0 && (
          <span className="ml-auto text-xs opacity-75">
            {pendingCount} change{pendingCount !== 1 ? "s" : ""} pending sync
          </span>
        )}
      </div>
    );
  }

  // Online but has pending changes
  if (pendingCount > 0) {
    return (
      <div className="flex items-center gap-2 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 px-4 py-2 text-sm">
        {syncStatus === "syncing" ? (
          <RefreshCw className="h-4 w-4 animate-spin" />
        ) : (
          <RefreshCw className="h-4 w-4" />
        )}
        <span>
          {syncStatus === "syncing"
            ? "Syncing..."
            : `${pendingCount} change${pendingCount !== 1 ? "s" : ""} pending sync`}
        </span>
        {lastSyncAt && (
          <span className="ml-auto text-xs opacity-75">
            Last sync: {new Date(lastSyncAt).toLocaleTimeString()}
          </span>
        )}
      </div>
    );
  }

  return null;
}
