/**
 * Upload progress component for TUS resumable uploads.
 * Shows compression → upload → processing phases with progress bar.
 */
import { Loader2, Pause, Play, X, Check, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { TusProgress } from "@/hooks/useTusUpload";
import { formatBytes } from "@/lib/format";

function formatEta(seconds: number): string {
  if (seconds <= 0 || !isFinite(seconds)) return "";
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  if (seconds < 3600) return `${Math.ceil(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.ceil((seconds % 3600) / 60)}m`;
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
    overallPercent = progress.percent * 0.05; // 0-5%
  } else if (progress.phase === "uploading") {
    overallPercent = 5 + progress.percent * 0.95; // 5-100%
  } else if (isDone) {
    overallPercent = 100;
  }

  return (
    <div className={`rounded-lg border p-3 text-sm ${
      isError ? "border-destructive/40 bg-destructive/10 text-foreground" :
      isDone ? "border-success/40 bg-success/10 text-foreground" :
      "border-primary/40 bg-primary/10 text-foreground"
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          {isActive && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
          {isDone && <Check className="h-4 w-4 text-success" />}
          {isError && <AlertTriangle className="h-4 w-4 text-destructive" />}
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
        <div className="w-full bg-muted rounded-full h-1.5 mb-1">
          <div
            className="bg-primary h-1.5 rounded-full transition-all duration-300"
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
        {isDone && "Upload complete"}
        {isError && (progress.error || "Upload failed")}
      </div>
    </div>
  );
}
