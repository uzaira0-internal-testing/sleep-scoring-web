/**
 * Upload progress component for TUS resumable uploads.
 * Shows compression → upload → processing phases with progress bar.
 */
import { Loader2, Pause, Play, X, Check, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { TusProgress } from "@/hooks/useTusUpload";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatEta(seconds: number): string {
  if (seconds <= 0 || !isFinite(seconds)) return "";
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  if (seconds < 3600) return `${Math.ceil(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.ceil((seconds % 3600) / 60)}m`;
}

function phaseLabel(phase: string | null): string {
  if (!phase) return "Processing...";
  switch (phase) {
    case "decompressing":
      return "Decompressing...";
    case "reading_csv":
      return "Reading CSV...";
    case "converting_counts":
      return "Converting raw data to counts...";
    case "inserting_db":
      return "Saving to database...";
    default:
      return phase;
  }
}

interface UploadProgressProps {
  progress: TusProgress;
  onPause?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  onDismiss?: () => void;
  isPaused?: boolean;
}

export function UploadProgress({
  progress,
  onPause,
  onResume,
  onCancel,
  onDismiss,
  isPaused = false,
}: UploadProgressProps) {
  if (progress.phase === "idle") return null;

  const isDone = progress.phase === "done";
  const isError = progress.phase === "error";
  const isActive = !isDone && !isError;

  // Calculate overall progress across phases
  let overallPercent = 0;
  if (progress.phase === "compressing") {
    overallPercent = progress.percent * 0.1; // 0-10%
  } else if (progress.phase === "uploading") {
    overallPercent = 10 + progress.percent * 0.5; // 10-60%
  } else if (progress.phase === "processing") {
    overallPercent = 60 + progress.processingPercent * 0.4; // 60-100%
  } else if (isDone) {
    overallPercent = 100;
  }

  return (
    <div className={`rounded-lg border p-3 text-sm ${
      isError ? "border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950" :
      isDone ? "border-green-300 bg-green-50 dark:border-green-800 dark:bg-green-950" :
      "border-blue-300 bg-blue-50 dark:border-blue-800 dark:bg-blue-950"
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          {isActive && <Loader2 className="h-4 w-4 animate-spin text-blue-500" />}
          {isDone && <Check className="h-4 w-4 text-green-500" />}
          {isError && <AlertTriangle className="h-4 w-4 text-red-500" />}
          <span className="font-medium truncate max-w-[250px]">
            {progress.fileName}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {progress.phase === "uploading" && onPause && onResume && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={isPaused ? onResume : onPause}
            >
              {isPaused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
            </Button>
          )}
          {isActive && onCancel && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={onCancel}
            >
              <X className="h-3 w-3" />
            </Button>
          )}
          {(isDone || isError) && onDismiss && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={onDismiss}
            >
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>
      </div>

      {/* Progress bar */}
      {isActive && (
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5 mb-1">
          <div
            className="bg-blue-500 h-1.5 rounded-full transition-all duration-300"
            style={{ width: `${Math.min(overallPercent, 100)}%` }}
          />
        </div>
      )}

      {/* Phase details */}
      <div className="text-xs text-muted-foreground">
        {progress.phase === "compressing" && "Compressing file..."}
        {progress.phase === "uploading" && (
          <span>
            Uploading: {formatBytes(progress.bytesUploaded)} / {formatBytes(progress.bytesTotal)}
            {progress.speed > 0 && ` · ${formatBytes(progress.speed)}/s`}
            {progress.eta > 0 && ` · ${formatEta(progress.eta)} remaining`}
          </span>
        )}
        {progress.phase === "processing" && (
          <span>
            {phaseLabel(progress.processingPhase)}
            {progress.processingPercent > 0 && ` ${progress.processingPercent.toFixed(0)}%`}
          </span>
        )}
        {isDone && "Upload and processing complete"}
        {isError && (progress.error || "Upload failed")}
      </div>
    </div>
  );
}
