import React from "react";
import { ChevronLeft, ChevronRight, Filter } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSleepScoringStore } from "@/store";
import { fetchWithAuth, getApiBase } from "@/api/client";
import type { DateStatus } from "@/api/types";

interface DateNavigatorProps {
  dateStatusMap: Map<string, DateStatus>;
  consensusOnly: boolean;
  onConsensusOnlyChange?: (value: boolean) => void;
  isLocal: boolean;
  onComplexityBreakdown: (data: {
    complexity_pre: number | null;
    complexity_post: number | null;
    features: Record<string, unknown>;
  }) => void;
}

export const DateNavigator = React.memo(function DateNavigator({
  dateStatusMap,
  consensusOnly,
  onConsensusOnlyChange,
  isLocal,
  onComplexityBreakdown,
}: DateNavigatorProps) {
  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const currentDateIndex = useSleepScoringStore((state) => state.currentDateIndex);
  const availableDates = useSleepScoringStore((state) => state.availableDates);
  const navigateDate = useSleepScoringStore((state) => state.navigateDate);

  const currentDate = availableDates[currentDateIndex] ?? null;
  const canGoPrev = currentDateIndex > 0;
  const canGoNext = currentDateIndex < availableDates.length - 1;

  return (
    <div className="px-4 py-2 flex items-center justify-center gap-2">
      <Button
        variant="outline"
        size="icon"
        className="h-7 w-7 shrink-0"
        onClick={() => navigateDate(-1)}
        disabled={!canGoPrev || !currentFileId}
        data-testid="prev-date-btn"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <div className="relative min-w-[200px] w-[min(420px,45vw)]">
        <select
          className="w-full h-7 px-3 pr-8 rounded-md border border-input bg-background text-sm font-medium appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
          value={currentDateIndex}
          onChange={(e) => {
            const idx = parseInt(e.target.value, 10);
            if (idx !== currentDateIndex) {
              useSleepScoringStore.getState().setCurrentDateIndex(idx);
            }
          }}
          disabled={!currentFileId || availableDates.length === 0}
        >
          {availableDates.map((date, idx) => {
            const st = dateStatusMap.get(date);
            if (consensusOnly && !st?.needs_consensus && !st?.auto_flagged) return null;
            const autoFlagged = st?.auto_flagged;
            const manualFlagged = st?.needs_consensus;
            const flagPrefix = autoFlagged ? "\u26a0\ufe0f " : manualFlagged ? "\ud83d\udc65 " : "";
            const prefix = st?.is_no_sleep ? "\u26d4 " : st?.has_markers ? "\u2713 " : "\u25cb ";
            const weekday = new Date(date + "T12:00:00Z").toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
            return (
              <option key={date} value={idx}>
                {flagPrefix}{prefix}{date} {weekday} ({idx + 1}/{availableDates.length})
              </option>
            );
          })}
        </select>
        {currentDate && (() => {
          const st = dateStatusMap.get(currentDate);
          if (st?.auto_flagged) return <span className="absolute right-8 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-red-500" title="Scorers disagree" />;
          if (st?.needs_consensus) return <span className="absolute right-8 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-orange-500" title="Flagged for consensus" />;
          if (st?.is_no_sleep) return <span className="absolute right-8 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-amber-500" title="No sleep" />;
          if (st?.has_markers) return <span className="absolute right-8 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-green-500" title="Has markers" />;
          return <span className="absolute right-8 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-muted-foreground/30" title="No markers" />;
        })()}
        <ChevronRight className="absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none rotate-90" />
      </div>
      <Button
        variant="outline"
        size="icon"
        className="h-7 w-7 shrink-0"
        onClick={() => navigateDate(1)}
        disabled={!canGoNext || !currentFileId}
        data-testid="next-date-btn"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
      {!isLocal && onConsensusOnlyChange && (
        <Button
          variant={consensusOnly ? "default" : "outline"}
          size="icon"
          className="h-7 w-7 shrink-0"
          onClick={() => onConsensusOnlyChange(!consensusOnly)}
          title={consensusOnly ? "Showing flagged/disagreed dates only. Click to show all." : "Filter to flagged/disagreed dates only"}
        >
          <Filter className="h-3.5 w-3.5" />
        </Button>
      )}
      {currentDate && (() => {
        const st = dateStatusMap.get(currentDate);
        const complexity = st?.complexity_post ?? st?.complexity_pre;
        if (complexity == null) return null;
        if (complexity === -1) {
          return (
            <span className="text-xs font-medium px-1.5 py-0.5 rounded text-purple-600 dark:text-purple-400 bg-purple-500/10 tabular-nums cursor-help" title="Incomplete diary — need both onset and wake to score">
              &infin;
            </span>
          );
        }
        const color = complexity >= 70 ? "text-green-600 dark:text-green-400 bg-green-500/10" : complexity >= 40 ? "text-yellow-600 dark:text-yellow-400 bg-yellow-500/10" : "text-red-600 dark:text-red-400 bg-red-500/10";
        return (
          <button
            className={`text-xs font-medium px-1.5 py-0.5 rounded ${color} tabular-nums cursor-pointer hover:ring-1 hover:ring-current transition-shadow`}
            title={`Scoring difficulty: ${complexity}/100 (higher = easier)${isLocal ? "" : "\nClick for breakdown"}`}
            onClick={async () => {
              if (!currentFileId || !currentDate || isLocal) return;
              try {
                const data = await fetchWithAuth<{ complexity_pre: number | null; complexity_post: number | null; features: Record<string, unknown> }>(
                  `${getApiBase()}/files/${currentFileId}/${currentDate}/complexity`
                );
                onComplexityBreakdown(data);
              } catch {
                onComplexityBreakdown({ complexity_pre: complexity, complexity_post: null, features: { error: "Failed to load breakdown" } });
              }
            }}
          >
            {complexity}
          </button>
        );
      })()}
    </div>
  );
});
