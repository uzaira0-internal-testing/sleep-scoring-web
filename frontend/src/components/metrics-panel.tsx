/**
 * Metrics Panel Component
 *
 * Displays Tudor-Locke sleep quality metrics for the selected sleep period.
 */

import { BarChart3 } from "lucide-react";
import type { SleepMetrics } from "@/api/types";
import { formatMinutes, formatPercent, formatNumber } from "@/utils/formatters";

interface MetricsPanelProps {
  metrics: SleepMetrics[];
  selectedPeriodIndex: number | null;
  compact?: boolean;
}

/** Thresholds for metric warnings */
function getMetricWarning(metric: string, value: number | null | undefined): boolean {
  if (value === null || value === undefined) return false;
  switch (metric) {
    case "tst": return value > 840 || value < 120; // TST > 14h or < 2h
    case "se": return value < 0.5; // SE < 50%
    case "waso": return value > 180; // WASO > 3h
    case "sol": return value > 120; // SOL > 2h
    default: return false;
  }
}

function MetricRow({
  label,
  value,
  tooltip,
  warning,
}: {
  label: string;
  value: string;
  tooltip?: string;
  warning?: boolean;
}) {
  return (
    <div className="flex justify-between items-center py-1" title={tooltip}>
      <span className="text-muted-foreground text-xs">{label}</span>
      <span className={`font-mono text-xs font-medium tabular-nums ${warning ? "text-amber-600 dark:text-amber-400" : ""}`}>{value}</span>
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="text-xs font-semibold text-muted-foreground/70 uppercase tracking-widest mt-3 mb-1 first:mt-0">
      {children}
    </h4>
  );
}

export function MetricsPanel({
  metrics,
  selectedPeriodIndex,
  compact = false,
}: MetricsPanelProps) {
  const selectedMetrics =
    selectedPeriodIndex !== null ? metrics[selectedPeriodIndex] : null;

  if (compact) {
    return (
      <div className="h-full flex flex-col">
        <div className="flex-none px-3 py-1.5 border-b border-border/40 flex items-center gap-1.5 text-xs font-medium">
          <BarChart3 className="h-3 w-3 text-primary" />
          Metrics
          {selectedPeriodIndex !== null && (
            <span className="text-muted-foreground font-normal">(P{selectedPeriodIndex + 1})</span>
          )}
        </div>
        <div className="flex-1 px-3 py-1.5 overflow-y-auto">
          {selectedMetrics ? (
            <div>
              <SectionHeader>Duration</SectionHeader>
              <MetricRow label="TST" value={formatMinutes(selectedMetrics.total_sleep_time_minutes)} tooltip="Total Sleep Time" warning={getMetricWarning("tst", selectedMetrics.total_sleep_time_minutes)} />
              <MetricRow label="TIB" value={formatMinutes(selectedMetrics.time_in_bed_minutes)} tooltip="Time in Bed" />
              <MetricRow label="WASO" value={formatMinutes(selectedMetrics.waso_minutes)} tooltip="Wake After Sleep Onset" warning={getMetricWarning("waso", selectedMetrics.waso_minutes)} />
              <MetricRow label="SOL" value={formatMinutes(selectedMetrics.sleep_onset_latency_minutes)} tooltip="Sleep Onset Latency" warning={getMetricWarning("sol", selectedMetrics.sleep_onset_latency_minutes)} />

              <SectionHeader>Quality</SectionHeader>
              <MetricRow label="SE" value={formatPercent(selectedMetrics.sleep_efficiency)} tooltip="Sleep Efficiency" warning={getMetricWarning("se", selectedMetrics.sleep_efficiency)} />
              <MetricRow label="MI" value={formatPercent(selectedMetrics.movement_index)} tooltip="Movement Index" />
              <MetricRow label="FI" value={formatPercent(selectedMetrics.fragmentation_index)} tooltip="Fragmentation Index" />

              <SectionHeader>Activity</SectionHeader>
              <MetricRow label="Awakenings" value={String(selectedMetrics.number_of_awakenings ?? "--")} />
              <MetricRow label="Avg Wake" value={formatMinutes(selectedMetrics.average_awakening_length_minutes)} tooltip="Avg awakening length" />
            </div>
          ) : (
            <p className="text-xs text-muted-foreground p-2">
              Select a sleep marker to view metrics
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-none px-3 py-2 border-b border-border/40">
        <h3 className="text-sm font-medium flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-primary" />
          Sleep Quality Metrics
          {selectedPeriodIndex !== null && (
            <span className="text-muted-foreground font-normal text-xs">
              (Period {selectedPeriodIndex + 1})
            </span>
          )}
        </h3>
      </div>
      <div className="flex-1 px-4 py-3 overflow-y-auto">
        {selectedMetrics ? (
          <div className="space-y-3">
            <div>
              <SectionHeader>Duration</SectionHeader>
              <MetricRow label="Time in Bed" value={formatMinutes(selectedMetrics.time_in_bed_minutes)} tooltip="Total time from onset to offset" />
              <MetricRow label="Total Sleep Time" value={formatMinutes(selectedMetrics.total_sleep_time_minutes)} tooltip="Sum of sleep epochs" warning={getMetricWarning("tst", selectedMetrics.total_sleep_time_minutes)} />
              <MetricRow label="Sleep Onset Latency" value={formatMinutes(selectedMetrics.sleep_onset_latency_minutes)} tooltip="Time from in-bed to first sleep" warning={getMetricWarning("sol", selectedMetrics.sleep_onset_latency_minutes)} />
              <MetricRow label="WASO" value={formatMinutes(selectedMetrics.waso_minutes)} tooltip="Wake After Sleep Onset" warning={getMetricWarning("waso", selectedMetrics.waso_minutes)} />
            </div>

            <div>
              <SectionHeader>Quality</SectionHeader>
              <MetricRow label="Sleep Efficiency" value={formatPercent(selectedMetrics.sleep_efficiency)} tooltip="(TST / TIB) x 100" warning={getMetricWarning("se", selectedMetrics.sleep_efficiency)} />
              <MetricRow label="Movement Index" value={formatPercent(selectedMetrics.movement_index)} tooltip="% epochs with movement" />
              <MetricRow label="Fragmentation Index" value={formatPercent(selectedMetrics.fragmentation_index)} tooltip="% 1-min sleep bouts" />
              <MetricRow label="Sleep Fragmentation" value={formatPercent(selectedMetrics.sleep_fragmentation_index)} tooltip="MI + FI" />
            </div>

            <div>
              <SectionHeader>Awakenings</SectionHeader>
              <MetricRow label="Count" value={String(selectedMetrics.number_of_awakenings ?? "--")} />
              <MetricRow label="Avg Length" value={formatMinutes(selectedMetrics.average_awakening_length_minutes)} tooltip="Average wake episode duration" />
            </div>

            <div>
              <SectionHeader>Activity</SectionHeader>
              <MetricRow label="Total Activity" value={formatNumber(selectedMetrics.total_activity, 0)} />
              <MetricRow label="Nonzero Epochs" value={String(selectedMetrics.nonzero_epochs ?? "--")} />
            </div>
          </div>
        ) : (
          <div className="h-full flex items-center justify-center">
            <p className="text-sm text-muted-foreground">Select a sleep marker</p>
          </div>
        )}
      </div>
    </div>
  );
}
