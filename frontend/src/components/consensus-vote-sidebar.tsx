/* eslint-disable react-refresh/only-export-components */
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Check, Copy, Loader2, Vote } from "lucide-react";

import { consensusApi, getApiBase } from "@/api/client";
import type { ConsensusBallotCandidate } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAlertDialog } from "@/components/ui/confirm-dialog";
import { useDates, useSleepScoringStore } from "@/store";
import { formatTime } from "@/utils/formatters";

interface ConsensusVoteSidebarProps {
  highlightedCandidateId: number | null;
  onHighlightCandidate: (candidateId: number | null) => void;
  onCopyCandidate: (candidate: ConsensusBallotCandidate) => void;
  autoFlagged?: boolean;
}

export function buildConsensusWsUrl(params: {
  fileId: number;
  analysisDate: string;
  username: string;
  sitePassword: string | null;
}): string | null {
  if (typeof window === "undefined") return null;
  const apiBase = getApiBase();

  let apiUrl: URL;
  try {
    apiUrl = apiBase.startsWith("http://") || apiBase.startsWith("https://")
      ? new URL(apiBase)
      : new URL(apiBase, window.location.origin);
  } catch {
    return null;
  }

  const wsProtocol = apiUrl.protocol === "https:" ? "wss:" : "ws:";
  const wsPath = `${apiUrl.pathname.replace(/\/$/, "")}/consensus/stream`;
  const query = new URLSearchParams({
    file_id: String(params.fileId),
    analysis_date: params.analysisDate,
    username: params.username || "anonymous",
    ...(params.sitePassword ? { site_password: params.sitePassword } : {}),
  });

  return `${wsProtocol}//${apiUrl.host}${wsPath}?${query.toString()}`;
}

function markerSummary(markers: ConsensusBallotCandidate["sleep_markers_json"]): string {
  const list = (markers ?? []).filter((m) => m.onset_timestamp != null && m.offset_timestamp != null);
  if (list.length === 0) return "No sleep markers";

  const sorted = [...list].sort((a, b) => (a.marker_index ?? 9999) - (b.marker_index ?? 9999));
  return sorted.map((m) => {
    const label = (m.marker_type === "NAP" ? "Nap" : "Main");
    return `${label}: ${formatTime(m.onset_timestamp!)}-${formatTime(m.offset_timestamp!)}`;
  }).join(" | ");
}

export function ConsensusVoteSidebar({
  highlightedCandidateId,
  onHighlightCandidate,
  onCopyCandidate,
  autoFlagged,
}: ConsensusVoteSidebarProps) {
  const queryClient = useQueryClient();
  const { alert, alertDialog } = useAlertDialog();
  const currentFileId = useSleepScoringStore((state) => state.currentFileId);
  const username = useSleepScoringStore((state) => state.username);
  const sitePassword = useSleepScoringStore((state) => state.sitePassword);
  const { currentDate } = useDates();
  const [wsConnected, setWsConnected] = useState(false);

  const ballotKey = useMemo(
    () => ["consensus-ballot", currentFileId, currentDate, username || "anonymous"] as const,
    [currentDate, currentFileId, username],
  );

  const { data, isLoading } = useQuery({
    queryKey: ballotKey,
    queryFn: () => consensusApi.getBallot(currentFileId!, currentDate!),
    enabled: !!currentFileId && !!currentDate,
    staleTime: 0,
    refetchInterval: wsConnected ? 15000 : 2000,
  });

  useEffect(() => {
    if (!currentFileId || !currentDate) return;

    const wsUrl = buildConsensusWsUrl({
      fileId: currentFileId,
      analysisDate: currentDate,
      username: username || "anonymous",
      sitePassword: sitePassword ?? null,
    });
    if (!wsUrl) return;

    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let shouldReconnect = true;

    const connect = () => {
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onmessage = (evt) => {
        try {
          const payload = JSON.parse(evt.data as string) as {
            type?: string;
            file_id?: number;
            analysis_date?: string;
          };
          if (
            payload.type === "consensus_update"
            && payload.file_id === currentFileId
            && payload.analysis_date === currentDate
          ) {
            queryClient.invalidateQueries({ queryKey: ballotKey });
          }
        } catch {
          // Ignore malformed events and rely on polling fallback.
        }
      };

      ws.onclose = (evt) => {
        setWsConnected(false);
        if (!shouldReconnect) return;
        if (evt.code === 1008 || evt.code === 4401) return;
        reconnectTimer = setTimeout(connect, 1500);
      };

      ws.onerror = () => {
        setWsConnected(false);
      };
    };

    connect();

    return () => {
      shouldReconnect = false;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws && ws.readyState <= WebSocket.OPEN) {
        ws.close(1000, "component_dispose");
      }
    };
  }, [ballotKey, currentDate, currentFileId, queryClient, sitePassword, username]);

  const voteMutation = useMutation({
    mutationFn: (candidateId: number | null) => consensusApi.castVote(currentFileId!, currentDate!, candidateId),
    onSuccess: (updatedBallot) => {
      queryClient.setQueryData(ballotKey, updatedBallot);
      queryClient.invalidateQueries({ queryKey: ballotKey });
    },
    onError: (error: Error) => {
      alert({ title: "Vote Failed", description: error.message });
    },
  });

  const candidates = data?.candidates ?? [];

  const leaderLabel = useMemo(() => {
    if (!data?.leading_candidate_id) return null;
    return data.candidates.find((c) => c.candidate_id === data.leading_candidate_id)?.label ?? null;
  }, [data]);

  const myVoteLabel = useMemo(() => {
    if (!data?.my_vote_candidate_id) return null;
    return data.candidates.find((c) => c.candidate_id === data.my_vote_candidate_id)?.label ?? null;
  }, [data]);

  if (!currentFileId || !currentDate) return null;

  return (
    <Card className={`h-full flex flex-col overflow-hidden ${autoFlagged ? "border-red-500/60 border-2" : ""}`}>
      <CardHeader className={`py-2 px-3 border-b ${autoFlagged ? "bg-red-500/10" : ""}`}>
        <CardTitle className="text-sm flex items-center gap-1.5">
          <Vote className={`h-4 w-4 ${autoFlagged ? "text-red-500" : ""}`} />
          Consensus Vote
          {autoFlagged && <span className="text-[10px] font-normal text-red-500 ml-1">Scorers disagree</span>}
          <span
            className={`ml-1 inline-block h-2 w-2 rounded-full ${wsConnected ? "bg-emerald-500" : "bg-amber-500"}`}
            title={wsConnected ? "Live updates connected" : "Live updates reconnecting (polling fallback active)"}
          />
        </CardTitle>
      </CardHeader>
      <CardContent className="p-2 flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="h-full flex items-center justify-center text-muted-foreground text-xs">
            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
            Loading
          </div>
        ) : candidates.length === 0 ? (
          <div className="text-xs text-muted-foreground">
            No candidate sets yet. Candidate sets appear after scorers save markers.
          </div>
        ) : (
          <div className="space-y-2">
            <div className="text-[11px] text-muted-foreground">
              {data?.total_votes ?? 0} total votes
              {leaderLabel ? ` | leader: ${leaderLabel}` : ""}
              {myVoteLabel ? ` | your vote: ${myVoteLabel}` : ""}
            </div>
            {candidates.map((candidate) => {
              const isHighlighted = highlightedCandidateId === candidate.candidate_id;
              const hasMyVote = candidate.selected_by_me;
              const canVote = !voteMutation.isPending;

              return (
                <div
                  key={candidate.candidate_id}
                  className={`rounded border p-2 cursor-pointer transition-colors ${
                    isHighlighted
                      ? "border-primary bg-primary/5"
                      : hasMyVote
                        ? "border-emerald-500/50 bg-emerald-500/5"
                        : "border-border hover:bg-muted/30"
                  }`}
                  onClick={() => onHighlightCandidate(isHighlighted ? null : candidate.candidate_id)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-medium flex items-center gap-1">
                      {candidate.source_type === "auto" && <Bot className="h-3 w-3 text-emerald-600" />}
                      {candidate.label}
                      {hasMyVote && <Check className="h-3 w-3 text-emerald-600" />}
                    </div>
                    <div className="text-[11px] text-muted-foreground tabular-nums">
                      {candidate.vote_count} vote{candidate.vote_count === 1 ? "" : "s"}
                    </div>
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1">
                    {candidate.is_no_sleep
                      ? `No-sleep candidate${(candidate.sleep_markers_json?.length ?? 0) > 0 ? ` (${candidate.sleep_markers_json!.length} nap${candidate.sleep_markers_json!.length === 1 ? "" : "s"})` : ""}`
                      : markerSummary(candidate.sleep_markers_json)}
                  </div>
                  <div className="mt-2 flex items-center gap-1">
                    <Button
                      variant={hasMyVote ? "default" : "outline"}
                      size="sm"
                      className="h-7 text-[11px] px-2"
                      disabled={!canVote}
                      onClick={(e) => {
                        e.stopPropagation();
                        voteMutation.mutate(hasMyVote ? null : candidate.candidate_id);
                      }}
                    >
                      {voteMutation.isPending ? (
                        <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                      ) : hasMyVote ? (
                        <Check className="h-3 w-3 mr-1" />
                      ) : null}
                      {hasMyVote ? "Unvote" : "Vote"}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-[11px] px-2"
                      onClick={(e) => {
                        e.stopPropagation();
                        onCopyCandidate(candidate);
                      }}
                    >
                      <Copy className="h-3 w-3 mr-1" />
                      Copy
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
      {alertDialog}
    </Card>
  );
}
