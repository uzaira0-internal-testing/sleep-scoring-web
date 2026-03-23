import { useState, useRef, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Info, Loader2, Upload, Book, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { diaryApi } from "@/api/client";
import { parseDiaryCsv } from "@/services/diary-parser";
import { getLocalFiles, saveDiaryEntry, type FileRecord } from "@/db";
import { ActionResult } from "@/components/action-result";

// =============================================================================
// Server Diary Import
// =============================================================================

export function ServerDiaryImportSection(): JSX.Element {
  const queryClient = useQueryClient();
  const diaryFileRef = useRef<HTMLInputElement>(null);
  const [diaryResult, setDiaryResult] = useState<{ message: string; type: "success" | "error" } | null>(null);

  const diaryUploadMutation = useMutation({
    mutationFn: (file: File) => diaryApi.uploadDiaryCsv(file),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["diary"] });
      queryClient.invalidateQueries({ queryKey: ["dates-status"] });
      const msg = `Imported ${result.entries_imported} entries, skipped ${result.entries_skipped}`;
      const errMsg = result.errors?.length ? `. ${result.errors[0]}` : "";
      setDiaryResult({ message: msg + errMsg, type: result.entries_imported > 0 ? "success" : "error" });
    },
    onError: (error: Error) => {
      setDiaryResult({ message: error.message, type: "error" });
    },
  });

  const handleDiaryUpload = (e: React.ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0];
    if (!file) return;
    diaryUploadMutation.mutate(file);
    if (diaryFileRef.current) diaryFileRef.current.value = "";
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Book className="h-5 w-5" />
          Sleep Diary Import
        </CardTitle>
        <CardDescription>
          Upload a sleep diary CSV exported from REDCap or similar. Rows are automatically matched to activity files by the <strong>participant_id</strong> column.
          Existing entries for matching dates are updated (upsert).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <input
          ref={diaryFileRef}
          type="file"
          accept=".csv"
          onChange={handleDiaryUpload}
          className="hidden"
        />
        <Button
          variant="outline"
          onClick={() => diaryFileRef.current?.click()}
          disabled={diaryUploadMutation.isPending}
          className="gap-2"
        >
          {diaryUploadMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Upload className="h-4 w-4" />
          )}
          Upload Diary CSV
        </Button>

        {diaryResult && (
          <ActionResult message={diaryResult.message} type={diaryResult.type} onDismiss={() => setDiaryResult(null)} />
        )}

        <div className="rounded-lg border p-3 bg-muted/30 text-sm">
          <div className="flex items-start gap-2">
            <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
            <div className="space-y-1">
              <div><strong>Required:</strong> participant_id, startdate (or date)</div>
              <div><strong>Sleep:</strong> in_bed_time (or bedtime), sleep_offset_time (or wake_time), sleep_onset_time</div>
              <div><strong>Naps:</strong> napstart_1_time, napend_1_time, nap_onset_time_2, nap_offset_time_2, nap_onset_time_3, nap_offset_time_3</div>
              <div><strong>Nonwear:</strong> nonwear_start_time, nonwear_end_time, nonwear_reason (up to 3 periods)</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Local Diary Import
// =============================================================================

export function LocalDiaryImportSection(): JSX.Element {
  const [localFiles, setLocalFiles] = useState<FileRecord[]>([]);
  const [isImporting, setIsImporting] = useState(false);
  const [result, setResult] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    getLocalFiles().then(setLocalFiles).catch((err) => {
      console.error("Failed to load local files for diary import:", err);
    });
  }, []);

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsImporting(true);
    setResult(null);

    try {
      const text = await file.text();
      const parsed = parseDiaryCsv(text, localFiles);

      for (const { entries } of parsed.matched) {
        for (const entry of entries) {
          await saveDiaryEntry(entry.fileId, entry.analysisDate, entry);
        }
      }

      if (parsed.matchedRows > 0) {
        setResult({
          message: `Imported ${parsed.matchedRows} diary entries across ${parsed.matched.length} file(s).${parsed.unmatchedRows > 0 ? ` ${parsed.unmatchedRows} rows unmatched.` : ""}`,
          type: "success",
        });
      } else {
        setResult({
          message: `No rows matched local files.${parsed.errors.length > 0 ? ` ${parsed.errors[0]}` : ""}`,
          type: "error",
        });
      }
    } catch (err) {
      setResult({
        message: err instanceof Error ? err.message : "Import failed",
        type: "error",
      });
    } finally {
      setIsImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Book className="h-5 w-5" />
          Sleep Diary Import
        </CardTitle>
        <CardDescription>
          Import a sleep diary CSV. Rows are matched to local files by <strong>filename</strong> column.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <input
          ref={fileRef}
          type="file"
          accept=".csv"
          onChange={handleImport}
          className="hidden"
        />
        <Button
          variant="outline"
          onClick={() => fileRef.current?.click()}
          disabled={isImporting}
          className="gap-2"
        >
          {isImporting ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <FolderOpen className="h-4 w-4" />
          )}
          Import Diary CSV
        </Button>

        {result && (
          <ActionResult message={result.message} type={result.type} onDismiss={() => setResult(null)} />
        )}

        <div className="rounded-lg border p-3 bg-muted/30 text-sm">
          <div className="flex items-start gap-2">
            <Info className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
            <div className="space-y-1">
              <div><strong>Required:</strong> filename, date (or startdate)</div>
              <div><strong>Sleep:</strong> in_bed_time, sleep_offset_time, sleep_onset_time</div>
              <div><strong>Naps:</strong> napstart_1_time, napend_1_time (up to 3 naps)</div>
              <div><strong>Nonwear:</strong> nonwear_start_time, nonwear_end_time, nonwear_reason (up to 3)</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
