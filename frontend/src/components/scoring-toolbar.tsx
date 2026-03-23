import React from "react";
import { Moon, Watch, Ban, Users, Wand2, Loader2, Trash2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { useSleepScoringStore, useMarkers } from "@/store";
import { MARKER_TYPES, PERIOD_GUIDER_OPTIONS, type PeriodGuiderType } from "@/api/types";
import { MarkerTimeEditor } from "@/components/marker-time-editor";
import type { UseMutationResult } from "@tanstack/react-query";
import type { AutoScoreResult, AutoNonwearResult } from "@/services/data-source";

interface ScoringToolbarProps {
  autoScoreMutation: UseMutationResult<AutoScoreResult, Error, void, unknown>;
  autoNonwearMutation: UseMutationResult<AutoNonwearResult, Error, void, unknown>;
  autoScoreRef: React.MutableRefObject<boolean>;
  diaryBlocksAutoScore: boolean;
  studySettingsLoading: boolean;
  showComparisonMarkers: boolean;
  onShowComparisonMarkersChange: (value: boolean) => void;
  confirm: (opts: { title: string; description: string; variant?: string; confirmLabel?: string }) => Promise<boolean>;
}

export const ScoringToolbar = React.memo(function ScoringToolbar({
  autoScoreMutation,
  autoNonwearMutation,
  autoScoreRef,
  diaryBlocksAutoScore,
  studySettingsLoading,
  showComparisonMarkers,
  onShowComparisonMarkersChange,
  confirm,
}: ScoringToolbarProps) {
  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const currentDateIndex = useSleepScoringStore((state) => state.currentDateIndex);
  const availableDates = useSleepScoringStore((state) => state.availableDates);
  const autoScoreOnNavigate = useSleepScoringStore((state) => state.autoScoreOnNavigate);
  const setAutoScoreOnNavigate = useSleepScoringStore((state) => state.setAutoScoreOnNavigate);
  const autoNonwearOnNavigate = useSleepScoringStore((state) => state.autoNonwearOnNavigate);
  const periodGuider = useSleepScoringStore((state) => state.periodGuider);
  const setPeriodGuider = useSleepScoringStore((state) => state.setPeriodGuider);
  const showAdjacentMarkers = useSleepScoringStore((state) => state.showAdjacentMarkers);
  const setShowAdjacentMarkers = useSleepScoringStore((state) => state.setShowAdjacentMarkers);
  const showNonwearOverlays = useSleepScoringStore((state) => state.showNonwearOverlays);
  const setShowNonwearOverlays = useSleepScoringStore((state) => state.setShowNonwearOverlays);

  const currentDate = availableDates[currentDateIndex] ?? null;

  const {
    markerMode,
    creationMode,
    isNoSleep,
    needsConsensus,
    notes,
    setMarkerMode,
    cancelMarkerCreation,
    setNeedsConsensus,
    setNotes,
  } = useMarkers();

  return (
    <div className="px-4 py-1.5 border-t border-border/40 flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
      {/* Group A: Mode -- Sleep, Nonwear, No Sleep */}
      <div className="flex items-center gap-1 shrink-0">
        <Button
          variant={markerMode === "sleep" ? "default" : "outline"}
          size="sm"
          className="h-7 text-xs px-2.5"
          onClick={() => setMarkerMode("sleep")}
          title={isNoSleep ? "Place nap markers (no main sleep)" : undefined}
        >
          <Moon className="h-3.5 w-3.5 mr-1" />
          {isNoSleep ? "Nap" : "Sleep"}
        </Button>
        <Button
          variant={markerMode === "nonwear" ? "default" : "outline"}
          size="sm"
          className="h-7 text-xs px-2.5"
          onClick={() => setMarkerMode("nonwear")}
        >
          <Watch className="h-3.5 w-3.5 mr-1" />
          Nonwear
        </Button>
        <Button
          variant={isNoSleep ? "default" : "outline"}
          size="sm"
          className={`h-7 text-xs px-2.5 ${isNoSleep ? "bg-amber-600 hover:bg-amber-700" : ""}`}
          onClick={async () => {
            const state = useSleepScoringStore.getState();
            if (!state.isNoSleep) {
              const hasMainSleep = state.sleepMarkers.some(m => m.markerType === MARKER_TYPES.MAIN_SLEEP);
              if (hasMainSleep) {
                const ok = await confirm({ title: "No Sleep", description: "Marking as 'No Sleep' will clear main sleep markers. Nap markers will be preserved. Continue?", variant: "destructive", confirmLabel: "Clear & Mark" });
                if (!ok) return;
              }
              useSleepScoringStore.getState().setIsNoSleep(true);
            } else {
              state.setIsNoSleep(false);
            }
          }}
          title={isNoSleep ? "Click to allow main sleep markers" : "Mark this date as having no main sleep"}
        >
          <Ban className="h-3.5 w-3.5 mr-1" />
          No Sleep
        </Button>
      </div>

      <div className="h-5 w-px bg-border/40 shrink-0" />

      {/* Group B: Consensus + Notes */}
      <div className="flex items-center gap-2 shrink-0">
        <Button
          variant={needsConsensus ? "default" : "outline"}
          size="sm"
          className={`h-7 text-xs px-2.5 ${needsConsensus ? "bg-orange-600 hover:bg-orange-700" : ""}`}
          onClick={() => setNeedsConsensus(!needsConsensus)}
          title={needsConsensus ? "Remove consensus flag" : "Flag for consensus review"}
          disabled={!currentFileId || !currentDate}
        >
          <Users className="h-3.5 w-3.5 mr-1" />
          Consensus
        </Button>
        <input
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notes..."
          disabled={!currentFileId || !currentDate}
          className="h-7 text-xs px-2 rounded-md border border-border bg-background w-[140px] placeholder:text-muted-foreground/50 focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
          title="Annotation notes (auto-saved)"
        />
      </div>

      <div className="h-5 w-px bg-border/40 shrink-0" />

      {/* Group C: Auto Sleep (guider + button + checkbox together) */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Select
          value={periodGuider}
          onChange={(e) => setPeriodGuider(e.target.value as PeriodGuiderType)}
          className="h-7 text-xs w-[100px]"
          title="Sleep period search method"
          options={PERIOD_GUIDER_OPTIONS}
        />
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs px-2.5"
          onClick={() => { autoScoreRef.current = false; autoScoreMutation.mutate(); }}
          disabled={!currentFileId || !currentDate || autoScoreMutation.isPending || isNoSleep || diaryBlocksAutoScore || studySettingsLoading}
          title={studySettingsLoading ? "Loading study settings..." : diaryBlocksAutoScore ? "Cannot auto-score: no diary data for this date" : "Automatically detect and suggest sleep marker placements"}
        >
          {studySettingsLoading || autoScoreMutation.isPending ? (
            <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
          ) : (
            <Wand2 className="h-3.5 w-3.5 mr-1" />
          )}
          {studySettingsLoading ? "Loading settings..." : "Auto Sleep"}
        </Button>
        <div className="flex items-center gap-1">
          <Checkbox
            checked={autoScoreOnNavigate}
            onCheckedChange={(checked) => setAutoScoreOnNavigate(!!checked)}
          />
          <Label className="text-[11px] cursor-pointer" onClick={() => setAutoScoreOnNavigate(!autoScoreOnNavigate)}>
            Auto
          </Label>
        </div>
      </div>

      {/* Group D: Auto Nonwear (button + checkbox together) */}
      <div className="flex items-center gap-1.5 shrink-0">
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs px-2.5"
          onClick={() => { autoNonwearMutation.mutate(); }}
          disabled={!currentFileId || !currentDate || autoNonwearMutation.isPending}
          title="Automatically detect nonwear periods from diary + Choi/sensor signals"
        >
          {autoNonwearMutation.isPending ? (
            <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" />
          ) : (
            <Wand2 className="h-3.5 w-3.5 mr-1" />
          )}
          Auto Nonwear
        </Button>
        <div className="flex items-center gap-1">
          <Checkbox
            checked={autoNonwearOnNavigate}
            onCheckedChange={(checked) => useSleepScoringStore.getState().setAutoNonwearOnNavigate(!!checked)}
          />
          <Label className="text-[11px] cursor-pointer" onClick={() => useSleepScoringStore.getState().setAutoNonwearOnNavigate(!autoNonwearOnNavigate)}>
            Auto
          </Label>
        </div>
      </div>

      <div className="h-5 w-px bg-border/40 shrink-0" />

      {/* Group E: Display options (all checkboxes together) */}
      <div className="flex items-center gap-3 shrink-0">
        <div className="flex items-center gap-1">
          <Checkbox
            checked={showAdjacentMarkers}
            onCheckedChange={(checked) => setShowAdjacentMarkers(!!checked)}
          />
          <Label className="text-[11px] cursor-pointer" onClick={() => setShowAdjacentMarkers(!showAdjacentMarkers)}>
            Adjacent
          </Label>
        </div>
        <div className="flex items-center gap-1">
          <Checkbox
            checked={showComparisonMarkers}
            onCheckedChange={(checked) => onShowComparisonMarkersChange(!!checked)}
          />
          <Label className="text-[11px] cursor-pointer" onClick={() => onShowComparisonMarkersChange(!showComparisonMarkers)}>
            Compare
          </Label>
        </div>
        <div className="flex items-center gap-1">
          <Checkbox
            checked={showNonwearOverlays}
            onCheckedChange={(checked) => setShowNonwearOverlays(!!checked)}
          />
          <Label className="text-[11px] cursor-pointer" onClick={() => setShowNonwearOverlays(!showNonwearOverlays)}>
            NW Overlays
          </Label>
        </div>
      </div>

      {/* Group F: Marker edit -- Onset, Offset, Duration (always horizontal) */}
      <MarkerTimeEditor />

      <div className="h-5 w-px bg-border/40 shrink-0" />

      {/* Group G: Clear */}
      <Button
        variant="outline"
        size="sm"
        className="h-7 text-xs text-destructive border-destructive/50 hover:bg-destructive/10 shrink-0"
        onClick={async () => {
          const ok = await confirm({ title: "Clear Markers", description: "Clear all markers for this date?", variant: "destructive", confirmLabel: "Clear All" });
          if (ok) {
            useSleepScoringStore.getState().clearAllMarkers();
          }
        }}
      >
        <Trash2 className="h-3.5 w-3.5 mr-1" />
        Clear
      </Button>

      {/* Creation mode indicator */}
      {creationMode !== "idle" && (
        <Button
          variant="outline"
          size="sm"
          className="h-7 text-[11px] px-2.5 shrink-0 border-amber-400/40 text-amber-700 bg-amber-50 hover:bg-amber-100 dark:border-amber-500/40 dark:text-amber-300 dark:bg-amber-500/10"
          title={`Click plot to set ${creationMode === "placing_onset" ? "offset" : "onset"}. Click to cancel.`}
          onClick={cancelMarkerCreation}
        >
          <X className="h-3 w-3 mr-1" />
          {creationMode === "placing_onset" ? "Set Offset" : "Set Onset"}
        </Button>
      )}
    </div>
  );
});
