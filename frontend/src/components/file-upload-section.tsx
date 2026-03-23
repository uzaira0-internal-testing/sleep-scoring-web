import { useState, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { FileText, Trash2, Loader2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAlertDialog, type ConfirmFn } from "@/components/ui/confirm-dialog";
import { useSleepScoringStore } from "@/store";
import { filesApi } from "@/api/client";
import type { FileInfo } from "@/api/types";
import { useTusUpload, TUS_SIZE_THRESHOLD } from "@/hooks/useTusUpload";
import { UploadProgress } from "@/components/upload-progress";
import { filesQueryOptions } from "@/api/query-options";
import { ActionResult } from "@/components/action-result";

interface FileUploadSectionProps {
  files: FileInfo[];
  confirm: ConfirmFn;
}

export function FileUploadSection({ files, confirm }: FileUploadSectionProps) {
  const queryClient = useQueryClient();
  const { alert } = useAlertDialog();

  const activityFileRef = useRef<HTMLInputElement>(null);
  const activityFolderRef = useRef<HTMLInputElement>(null);
  const [replaceOnUpload, setReplaceOnUpload] = useState(true);

  const uploadProgress = useSleepScoringStore((state) => state.uploadProgress);
  const isUploading = useSleepScoringStore((state) => state.isUploading);
  const uploadResult = useSleepScoringStore((state) => state.uploadResult);

  const { progress: tusProgress, upload: tusUpload, cancel: tusCancel, pause: tusPause, resume: tusResume, reset: tusReset } = useTusUpload();
  const [isPaused, setIsPaused] = useState(false);
  const isTusActive = tusProgress.phase !== "idle";

  const deleteFileMutation = useMutation({
    mutationFn: filesApi.deleteFile,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: filesQueryOptions().queryKey });
    },
    onError: (error: Error) => {
      alert({ title: "Delete Failed", description: error.message });
    },
  });

  const handleActivityUpload = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;
    const csvFiles = Array.from(fileList).filter((f) => f.name.toLowerCase().endsWith(".csv") || f.name.toLowerCase().endsWith(".xlsx"));
    if (csvFiles.length === 0) {
      useSleepScoringStore.getState().setUploadResult({ message: "No CSV/XLSX files found", type: "error" });
      return;
    }
    if (activityFileRef.current) activityFileRef.current.value = "";
    if (activityFolderRef.current) activityFolderRef.current.value = "";

    // Snapshot replace flag at submit time to avoid stale closure if user toggles mid-upload
    const replace = replaceOnUpload;
    const hasLargeFile = csvFiles.some((f) => f.size > TUS_SIZE_THRESHOLD);
    if (hasLargeFile && csvFiles.length === 1) {
      tusReset();
      tusUpload(csvFiles, replace);
      return;
    }

    const store = useSleepScoringStore.getState();
    store.setIsUploading(true);
    store.setUploadResult(null);

    (async () => {
      let uploaded = 0;
      let failed = 0;
      const failedNames: string[] = [];
      let lastError = "";

      const largeFiles = csvFiles.filter((f) => f.size > TUS_SIZE_THRESHOLD);
      const smallFiles = csvFiles.filter((f) => f.size <= TUS_SIZE_THRESHOLD);

      for (const file of smallFiles) {
        useSleepScoringStore.getState().setUploadProgress(
          `Uploading ${uploaded + failed + 1}/${csvFiles.length}: ${file.name}`
        );
        try {
          await filesApi.uploadFile(file, replace);
          uploaded++;
        } catch (err) {
          failed++;
          failedNames.push(file.name);
          if (err instanceof Error) lastError = err.message;
        }
      }

      for (const file of largeFiles) {
        useSleepScoringStore.getState().setUploadProgress(
          `Uploading (resumable) ${uploaded + failed + 1}/${csvFiles.length}: ${file.name}`
        );
        try {
          await tusUpload([file], replace);
          uploaded++;
        } catch (err) {
          failed++;
          failedNames.push(file.name);
          if (err instanceof Error) lastError = err.message;
        }
      }

      useSleepScoringStore.getState().setUploadProgress(null);
      useSleepScoringStore.getState().setIsUploading(false);
      let message = `Uploaded ${uploaded} file${uploaded !== 1 ? "s" : ""}`;
      if (failed > 0) {
        message += `, ${failed} failed`;
        if (failedNames.length <= 3) message += ` (${failedNames.join(", ")})`;
        if (lastError) message += `: ${lastError}`;
      }
      const result = {
        message,
        type: (failed > 0 ? "error" : "success") as "success" | "error",
      };
      useSleepScoringStore.getState().setUploadResult(result);
      queryClient.invalidateQueries({ queryKey: filesQueryOptions().queryKey });
      queryClient.invalidateQueries({ queryKey: ["dates-status"] });
    })();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Upload className="h-5 w-5" />
          Upload to Server
        </CardTitle>
        <CardDescription>
          Upload epoch CSV files with activity counts. Re-uploading a file with the same name replaces the existing data.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <input
          ref={activityFileRef}
          type="file"
          accept=".csv,.xlsx,.xls"
          multiple
          onChange={handleActivityUpload}
          className="hidden"
        />
        <input
          ref={activityFolderRef}
          type="file"
          {...{ webkitdirectory: "" } as React.InputHTMLAttributes<HTMLInputElement>}
          onChange={handleActivityUpload}
          className="hidden"
        />
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="outline"
            onClick={() => activityFileRef.current?.click()}
            disabled={!!uploadProgress}
            className="gap-2"
          >
            {uploadProgress && uploadProgress.includes("Uploading") ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Upload className="h-4 w-4" />
            )}
            Upload Files
          </Button>
          <Button
            variant="outline"
            onClick={() => activityFolderRef.current?.click()}
            disabled={!!uploadProgress}
            className="gap-2"
          >
            <FileText className="h-4 w-4" />
            Upload Folder
          </Button>
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={replaceOnUpload}
              onChange={(e) => setReplaceOnUpload(e.target.checked)}
              className="rounded"
            />
            Replace existing
          </label>
        </div>

        {isTusActive && (
          <UploadProgress
            progress={tusProgress}
            onPause={() => { tusPause(); setIsPaused(true); }}
            onResume={() => { tusResume(); setIsPaused(false); }}
            onCancel={() => { tusCancel(); setIsPaused(false); }}
            onDismiss={tusReset}
            isPaused={isPaused}
          />
        )}

        {uploadProgress && !isTusActive && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin flex-shrink-0" />
            {uploadProgress}
          </div>
        )}

        {uploadResult && !isUploading && (
          <ActionResult message={uploadResult.message} type={uploadResult.type} onDismiss={() => useSleepScoringStore.getState().setUploadResult(null)} />
        )}

        {files.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">
              Server files ({files.length})
            </p>
            <div className="border rounded-md divide-y max-h-48 overflow-y-auto">
              {files.map((f) => (
                <div key={f.id} className="flex items-center justify-between px-3 py-2 text-sm">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                    <span className="truncate">{f.filename}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      f.status === "ready" ? "bg-success/10 text-success" :
                      f.status === "failed" ? "bg-destructive/10 text-destructive" :
                      f.status === "uploading" || f.status === "processing" ? "bg-primary/10 text-primary" :
                      "bg-muted text-muted-foreground"
                    }`}>
                      {f.status}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                    {f.row_count && (
                      <span className="text-xs text-muted-foreground">{f.row_count.toLocaleString()} rows</span>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={async () => {
                        const ok = await confirm({ title: "Delete File", description: `Delete ${f.filename}?`, variant: "destructive", confirmLabel: "Delete" });
                        if (ok) deleteFileMutation.mutate(f.id);
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
