import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Activity, Loader2, Lock, User, Wifi, WifiOff, Plus, Trash2, Globe, HardDrive, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { authApi, meApi } from "@/api/client";
import { useSleepScoringStore } from "@/store";
import { isTauri, switchTauriWorkspace } from "@/lib/tauri";
import { useCapabilitiesStore } from "@/store/capabilities-store";
import {
  useWorkspaceStore,
  setActiveWorkspaceId,
  type WorkspaceEntry,
} from "@/store/workspace-store";
import { switchDb } from "@/lib/workspace-db";
import { switchApi } from "@/lib/workspace-api";
import { queryClient } from "@/query-client";
import { migrateFromLegacy } from "@/lib/workspace-migration";
import { LoginFormSchema, type LoginFormValues } from "@/lib/schemas";

type LoginPhase = "loading" | "mode-picker" | "workspace-picker" | "login-form";
type LoginMode = "server" | "local";

function LoginShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4 relative overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-1/2 -right-1/4 w-[800px] h-[800px] rounded-full bg-primary/[0.03] blur-3xl" />
        <div className="absolute -bottom-1/3 -left-1/4 w-[600px] h-[600px] rounded-full bg-sleep/[0.04] blur-3xl" />
      </div>
      <div className="relative z-10 w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="inline-flex h-14 w-14 rounded-2xl bg-primary/10 items-center justify-center mb-4">
            <Activity className="h-7 w-7 text-primary" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Sleep Scoring</h1>
          <p className="text-sm text-muted-foreground mt-1">Research actigraphy analysis platform</p>
        </div>
        {children}
      </div>
    </div>
  );
}

/**
 * Login page with workspace picker + credentials form.
 */
export function LoginPage() {
  const navigate = useNavigate();
  const setAuth = useSleepScoringStore((state) => state.setAuth);
  const setServerAvailable = useCapabilitiesStore((s) => s.setServerAvailable);
  const resetProbeCache = useCapabilitiesStore((s) => s.resetProbeCache);
  const { workspaces, createWorkspace, deleteWorkspace, updateLastAccessed } =
    useWorkspaceStore();

  const [phase, setPhase] = useState<LoginPhase>("loading");
  const [loginMode, setLoginMode] = useState<LoginMode>("local");
  const [authRequired, setAuthRequired] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedWorkspace, setSelectedWorkspace] = useState<WorkspaceEntry | null>(null);

  // Form validation via react-hook-form + Zod
  const { register, handleSubmit: rhfHandleSubmit, formState: { errors: formErrors } } = useForm<LoginFormValues>({
    resolver: zodResolver(LoginFormSchema),
    defaultValues: { password: "", username: "" },
  });

  // New workspace form state
  const [newServerUrl, setNewServerUrl] = useState("");
  const [newDisplayName, setNewDisplayName] = useState("");
  const [isCreatingNew, setIsCreatingNew] = useState(false);
  const [wantsServer, setWantsServer] = useState(false);

  // Run legacy migration on first load
  useEffect(() => {
    migrateFromLegacy();
  }, []);

  // Decide initial phase — wait for Zustand persist hydration, then auto-detect.
  // The workspace store uses `persist` middleware which hydrates async from localStorage.
  // On first render `workspaces` may still be [] even if workspaces exist. We wait for
  // the `onFinishHydration` callback before deciding which phase to show.
  useEffect(() => {
    let cancelled = false;
    let unsubHydration: (() => void) | null = null;

    function decide(hydratedWorkspaces: WorkspaceEntry[]): void {
      if (cancelled) return;

      // Browser mode (not Tauri): the backend is co-hosted at the same origin.
      // Skip workspace picker entirely — go straight to credentials.
      if (!isTauri()) {
        authApi.getAuthStatus(undefined)
          .then((status) => {
            if (cancelled) return;
            setLoginMode("server");
            setAuthRequired(status.password_required);
            // wantsServer=false: no URL field needed (server is co-hosted)
            setWantsServer(false);
            setNewServerUrl("");

            // Reuse existing co-hosted workspace (serverUrl === "") or create one
            const cohosted = hydratedWorkspaces.find((w) => w.serverUrl === "");
            if (cohosted) {
              setSelectedWorkspace(cohosted);
              setIsCreatingNew(false);
            } else {
              setIsCreatingNew(true);
              setNewDisplayName("Server");
            }
            setPhase("login-form");
          })
          .catch(() => {
            if (cancelled) return;
            // No co-hosted backend — unexpected for browser deployments.
            // Log a warning so it's not a completely silent fallback.
            console.warn("Co-hosted backend probe failed — falling back to workspace/mode picker");
            if (hydratedWorkspaces.length > 0) {
              setPhase("workspace-picker");
            } else {
              setPhase("mode-picker");
            }
          });
        return;
      }

      // Tauri mode: show workspace picker if workspaces exist, otherwise mode-picker.
      // Don't probe relative URLs — Tauri's asset server returns 200 HTML for all
      // paths (SPA fallback), which would false-positive as a reachable backend.
      if (hydratedWorkspaces.length > 0) {
        setPhase("workspace-picker");
      } else {
        setPhase("mode-picker");
      }
    }

    // Check if persist has already hydrated (e.g. StrictMode second render)
    if (useWorkspaceStore.persist.hasHydrated()) {
      decide(useWorkspaceStore.getState().workspaces);
    } else {
      // Wait for hydration to finish
      unsubHydration = useWorkspaceStore.persist.onFinishHydration(() => {
        decide(useWorkspaceStore.getState().workspaces);
      });
    }

    return () => {
      cancelled = true;
      unsubHydration?.();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // wantsServer = user intent (from mode picker), loginMode = probe result (server reachable?)
  // Returns { ok, passwordRequired } so callers don't need to re-read batched React state.
  async function probeUrl(serverUrl: string, showError = false): Promise<{ ok: boolean; passwordRequired: boolean }> {
    try {
      const status = await authApi.getAuthStatus(serverUrl || undefined);
      setLoginMode("server");
      setAuthRequired(status.password_required);
      setError(null);
      return { ok: true, passwordRequired: status.password_required };
    } catch (err) {
      setLoginMode("local");
      if (showError && serverUrl) {
        const message = err instanceof TypeError
          ? `Cannot reach "${serverUrl}" — check the URL for typos`
          : `Could not connect to "${serverUrl}"`;
        setError(message);
      }
      return { ok: false, passwordRequired: false };
    }
  }

  function handleSelectWorkspace(ws: WorkspaceEntry): void {
    setSelectedWorkspace(ws);
    setNewServerUrl(ws.serverUrl);
    setWantsServer(!!ws.serverUrl);
    setIsCreatingNew(false);
    setPhase("login-form");
    // Only probe if workspace has a server URL — local workspaces have no server to check.
    if (ws.serverUrl) {
      probeUrl(ws.serverUrl);
    }
  }

  function handleChooseMode(server: boolean): void {
    setSelectedWorkspace(null);
    setNewServerUrl("");
    setNewDisplayName(server ? "" : "Local Analysis");
    setLoginMode("local");
    setWantsServer(server);
    setIsCreatingNew(true);
    setError(null);
    setPhase("login-form");
  }

  function handleNewWorkspace(): void {
    setSelectedWorkspace(null);
    setNewServerUrl("");
    setNewDisplayName("");
    setLoginMode("local");
    setWantsServer(false);
    setIsCreatingNew(true);
    setPhase("mode-picker");
  }

  function handleBack(): void {
    setError(null);
    setLoginMode("local");
    setWantsServer(false);
    // From login-form: go to mode-picker (where the mode choice lives)
    // From mode-picker: go to workspace-picker (only shown if workspaces exist)
    if (phase === "login-form" && isCreatingNew) {
      setPhase("mode-picker");
    } else {
      setPhase("workspace-picker");
    }
  }

  async function handleServerUrlBlur(): Promise<void> {
    const url = newServerUrl.trim().replace(/\/+$/, "");
    setNewServerUrl(url);
    await probeUrl(url, wantsServer);
    // Auto-generate display name from URL if empty
    if (!newDisplayName && url) {
      try {
        const host = new URL(url).hostname;
        setNewDisplayName(host);
      } catch {
        setNewDisplayName(url);
      }
    }
  }

  async function activateWorkspace(ws: WorkspaceEntry, password: string, username: string, isServer: boolean): Promise<void> {
    setActiveWorkspaceId(ws.id);
    switchDb(ws.dbName);
    switchApi(ws.serverUrl);
    updateLastAccessed(ws.id);
    queryClient.clear();
    resetProbeCache();

    // Switch Tauri backend to workspace-scoped SQLite
    if (isTauri()) {
      await switchTauriWorkspace(ws.id);
    }

    // Set auth in the store (this also restores user prefs)
    setAuth(password, username);

    // Set capabilities based on probe result (passed explicitly to avoid stale React state)
    if (isServer) {
      setServerAvailable(true);
      try {
        const me = await meApi.getMe();
        useSleepScoringStore.getState().setIsAdmin(me.is_admin);
      } catch (err) {
        useSleepScoringStore.getState().setIsAdmin(false);
        console.warn("Failed to fetch admin status:", err instanceof Error ? err.message : err);
      }
    } else {
      setServerAvailable(false);
    }
  }

  const handleSubmit = async (formValues: LoginFormValues) => {
    setError(null);
    setIsLoading(true);

    const username = formValues.username?.trim() || "anonymous";
    const password = formValues.password || "";

    try {
      const serverUrl = isCreatingNew ? newServerUrl.trim().replace(/\/+$/, "") : (selectedWorkspace?.serverUrl ?? "");

      // Determine if this is a server workspace.
      // probeUrl sets React state (loginMode) but that's batched — can't read it synchronously.
      // So we track server reachability via probeUrl's return value + existing loginMode.
      let isServer = loginMode === "server";

      // If probe hasn't resolved yet (fire-and-forget from handleSelectWorkspace,
      // or Enter-without-blur for new workspace), run it now before submitting.
      if (serverUrl && !isServer) {
        const result = await probeUrl(serverUrl, wantsServer);
        if (result.ok) {
          isServer = true;
          // If server needs password but form doesn't have it, stop and show the field
          if (result.passwordRequired && !password) {
            setError("Server requires a password");
            return;
          }
        } else if (wantsServer) {
          // User explicitly chose server mode but probe failed — probeUrl already set error
          return;
        }
        // If !wantsServer and probe failed, proceed as local (existing behavior)
      }

      // Verify password if needed (authRequired reflects latest probe for the blur-then-submit path)
      if (isServer && authRequired) {
        if (!password) {
          setError("Server requires a password");
          return;
        }
        await authApi.verifyPassword(password, serverUrl || undefined);
      }

      // Create or reuse workspace
      let ws: WorkspaceEntry;
      if (isCreatingNew) {
        const displayName = newDisplayName.trim() || (serverUrl ? "Server" : "Local Analysis");
        ws = createWorkspace(serverUrl, displayName);
      } else {
        if (!selectedWorkspace) {
          setError("No workspace selected");
          return;
        }
        ws = selectedWorkspace;
      }

      await activateWorkspace(ws, isServer ? password : "", username, isServer);
      navigate("/scoring");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setIsLoading(false);
    }
  };

  // --- Loading ---
  if (phase === "loading") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // --- Mode Picker (first-time or new workspace) ---
  if (phase === "mode-picker") {
    return (
      <LoginShell>
        <div className="space-y-3">
          <button
            className="w-full text-left rounded-xl border border-border/50 bg-card p-5 shadow-lg hover:border-primary/30 hover:bg-accent/30 transition-all group"
            onClick={() => handleChooseMode(false)}
          >
            <div className="flex items-start gap-4">
              <div className="flex-none h-10 w-10 rounded-lg bg-muted/60 flex items-center justify-center group-hover:bg-primary/10 transition-colors">
                <HardDrive className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
              <div>
                <div className="font-medium text-sm">Local Analysis</div>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                  Open CSV files from your computer. Score offline — no server needed.
                </p>
              </div>
            </div>
          </button>

          <button
            className="w-full text-left rounded-xl border border-border/50 bg-card p-5 shadow-lg hover:border-green-500/30 hover:bg-accent/30 transition-all group"
            onClick={() => handleChooseMode(true)}
          >
            <div className="flex items-start gap-4">
              <div className="flex-none h-10 w-10 rounded-lg bg-muted/60 flex items-center justify-center group-hover:bg-green-500/10 transition-colors">
                <Globe className="h-5 w-5 text-muted-foreground group-hover:text-green-500 transition-colors" />
              </div>
              <div>
                <div className="font-medium text-sm">Connect to Server</div>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                  Enter a server URL to access shared files, consensus voting, and team scoring.
                </p>
              </div>
            </div>
          </button>
        </div>

        {workspaces.length > 0 && (
          <Button
            type="button"
            variant="ghost"
            className="w-full text-xs text-muted-foreground mt-4"
            onClick={handleBack}
          >
            <ArrowLeft className="h-3 w-3 mr-1" />
            Back to workspaces
          </Button>
        )}
      </LoginShell>
    );
  }

  // --- Workspace Picker ---
  if (phase === "workspace-picker") {
    const sorted = [...workspaces].sort(
      (a, b) => new Date(b.lastAccessedAt).getTime() - new Date(a.lastAccessedAt).getTime(),
    );

    return (
      <LoginShell>
        <Card className="shadow-lg border-border/50">
          <CardHeader className="pb-4">
            <CardTitle className="text-lg">Recent Workspaces</CardTitle>
            <CardDescription>Select a workspace or create a new one</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {sorted.map((ws) => (
              <button
                key={ws.id}
                className="w-full text-left px-3 py-2.5 rounded-lg border border-border/50 hover:bg-accent/50 transition-colors group flex items-start gap-3"
                onClick={() => handleSelectWorkspace(ws)}
              >
                <div className={`mt-0.5 h-2.5 w-2.5 rounded-full flex-none ${ws.serverUrl ? "bg-green-500" : "bg-muted-foreground/40"}`} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{ws.displayName}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {ws.serverUrl || "Local only"} &middot; {formatTimeAgo(ws.lastAccessedAt)}
                  </div>
                </div>
                <button
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:text-destructive"
                  onClick={(ev) => {
                    ev.stopPropagation();
                    deleteWorkspace(ws.id);
                  }}
                  title="Delete workspace"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </button>
            ))}

            <button
              className="w-full text-left px-3 py-2.5 rounded-lg border border-dashed border-border/50 hover:bg-accent/50 transition-colors flex items-center gap-3 text-muted-foreground"
              onClick={handleNewWorkspace}
            >
              <Plus className="h-4 w-4" />
              <span className="text-sm">New Workspace</span>
            </button>
          </CardContent>
        </Card>
      </LoginShell>
    );
  }

  // --- Login Form ---
  const title = loginMode === "server"
    ? (isCreatingNew && wantsServer ? "Connect to Server" : "Sign In")
    : (isCreatingNew ? "Local Analysis" : "Get Started");

  const description = loginMode === "server"
    ? (isCreatingNew && wantsServer ? "Enter your server details" : "Enter your credentials to continue")
    : (isCreatingNew ? "Score files offline on your computer" : `Signing in to ${selectedWorkspace?.displayName ?? "workspace"}`);

  const showPassword = loginMode === "server" && authRequired;
  const passwordLabel = "Site Password";
  const passwordPlaceholder = "Shared site password";

  // Show server URL field when user chose "Connect to Server" from mode picker
  const showServerUrl = isCreatingNew && wantsServer;

  // In browser mode with co-hosted backend, hide workspace-specific UI
  const isBrowserCohosted = !isTauri() && loginMode === "server" && !wantsServer;
  const showWorkspaceName = isCreatingNew && !isBrowserCohosted;
  const showBackButton = !isBrowserCohosted;

  const ModeIcon = loginMode === "server" ? Wifi : WifiOff;
  const modeLabel = loginMode === "server" ? "Connected to server" : "Local mode";

  return (
    <LoginShell>
      <Card className="shadow-lg border-border/50">
        <CardHeader className="pb-4">
          <CardTitle className="text-lg">{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={rhfHandleSubmit(handleSubmit)} className="space-y-4">
              {/* Server URL — only when user chose "Connect to Server" */}
              {showServerUrl && (
                <div className="space-y-2">
                  <Label htmlFor="serverUrl" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Server URL
                  </Label>
                  <div className="relative">
                    <Globe className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50" />
                    <Input
                      id="serverUrl"
                      type="text"
                      placeholder="https://sleep.lab.edu"
                      className="pl-9"
                      autoFocus
                      value={newServerUrl}
                      onChange={(e) => setNewServerUrl(e.target.value)}
                      onBlur={handleServerUrlBlur}
                    />
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {loginMode === "server" ? "Server detected" : "Paste the URL your lab administrator gave you"}
                  </p>
                </div>
              )}

              {/* Workspace name — only for new workspaces, hidden in browser co-hosted mode */}
              {showWorkspaceName && (
                <div className="space-y-2">
                  <Label htmlFor="displayName" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Workspace Name
                  </Label>
                  <Input
                    id="displayName"
                    type="text"
                    placeholder={wantsServer ? "e.g. Lab Server" : "e.g. My Analysis"}
                    value={newDisplayName}
                    onChange={(e) => setNewDisplayName(e.target.value)}
                  />
                </div>
              )}

              {showPassword && (
                <div className="space-y-2">
                  <Label htmlFor="password" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    {passwordLabel}
                  </Label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50" />
                    <Input
                      id="password"
                      type="password"
                      placeholder={passwordPlaceholder}
                      autoComplete="current-password"
                      className="pl-9"
                      required={loginMode === "server" && authRequired}
                      {...register("password")}
                    />
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="username" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Your Name
                </Label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground/50" />
                  <Input
                    id="username"
                    type="text"
                    placeholder="For audit logging (optional)"
                    autoComplete="username"
                    className="pl-9"
                    {...register("username")}
                  />
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Helps track who made scoring changes. Leave blank for anonymous.
                </p>
                {formErrors.username && (
                  <p className="text-xs text-destructive">{formErrors.username.message}</p>
                )}
              </div>

              {error && (
                <div className="text-sm text-destructive bg-destructive/10 px-3 py-2.5 rounded-lg border border-destructive/20">
                  {error}
                </div>
              )}

              <Button type="submit" className="w-full h-10" disabled={isLoading}>
                {isLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    {loginMode === "server" ? "Verifying..." : "Starting..."}
                  </>
                ) : (
                  "Continue"
                )}
              </Button>

              {showBackButton && (
                <Button
                  type="button"
                  variant="ghost"
                  className="w-full text-xs text-muted-foreground"
                  onClick={handleBack}
                >
                  <ArrowLeft className="h-3 w-3 mr-1" />
                  Back
                </Button>
              )}
            </form>
          </CardContent>
        </Card>

        {/* Mode indicator — hidden in browser co-hosted mode (always server) */}
        {!isBrowserCohosted && (
          <div className="flex items-center justify-center gap-1.5 mt-6">
            <ModeIcon className="h-3.5 w-3.5 text-muted-foreground/60" />
            <p className="text-xs text-muted-foreground/60">{modeLabel}</p>
          </div>
        )}
    </LoginShell>
  );
}

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "yesterday";
  return `${days}d ago`;
}
