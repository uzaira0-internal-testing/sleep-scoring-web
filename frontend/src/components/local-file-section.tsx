import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { FileText, Trash2, Loader2, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ConfirmFn } from "@/components/ui/confirm-dialog";
import { useLocalFile } from "@/hooks/useLocalFile";
import { LocalProcessingProgress } from "@/components/local-processing-progress";
import { deleteFileRecord } from "@/db";
import { localFilesQueryOptions } from "@/api/query-options";

interface LocalFileSectionProps {
  isServerMode: boolean;
  confirm: ConfirmFn;
  alert: (opts: { title: string; description: string }) => Promise<void>;
}

export function LocalFileSection({ isServerMode, confirm, alert }: LocalFileSectionProps) {
  const queryClient = useQueryClient();
  const { openLocalFiles, openLocalFolder, isProcessing, progress: localProgress } = useLocalFile();
  const { data: localFiles = [] } = useQuery({
    ...localFilesQueryOptions(),
    refetchInterval: isProcessing ? 1000 : false,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FolderOpen className="h-5 w-5" />
          {isServerMode ? "Local / Browser Processing" : "Activity Data Files"}
        </CardTitle>
        <CardDescription>
          {isServerMode
            ? "Process files locally in your browser using WASM. Data stays on your machine and is stored in IndexedDB — nothing is uploaded to the server."
            : "Open CSV files from your computer. Files are processed locally using WASM and stored in your browser."}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="outline"
            onClick={openLocalFiles}
            disabled={isProcessing}
            className="gap-2"
          >
            {isProcessing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FolderOpen className="h-4 w-4" />
            )}
            Open Files
          </Button>
          <Button
            variant="outline"
            onClick={openLocalFolder}
            disabled={isProcessing}
            className="gap-2"
          >
            <FolderOpen className="h-4 w-4" />
            Open Folder
          </Button>
        </div>

        {localProgress && <LocalProcessingProgress progress={localProgress} isProcessing={isProcessing} />}

        {localFiles.length > 0 && (
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground uppercase tracking-wide">
              Local files ({localFiles.length})
            </p>
            <div className="border rounded-md divide-y max-h-48 overflow-y-auto">
              {localFiles.map((f) => (
                <div key={f.id} className="flex items-center justify-between px-3 py-2 text-sm">
                  <div className="flex items-center gap-2 min-w-0">
                    <FileText className="h-3.5 w-3.5 text-muted-foreground flex-shrink-0" />
                    <span className="truncate">{f.filename}</span>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                      local
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                    <span className="text-xs text-muted-foreground">{f.availableDates.length} dates</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={async () => {
                        const ok = await confirm({ title: "Delete File", description: `Delete ${f.filename}?`, variant: "destructive", confirmLabel: "Delete" });
                        if (ok && f.id) {
                          try {
                            await deleteFileRecord(f.id);
                            queryClient.invalidateQueries({ queryKey: localFilesQueryOptions().queryKey });
                          } catch (err) {
                            console.error("Failed to delete file:", err);
                            await alert({ title: "Delete Failed", description: `Could not delete ${f.filename}. Please try again.` });
                          }
                        }
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
