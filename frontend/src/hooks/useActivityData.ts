import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSleepScoringStore } from "@/store";
import { useDataSource } from "@/contexts/data-source-context";
import { activityDataQueryOptions } from "@/api/query-options";
import type { ActivityData } from "@/services/data-source";

/** Empty sentinel to avoid re-creating empty arrays on every render. */
const EMPTY_ARRAY: number[] = [];
const EMPTY_SENSOR_NONWEAR: ActivityData["sensorNonwearPeriods"] = [];

/**
 * Hook that fetches and exposes activity data via React Query.
 *
 * This is the single source of truth for activity data -- no copy in Zustand.
 * Uses shared activityDataQueryOptions so the cache key is defined in one place.
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

  const currentFileId = useSleepScoringStore((s) => s.currentFileId);
  const currentDate = useSleepScoringStore((s) => s.availableDates[s.currentDateIndex] ?? null);
  const viewModeHours = useSleepScoringStore((s) => s.viewModeHours);
  const currentAlgorithm = useSleepScoringStore((s) => s.currentAlgorithm);
  const preferredDisplayColumn = useSleepScoringStore((s) => s.preferredDisplayColumn);

  const { data, isLoading } = useQuery(
    activityDataQueryOptions(dataSource, currentFileId, currentDate, viewModeHours, currentAlgorithm, isLocal ? "local" : "server"),
  );

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
