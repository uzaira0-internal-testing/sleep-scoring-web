import type { ProcessingProgress } from "@/services/local-processing";
import { FileText, Cpu, Database, CheckCircle } from "lucide-react";

const PHASE_ICONS = {
  reading: FileText,
  parsing: Cpu,
  epoching: Cpu,
  scoring: Cpu,
  nonwear: Cpu,
  storing: Database,
  complete: CheckCircle,
} as const;

const PHASE_LABELS = {
  reading: "Reading file",
  parsing: "Parsing CSV",
  epoching: "Converting to epochs",
  scoring: "Running sleep algorithms",
  nonwear: "Detecting nonwear",
  storing: "Saving to database",
  complete: "Complete",
} as const;

interface LocalProcessingProgressProps {
  progress: ProcessingProgress;
  isProcessing: boolean;
}

/**
 * Progress indicator for local file processing pipeline.
 * Follows the same pattern as upload-progress.tsx.
 */
export function LocalProcessingProgress({ progress, isProcessing }: LocalProcessingProgressProps) {
  if (!isProcessing && progress.phase !== "complete") return null;

  const Icon = PHASE_ICONS[progress.phase];
  const label = PHASE_LABELS[progress.phase];
  const isComplete = progress.phase === "complete";

  return (
    <div className="rounded-lg border p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <Icon className={`h-4 w-4 ${isComplete ? "text-green-500" : "text-blue-500"}`} />
        <span>{label}</span>
      </div>

      {!isComplete && (
        <div className="space-y-1">
          <div className="h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
            <div
              className="h-full rounded-full bg-blue-500 transition-all duration-300"
              style={{ width: `${Math.min(progress.percent, 100)}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {progress.message}
          </p>
        </div>
      )}

      {isComplete && (
        <p className="text-sm text-green-600 dark:text-green-400">
          File processed and stored locally.
        </p>
      )}
    </div>
  );
}
