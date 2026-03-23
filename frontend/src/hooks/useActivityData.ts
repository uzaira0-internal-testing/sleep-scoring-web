import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSleepScoringStore } from "@/store";
import { useDataSource } from "@/contexts/data-source-context";
import type { ActivityData } from "@/services/data-source";

/** Empty sentinel to avoid re-creating empty arrays on every render. */
const EMPTY_ARRAY: number[] = [];
const EMPTY_SENSOR_NONWEAR: ActivityData["sensorNonwearPeriods"] = [];

/**
 * Hook that fetches and exposes activity data via React Query.
 *
 * This is the single source of truth for activity data -- no copy in Zustand.
 * The query key matches the one in scoring.tsx so the cache is shared:
 * both the scoring page (which triggers the fetch) and ActivityPlot (which
 * reads the data) hit the same cache entry.
 */
export function useActivityData(): {
  timestamps: number[];
  axisX: number[];
  axisY: number[];
  axisZ: number[];
  vectorMagnitude: number[];
  algorithmResults: number[] | null;
  nonwearResults: number[] | null;
  sensorNonwearPeriods: ActivityData["sensorNonwearPeriods"];
  isLoading: boolean;
  preferredDisplayColumn: "axis_x" | "axis_y" | "axis_z" | "vector_magnitude";
  viewStart: number | null;
  viewEnd: number | null;
} {
  const { dataSource, isLocal } = useDataSource();

  // Read store values needed for query key + display preference
  const currentFileId = useSleepScoringStore((s) => s.currentFileId);
  const currentDateIndex = useSleepScoringStore((s) => s.currentDateIndex);
  const availableDates = useSleepScoringStore((s) => s.availableDates);
  const viewModeHours = useSleepScoringStore((s) => s.viewModeHours);
  const currentAlgorithm = useSleepScoringStore((s) => s.currentAlgorithm);
  const preferredDisplayColumn = useSleepScoringStore((s) => s.preferredDisplayColumn);

  const currentDate = availableDates[currentDateIndex] ?? null;

  const { data, isLoading } = useQuery({
    queryKey: ["activity", currentFileId, currentDate, viewModeHours, currentAlgorithm, isLocal ? "local" : "server"],
    queryFn: () =>
      dataSource.loadActivityData(currentFileId!, currentDate!, {
        algorithm: currentAlgorithm,
        viewHours: viewModeHours,
      }),
    enabled: !!currentFileId && !!currentDate,
  });

  return useMemo(() => ({
    timestamps: data?.timestamps ?? EMPTY_ARRAY,
    axisX: data?.axisX ?? EMPTY_ARRAY,
    axisY: data?.axisY ?? EMPTY_ARRAY,
    axisZ: data?.axisZ ?? EMPTY_ARRAY,
    vectorMagnitude: data?.vectorMagnitude ?? EMPTY_ARRAY,
    algorithmResults: data?.algorithmResults ?? null,
    nonwearResults: data?.nonwearResults ?? null,
    sensorNonwearPeriods: data?.sensorNonwearPeriods ?? EMPTY_SENSOR_NONWEAR,
    isLoading,
    preferredDisplayColumn,
    viewStart: data?.viewStart ?? null,
    viewEnd: data?.viewEnd ?? null,
  }), [data, isLoading, preferredDisplayColumn]);
}
