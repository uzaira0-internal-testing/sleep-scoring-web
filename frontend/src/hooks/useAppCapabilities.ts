/**
 * Hook that detects app capabilities by probing the backend.
 * Caches successful results for 60s, re-probes on `online` event.
 */
import { useEffect, useMemo } from "react";
import { useCapabilitiesStore } from "@/store/capabilities-store";
import { buildCapabilities, type AppCapabilities } from "@/lib/app-capabilities";

export function useAppCapabilities(): AppCapabilities {
  const { serverAvailable, serverChecked, groupConfigured, probeServer, resetProbeCache } =
    useCapabilitiesStore();

  useEffect(() => {
    if (!serverChecked) {
      probeServer();
    }

    const handleOnline = () => {
      resetProbeCache();
      probeServer();
    };
    window.addEventListener("online", handleOnline);
    return () => window.removeEventListener("online", handleOnline);
  }, [serverChecked, probeServer, resetProbeCache]);

  return useMemo(
    () => buildCapabilities(serverAvailable, groupConfigured),
    [serverAvailable, groupConfigured],
  );
}
