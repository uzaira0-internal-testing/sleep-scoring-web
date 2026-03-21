/**
 * Analysis page showing cross-file summary statistics and scoring progress.
 */

import { useState, useEffect, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Loader2, BarChart3, Clock, Moon, Activity, TrendingUp, FileText, BookOpen, AlertTriangle, Users } from "lucide-react";
import { useSleepScoringStore } from "@/store";
import { fetchWithAuth, getApiBase } from "@/api/client";
import { useAppCapabilities } from "@/hooks/useAppCapabilities";
import { computeLocalAnalysis, type LocalAnalysisSummary } from "@/services/local-analysis";

type AnalysisSummaryResponse = LocalAnalysisSummary & {
  files_summary: (LocalAnalysisSummary["files_summary"][number] & { consensus_remaining?: number; auto_flagged_count?: number })[];
};

function MetricCard({ label, value, unit, icon: Icon }: { label: string; value: number | null; unit: string; icon: React.ElementType }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <div className="text-2xl font-bold">
              {value !== null ? value.toFixed(1) : "—"}
              {value !== null && <span className="text-sm font-normal text-muted-foreground ml-1">{unit}</span>}
            </div>
            <div className="text-xs text-muted-foreground">{label}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ProgressBar({ scored, total }: { scored: number; total: number }) {
  const pct = total > 0 ? Math.round((scored / total) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-10 text-right">{pct}%</span>
    </div>
  );
}

export function AnalysisPage() {
  const isAuthenticated = useSleepScoringStore((state) => state.isAuthenticated);
  const username = useSleepScoringStore((state) => state.username);
  const setCurrentFile = useSleepScoringStore((state) => state.setCurrentFile);
  const navigate = useNavigate();
  const caps = useAppCapabilities();

  // Server analysis (when server available)
  const { data: serverData, isLoading: isLoadingServer } = useQuery({
    queryKey: ["analysis-summary", username || "anonymous"],
    queryFn: () => fetchWithAuth<AnalysisSummaryResponse>(`${getApiBase()}/analysis/summary`),
    enabled: isAuthenticated && caps.server,
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    refetchInterval: 30000,
  });

  // Local analysis (always computed)
  const [localData, setLocalData] = useState<LocalAnalysisSummary | null>(null);
  const [isLoadingLocal, setIsLoadingLocal] = useState(true);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await computeLocalAnalysis(username || "anonymous");
        if (!cancelled) setLocalData(data);
      } catch (err) {
        console.error("Failed to compute local analysis:", err);
        if (!cancelled) setLocalData(null);
      } finally {
        if (!cancelled) setIsLoadingLocal(false);
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [username]);

  // Merge server + local data with weighted means
  const data: AnalysisSummaryResponse | null = useMemo(() => {
    if (caps.server && serverData && localData) {
      const sm = serverData.aggregate_metrics;
      const lm = localData.aggregate_metrics;
      const sn = sm.total_sleep_periods + sm.total_nap_periods;
      const ln = lm.total_sleep_periods + lm.total_nap_periods;
      const weightedMean = (sv: number | null, lv: number | null) => {
        if (sv == null && lv == null) return null;
        if (sv == null) return lv;
        if (lv == null) return sv;
        const total = sn + ln;
        return total > 0 ? (sv * sn + lv * ln) / total : null;
      };
      return {
        total_files: serverData.total_files + localData.total_files,
        total_dates: serverData.total_dates + localData.total_dates,
        scored_dates: serverData.scored_dates + localData.scored_dates,
        files_summary: [
          ...serverData.files_summary,
          ...localData.files_summary.map((f) => ({ ...f, file_id: -f.file_id })),
        ],
        aggregate_metrics: {
          mean_tst_minutes: weightedMean(sm.mean_tst_minutes, lm.mean_tst_minutes),
          mean_sleep_efficiency: weightedMean(sm.mean_sleep_efficiency, lm.mean_sleep_efficiency),
          mean_waso_minutes: weightedMean(sm.mean_waso_minutes, lm.mean_waso_minutes),
          mean_sleep_onset_latency: weightedMean(sm.mean_sleep_onset_latency, lm.mean_sleep_onset_latency),
          total_sleep_periods: sm.total_sleep_periods + lm.total_sleep_periods,
          total_nap_periods: sm.total_nap_periods + lm.total_nap_periods,
        },
      };
    }
    if (caps.server && serverData) return serverData;
    if (localData) return localData as AnalysisSummaryResponse;
    return null;
  }, [caps.server, serverData, localData]);

  // In server mode, don't block on local analysis — it merges in when ready
  const isLoading = caps.server ? isLoadingServer : isLoadingLocal;

  if (isLoading) {
    return (
      <div className="p-6 max-w-6xl mx-auto flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const metrics = data?.aggregate_metrics;
  const overallPct = data && data.total_dates > 0
    ? Math.round((data.scored_dates / data.total_dates) * 100)
    : 0;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold">Analysis</h1>
        <p className="text-muted-foreground">
          Cross-file summary statistics and scoring progress
        </p>
      </div>

      {/* Overall Progress */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Scoring Progress
          </CardTitle>
          <CardDescription>
            {data?.scored_dates ?? 0} of {data?.total_dates ?? 0} dates scored across {data?.total_files ?? 0} files ({overallPct}%)
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ProgressBar scored={data?.scored_dates ?? 0} total={data?.total_dates ?? 0} />
        </CardContent>
      </Card>

      {/* Aggregate Metrics */}
      <div>
        <h2 className="text-lg font-semibold mb-3">Aggregate Metrics</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            label="Mean Total Sleep Time"
            value={metrics?.mean_tst_minutes ?? null}
            unit="min"
            icon={Moon}
          />
          <MetricCard
            label="Mean Sleep Efficiency"
            value={metrics?.mean_sleep_efficiency ?? null}
            unit="%"
            icon={TrendingUp}
          />
          <MetricCard
            label="Mean WASO"
            value={metrics?.mean_waso_minutes ?? null}
            unit="min"
            icon={Activity}
          />
          <MetricCard
            label="Mean Sleep Onset Latency"
            value={metrics?.mean_sleep_onset_latency ?? null}
            unit="min"
            icon={Clock}
          />
        </div>
        <div className="grid grid-cols-2 gap-4 mt-4 max-w-md">
          <Card>
            <CardContent className="pt-4 text-center">
              <div className="text-2xl font-bold">{metrics?.total_sleep_periods ?? 0}</div>
              <div className="text-xs text-muted-foreground">Total sleep periods</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4 text-center">
              <div className="text-2xl font-bold">{metrics?.total_nap_periods ?? 0}</div>
              <div className="text-xs text-muted-foreground">Total nap periods</div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* File Summary Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            File Summary
          </CardTitle>
        </CardHeader>
        <CardContent>
          {data?.files_summary && data.files_summary.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left">
                    <th className="py-2 pr-4 font-medium">Filename</th>
                    <th className="py-2 pr-4 font-medium">Participant</th>
                    <th className="py-2 pr-4 font-medium text-center">Dates Scored</th>
                    <th className="py-2 pr-4 font-medium">Progress</th>
                    <th className="py-2 pr-4 font-medium text-center" title="Manually flagged for consensus">Flagged</th>
                    <th className="py-2 pr-4 font-medium text-center" title="Auto-detected: 2+ human scorers disagree">Disagree</th>
                    <th className="py-2 pr-4 font-medium text-center">Diary</th>
                  </tr>
                </thead>
                <tbody>
                  {data.files_summary.map((file) => (
                    <tr
                      key={file.file_id}
                      className="border-b last:border-0 cursor-pointer hover:bg-muted/50 transition-colors"
                      onClick={() => {
                        setCurrentFile(file.file_id, file.filename);
                        navigate("/scoring");
                      }}
                    >
                      <td className="py-2.5 pr-4 font-mono text-xs text-primary underline-offset-2 hover:underline">{file.filename}</td>
                      <td className="py-2.5 pr-4">{file.participant_id || "—"}</td>
                      <td className={`py-2.5 pr-4 text-center font-medium ${
                        file.total_dates === 0 ? "text-muted-foreground"
                        : file.scored_dates === 0 ? "text-red-500"
                        : file.scored_dates >= file.total_dates ? "text-green-500"
                        : "text-orange-500"
                      }`}>
                        {file.scored_dates} / {file.total_dates}
                      </td>
                      <td className="py-2.5 pr-4 min-w-[120px]">
                        <ProgressBar scored={file.scored_dates} total={file.total_dates} />
                      </td>
                      <td className="py-2.5 pr-4 text-center">
                        {file.consensus_remaining > 0 ? (
                          <span className="inline-flex items-center gap-1 text-orange-500 text-xs font-medium">
                            <Users className="h-3.5 w-3.5" />
                            {file.consensus_remaining}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4 text-center">
                        {file.auto_flagged_count > 0 ? (
                          <span className="inline-flex items-center gap-1 text-red-500 text-xs font-medium">
                            <AlertTriangle className="h-3.5 w-3.5" />
                            {file.auto_flagged_count}
                          </span>
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-4 text-center">
                        {file.has_diary ? (
                          <BookOpen className="h-4 w-4 text-green-500 inline" />
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              No files available. {caps.server ? "Upload" : "Import"} files on the Data Settings page to see analysis.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
