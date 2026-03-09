/**
 * Consensus Panel Component
 *
 * Shows when 2+ user annotations exist for the current file/date.
 * Displays side-by-side comparison and admin resolution actions.
 */

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAlertDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Users, CheckCircle, AlertTriangle, Loader2, Shield, Bot } from "lucide-react";
import { useSleepScoringStore } from "@/store";
import { fetchWithAuth, getApiBase } from "@/api/client";

/** Display name for the auto-score pseudo-user. */
function displayUsername(username: string): string {
  return username === "auto_score" ? "Auto-Score" : username;
}

// =============================================================================
// Types
// =============================================================================

interface AnnotationSummary {
  username: string;
  sleep_markers_json: Record<string, unknown>[] | null;
  nonwear_markers_json: Record<string, unknown>[] | null;
  is_no_sleep: boolean;
  algorithm_used: string | null;
  status: string;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
}

interface ResolvedAnnotation {
  resolved_by: string;
  resolved_at: string | null;
  resolution_notes: string | null;
  final_sleep_markers_json: Record<string, unknown>[] | null;
  final_nonwear_markers_json: Record<string, unknown>[] | null;
}

interface ConsensusDateResponse {
  file_id: number;
  analysis_date: string;
  annotations: AnnotationSummary[];
  has_resolution: boolean;
  resolution: ResolvedAnnotation | null;
}

// =============================================================================
// Component
// =============================================================================

interface ConsensusPanelProps {
  compact?: boolean;
}

export function ConsensusPanel({ compact = false }: ConsensusPanelProps) {
  const queryClient = useQueryClient();
  const { alert, alertDialog } = useAlertDialog();
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [selectedUser, setSelectedUser] = useState<string | null>(null);

  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const currentDateIndex = useSleepScoringStore((state) => state.currentDateIndex);
  const availableDates = useSleepScoringStore((state) => state.availableDates);
  const currentDate = availableDates[currentDateIndex] ?? null;

  // Fetch consensus data
  const { data: consensus, isLoading } = useQuery({
    queryKey: ["consensus", currentFileId, currentDate],
    queryFn: () =>
      fetchWithAuth<ConsensusDateResponse>(
        `${getApiBase()}/consensus/${currentFileId}/${currentDate}`
      ),
    enabled: !!currentFileId && !!currentDate,
  });

  // Resolve mutation
  const resolveMutation = useMutation({
    mutationFn: async (data: {
      final_sleep_markers_json: Record<string, unknown>[];
      final_nonwear_markers_json: Record<string, unknown>[];
      resolution_notes: string | null;
    }) =>
      fetchWithAuth<ResolvedAnnotation>(
        `${getApiBase()}/consensus/${currentFileId}/${currentDate}/resolve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["consensus", currentFileId, currentDate],
      });
      queryClient.invalidateQueries({
        queryKey: ["markers", currentFileId, currentDate],
      });
      queryClient.invalidateQueries({
        queryKey: ["dates-status", currentFileId],
      });
      setSelectedUser(null);
      setResolutionNotes("");
    },
    onError: (error: Error) => {
      alert({ title: "Resolution Failed", description: error.message });
    },
  });

  const handleAcceptAnnotation = useCallback(
    (annotation: AnnotationSummary) => {
      resolveMutation.mutate({
        final_sleep_markers_json: annotation.sleep_markers_json ?? [],
        final_nonwear_markers_json: annotation.nonwear_markers_json ?? [],
        resolution_notes: resolutionNotes || `Accepted ${annotation.username}'s annotation`,
      });
    },
    [resolveMutation, resolutionNotes]
  );

  // Don't render if no consensus data or fewer than 2 annotations
  if (!currentFileId || !currentDate) return null;
  if (isLoading) return null;
  if (!consensus || consensus.annotations.length < 2) return null;

  const submittedAnnotations = consensus.annotations.filter(
    (a) => a.status === "submitted"
  );
  if (submittedAnnotations.length < 2) return null;

  return (
    <Card className={compact ? "h-full flex flex-col w-56 flex-none" : ""}>
      <CardHeader className={compact ? "py-2 px-3 flex-none" : ""}>
        <CardTitle className={compact ? "text-sm" : "text-base"}>
          <div className="flex items-center gap-2">
            <Users className="h-4 w-4" />
            Consensus
            {consensus.has_resolution ? (
              <CheckCircle className="h-3.5 w-3.5 text-green-500" />
            ) : (
              <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
            )}
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className={compact ? "p-2 flex-1 overflow-y-auto" : ""}>
        {/* Status */}
        <div className="text-xs text-muted-foreground mb-2">
          {submittedAnnotations.length} annotations
          {consensus.has_resolution && " (resolved)"}
        </div>

        {/* Annotation cards */}
        <div className="space-y-2">
          {submittedAnnotations.map((annotation) => (
            <div
              key={annotation.username}
              className={`border rounded-md p-3 text-sm ${
                selectedUser === annotation.username
                  ? "border-primary bg-primary/5"
                  : "border-border"
              }`}
              onClick={() => setSelectedUser(annotation.username)}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium flex items-center gap-1">
                  {annotation.username === "auto_score" && (
                    <Bot className="h-3 w-3 text-blue-500" />
                  )}
                  {displayUsername(annotation.username)}
                </span>
                <span className="text-xs text-muted-foreground">
                  {annotation.algorithm_used ?? "manual"}
                </span>
              </div>

              {annotation.is_no_sleep ? (
                <span className="text-muted-foreground italic">No sleep</span>
              ) : (
                <div className="space-y-0.5">
                  <div>
                    Sleep markers: {annotation.sleep_markers_json?.length ?? 0}
                  </div>
                  <div>
                    Nonwear markers:{" "}
                    {annotation.nonwear_markers_json?.length ?? 0}
                  </div>
                </div>
              )}

              {annotation.notes && (
                <p className="text-xs text-muted-foreground italic mt-1 truncate">
                  {annotation.notes}
                </p>
              )}

              {/* Accept button */}
              {!consensus.has_resolution && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs w-full mt-2 gap-1.5"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleAcceptAnnotation(annotation);
                  }}
                  disabled={resolveMutation.isPending}
                >
                  {resolveMutation.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Shield className="h-3 w-3" />
                  )}
                  Accept
                </Button>
              )}
            </div>
          ))}
        </div>

        {/* Resolution notes */}
        {!consensus.has_resolution && (
          <div className="mt-2">
            <Input
              className="h-9 text-sm"
              placeholder="Resolution notes (optional)"
              value={resolutionNotes}
              onChange={(e) => setResolutionNotes(e.target.value)}
            />
          </div>
        )}

        {/* Existing resolution */}
        {consensus.has_resolution && consensus.resolution && (
          <div className="mt-2 border-t pt-2">
            <div className="text-xs text-muted-foreground uppercase tracking-wide mb-1">
              Resolution
            </div>
            <div className="text-xs">
              <span className="text-muted-foreground">By:</span>{" "}
              <span className="font-medium">{consensus.resolution.resolved_by}</span>
            </div>
            {consensus.resolution.resolution_notes && (
              <p className="text-xs text-muted-foreground italic mt-0.5">
                {consensus.resolution.resolution_notes}
              </p>
            )}
          </div>
        )}
      </CardContent>
      {alertDialog}
    </Card>
  );
}
