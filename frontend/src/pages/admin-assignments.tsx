import { useState, useMemo, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Users, Search, X, Plus, Trash2, AlertTriangle, Loader2, FileText, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { useConfirmDialog, ConfirmDialog } from "@/components/ui/confirm-dialog";
import { assignmentApi, filesApi } from "@/api/client";
import { assignmentProgressQueryOptions, unassignedFilesQueryOptions } from "@/api/query-options";
import { useSleepScoringStore } from "@/store";
import { cn } from "@/lib/utils";
import type { AssignmentProgress, UserFileProgress } from "@/api/types";

// =============================================================================
// Progress Bar
// =============================================================================

function ProgressBar({ scored, total, className }: { scored: number; total: number; className?: string }) {
  const pct = total > 0 ? Math.round((scored / total) * 100) : 0;
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex-1 h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            pct === 100 ? "bg-green-500" : pct > 0 ? "bg-primary" : "bg-muted",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground tabular-nums w-10 text-right">{pct}%</span>
    </div>
  );
}

// =============================================================================
// Duplicate username detection
// =============================================================================

function findDuplicateGroups(usernames: string[]): Map<string, string[]> {
  const groups = new Map<string, string[]>();
  const lower = usernames.map((u) => u.toLowerCase());
  for (let i = 0; i < usernames.length; i++) {
    const firstWord = lower[i].split(/\s+/)[0];
    for (let j = i + 1; j < usernames.length; j++) {
      const otherFirstWord = lower[j].split(/\s+/)[0];
      if (firstWord === otherFirstWord || lower[i].startsWith(lower[j]) || lower[j].startsWith(lower[i])) {
        const key = firstWord;
        const existing = groups.get(key) ?? [];
        if (!existing.includes(usernames[i])) existing.push(usernames[i]);
        if (!existing.includes(usernames[j])) existing.push(usernames[j]);
        groups.set(key, existing);
      }
    }
  }
  return groups;
}

// =============================================================================
// Study Progress Summary
// =============================================================================

function StudyProgressSummary({
  progress,
  totalFiles,
  unassignedCount,
}: {
  progress: AssignmentProgress[];
  totalFiles: number;
  unassignedCount: number;
}) {
  const totalUsers = progress.length;
  const assignedFiles = new Set(progress.flatMap((u) => u.files.map((f) => f.file_id))).size;
  const totalDates = progress.reduce((sum, u) => sum + u.total_dates, 0);
  const scoredDates = progress.reduce((sum, u) => sum + u.scored_dates, 0);

  const metrics = [
    { label: "Scorers", value: totalUsers },
    { label: "Assigned", value: `${assignedFiles} / ${totalFiles}` },
    { label: "Dates Scored", value: `${scoredDates} / ${totalDates}` },
    { label: "Unassigned", value: unassignedCount },
  ];

  return (
    <div className="grid grid-cols-4 gap-3">
      {metrics.map((m) => (
        <Card key={m.label} className="border-border/50">
          <CardContent className="py-3 px-4">
            <p className="text-xs text-muted-foreground uppercase tracking-wider">{m.label}</p>
            <p className="text-lg font-semibold tabular-nums">{m.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// =============================================================================
// User List Panel
// =============================================================================

function UserListPanel({
  progress,
  selectedUser,
  onSelect,
}: {
  progress: AssignmentProgress[];
  selectedUser: string | null;
  onSelect: (username: string) => void;
}) {
  const [filter, setFilter] = useState("");
  const duplicateGroups = useMemo(
    () => findDuplicateGroups(progress.map((u) => u.username)),
    [progress],
  );
  const isDuplicate = useCallback(
    (username: string) => {
      for (const group of duplicateGroups.values()) {
        if (group.includes(username)) return true;
      }
      return false;
    },
    [duplicateGroups],
  );

  const filtered = useMemo(
    () =>
      progress
        .filter((u) => u.username.toLowerCase().includes(filter.toLowerCase()))
        .sort((a, b) => a.username.localeCompare(b.username)),
    [progress, filter],
  );

  return (
    <div className="w-80 flex-none border-r border-border/60 flex flex-col">
      <div className="p-3 border-b border-border/60">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Filter users..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {filtered.map((user) => (
          <button
            key={user.username}
            onClick={() => onSelect(user.username)}
            className={cn(
              "w-full text-left px-3 py-2.5 border-b border-border/30 hover:bg-accent/50 transition-colors",
              selectedUser === user.username && "bg-accent border-l-2 border-l-primary",
            )}
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium truncate flex items-center gap-1.5">
                {user.username}
                {isDuplicate(user.username) && (
                  <AlertTriangle className="h-3 w-3 text-amber-500 flex-none" title="Possible duplicate username" />
                )}
              </span>
              <span className="text-xs text-muted-foreground flex-none">{user.total_files} files</span>
            </div>
            <ProgressBar scored={user.scored_dates} total={user.total_dates} />
          </button>
        ))}
        {filtered.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">No users found</p>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// User Detail Panel
// =============================================================================

function UserDetailPanel({
  user,
  onAssign,
}: {
  user: AssignmentProgress;
  onAssign: () => void;
}) {
  const [fileFilter, setFileFilter] = useState("");
  const queryClient = useQueryClient();
  const confirm = useConfirmDialog();

  const removeFileMutation = useMutation({
    mutationFn: ({ fileId }: { fileId: number }) =>
      assignmentApi.deleteFileAssignment(fileId, user.username),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: assignmentProgressQueryOptions().queryKey }),
  });

  const removeAllMutation = useMutation({
    mutationFn: () => assignmentApi.deleteUserAssignments(user.username),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: assignmentProgressQueryOptions().queryKey }),
  });

  const handleRemoveAll = async () => {
    const ok = await confirm({
      title: "Remove All Assignments",
      description: `Remove all ${user.total_files} file assignments for "${user.username}"? This cannot be undone.`,
      confirmLabel: "Remove All",
      variant: "destructive",
    });
    if (ok) removeAllMutation.mutate();
  };

  const filtered = useMemo(
    () =>
      user.files
        .filter((f) => f.filename.toLowerCase().includes(fileFilter.toLowerCase()))
        .sort((a, b) => a.filename.localeCompare(b.filename)),
    [user.files, fileFilter],
  );

  return (
    <div className="flex-1 flex flex-col min-w-0">
      {/* Header */}
      <div className="p-4 border-b border-border/60">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold">{user.username}</h2>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={onAssign}>
              <Plus className="h-3.5 w-3.5 mr-1" />
              Assign Files
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="text-destructive hover:text-destructive"
              onClick={handleRemoveAll}
              disabled={removeAllMutation.isPending}
            >
              <Trash2 className="h-3.5 w-3.5 mr-1" />
              Remove All
            </Button>
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm text-muted-foreground">
          <span>{user.total_files} files</span>
          <span>{user.scored_dates} / {user.total_dates} dates scored</span>
        </div>
        <ProgressBar scored={user.scored_dates} total={user.total_dates} className="mt-2" />
      </div>

      {/* File filter */}
      <div className="px-4 py-2 border-b border-border/60">
        <div className="relative">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Filter files..."
            value={fileFilter}
            onChange={(e) => setFileFilter(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
        </div>
      </div>

      {/* File table */}
      <div className="flex-1 overflow-y-auto">
        {filtered.map((file) => {
          const pct = file.total_dates > 0 ? Math.round((file.scored_dates / file.total_dates) * 100) : 0;
          return (
            <div
              key={file.file_id}
              className="flex items-center gap-3 px-4 py-2 border-b border-border/20 hover:bg-muted/30 group"
            >
              {/* Status dot */}
              <div
                className={cn(
                  "h-2 w-2 rounded-full flex-none",
                  pct === 100 ? "bg-green-500" : pct > 0 ? "bg-amber-500" : "bg-red-400",
                )}
                title={pct === 100 ? "Complete" : pct > 0 ? "In progress" : "Not started"}
              />
              {/* Filename */}
              <span className="text-sm truncate flex-1 min-w-0" title={file.filename}>
                {file.filename}
              </span>
              {/* Progress */}
              <span className="text-xs text-muted-foreground tabular-nums flex-none w-20 text-right">
                {file.scored_dates}/{file.total_dates} dates
              </span>
              {/* Remove */}
              <button
                className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:text-destructive flex-none"
                onClick={() => removeFileMutation.mutate({ fileId: file.file_id })}
                disabled={removeFileMutation.isPending}
                title="Remove assignment"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          );
        })}
        {filtered.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-8">No files match filter</p>
        )}
      </div>

      <ConfirmDialog />
    </div>
  );
}

// =============================================================================
// Assign Files Dialog
// =============================================================================

function AssignFilesDialog({
  open,
  onOpenChange,
  targetUsername,
  allFiles,
  existingFileIds,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  targetUsername: string;
  allFiles: { id: number; filename: string }[];
  existingFileIds: Set<number>;
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState("");
  const [newUsername, setNewUsername] = useState(targetUsername);
  const queryClient = useQueryClient();

  const assignMutation = useMutation({
    mutationFn: () =>
      assignmentApi.createAssignments(Array.from(selected), newUsername.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: assignmentProgressQueryOptions().queryKey });
      onOpenChange(false);
      setSelected(new Set());
      setFilter("");
    },
  });

  const filtered = useMemo(
    () =>
      allFiles
        .filter((f) => f.filename.toLowerCase().includes(filter.toLowerCase()))
        .sort((a, b) => a.filename.localeCompare(b.filename)),
    [allFiles, filter],
  );

  const availableFiltered = filtered.filter((f) => !existingFileIds.has(f.id));

  const toggleFile = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => {
    setSelected(new Set(availableFiltered.map((f) => f.id)));
  };

  const selectNone = () => setSelected(new Set());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Assign Files</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          {/* Username */}
          <div>
            <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              Assign to
            </label>
            <Input
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              placeholder="Username"
              className="mt-1"
            />
          </div>

          {/* File search */}
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
            <Input
              placeholder="Search files..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="pl-8"
            />
          </div>

          {/* Quick actions */}
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={selectAll} className="text-xs h-7">
              Select All ({availableFiltered.length})
            </Button>
            <Button variant="ghost" size="sm" onClick={selectNone} className="text-xs h-7">
              Clear
            </Button>
            <span className="text-xs text-muted-foreground ml-auto">
              {selected.size} selected
            </span>
          </div>

          {/* File list */}
          <div className="border rounded-md max-h-[350px] overflow-y-auto">
            {filtered.map((f) => {
              const alreadyAssigned = existingFileIds.has(f.id);
              return (
                <label
                  key={f.id}
                  className={cn(
                    "flex items-center gap-2 px-3 py-1.5 hover:bg-muted/50 cursor-pointer text-sm border-b border-border/20 last:border-b-0",
                    alreadyAssigned && "opacity-50 cursor-not-allowed",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selected.has(f.id)}
                    disabled={alreadyAssigned}
                    onChange={() => toggleFile(f.id)}
                    className="rounded border-input"
                  />
                  <span className="truncate">{f.filename}</span>
                  {alreadyAssigned && (
                    <CheckCircle2 className="h-3 w-3 text-green-500 flex-none ml-auto" title="Already assigned" />
                  )}
                </label>
              );
            })}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => assignMutation.mutate()}
            disabled={selected.size === 0 || !newUsername.trim() || assignMutation.isPending}
          >
            {assignMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin mr-1" />
            ) : null}
            Assign {selected.size} File{selected.size !== 1 ? "s" : ""}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// Main Page
// =============================================================================

export function AdminAssignmentsPage() {
  const isAdmin = useSleepScoringStore((state) => state.isAdmin);
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [assignDialogOpen, setAssignDialogOpen] = useState(false);

  const { data: progress, isLoading } = useQuery({
    ...assignmentProgressQueryOptions(),
    queryFn: () => assignmentApi.getAssignmentProgress(),
    enabled: isAdmin,
  });

  const { data: allFilesData } = useQuery({
    queryKey: ["all-files-admin"],
    queryFn: () => filesApi.listFiles(),
    enabled: isAdmin,
  });

  const { data: unassigned } = useQuery({
    ...unassignedFilesQueryOptions(),
    queryFn: () => assignmentApi.getUnassignedFiles(),
    enabled: isAdmin,
  });

  if (!isAdmin) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-muted-foreground">Admin access required</p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="h-full flex items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const progressData = progress ?? [];
  const selectedUserData = progressData.find((u) => u.username === selectedUser) ?? null;
  const allFiles = (allFilesData?.items ?? allFilesData ?? []) as { id: number; filename: string }[];
  const existingFileIds = selectedUserData
    ? new Set(selectedUserData.files.map((f) => f.file_id))
    : new Set<number>();

  return (
    <div className="h-full flex flex-col">
      {/* Summary */}
      <div className="p-4 border-b border-border/60">
        <div className="flex items-center gap-2 mb-3">
          <Users className="h-5 w-5 text-muted-foreground" />
          <h1 className="text-lg font-semibold">File Assignments</h1>
        </div>
        <StudyProgressSummary
          progress={progressData}
          totalFiles={allFiles.length}
          unassignedCount={unassigned?.length ?? 0}
        />
      </div>

      {/* Two-panel layout */}
      <div className="flex-1 flex min-h-0">
        <UserListPanel
          progress={progressData}
          selectedUser={selectedUser}
          onSelect={setSelectedUser}
        />

        {selectedUserData ? (
          <UserDetailPanel
            user={selectedUserData}
            onAssign={() => setAssignDialogOpen(true)}
          />
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground">
            <FileText className="h-12 w-12 mb-3 opacity-50" />
            <p className="text-sm">Select a user to view their assignments</p>
          </div>
        )}
      </div>

      {/* Assign dialog */}
      {selectedUser && (
        <AssignFilesDialog
          open={assignDialogOpen}
          onOpenChange={setAssignDialogOpen}
          targetUsername={selectedUser}
          allFiles={allFiles}
          existingFileIds={existingFileIds}
        />
      )}
    </div>
  );
}
