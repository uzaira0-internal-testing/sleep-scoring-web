import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, Copy, RefreshCw, Trash2 } from "lucide-react";
import { appendErrorLog } from "@/lib/error-log";
import { config } from "@/config";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  copied: boolean;
}

/**
 * Global error boundary — catches React render errors and shows a recovery UI
 * instead of a blank white screen.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { hasError: false, error: null, copied: false };

  // Instance property avoids setState + double render from componentDidCatch
  private _componentStack: string | null = null;

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this._componentStack = errorInfo.componentStack ?? null;
    appendErrorLog({
      message: error.message,
      stack: error.stack,
      componentStack: errorInfo.componentStack ?? undefined,
    });
  }

  handleReload = (): void => {
    window.location.reload();
  };

  handleResetApp = (): void => {
    // Clear session state but keep workspace data
    try {
      sessionStorage.clear();
    } catch { /* ignore */ }
    window.location.href = window.location.origin + config.basePath + "/";
  };

  handleCopyError = (): void => {
    const { error } = this.state;
    const text = [
      `Error: ${error?.message}`,
      `URL: ${window.location.href}`,
      `Time: ${new Date().toISOString()}`,
      "",
      "Stack:",
      error?.stack,
      "",
      "Component Stack:",
      this._componentStack,
    ].join("\n");

    navigator.clipboard.writeText(text).then(
      () => {
        this.setState({ copied: true });
        setTimeout(() => this.setState({ copied: false }), 2000);
      },
      () => { /* clipboard unavailable (insecure context or not focused) */ },
    );
  };

  override render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const { error, copied } = this.state;

    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-4">
        <div className="w-full max-w-md space-y-6">
          <div className="text-center">
            <div className="inline-flex h-14 w-14 rounded-2xl bg-destructive/10 items-center justify-center mb-4">
              <AlertTriangle className="h-7 w-7 text-destructive" />
            </div>
            <h1 className="text-xl font-semibold tracking-tight">Something went wrong</h1>
            <p className="text-sm text-muted-foreground mt-2">
              The app encountered an unexpected error. Your data is safe.
            </p>
          </div>

          {/* Error details */}
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            <p className="text-sm font-mono text-destructive break-all">
              {error?.message || "Unknown error"}
            </p>
          </div>

          {/* Actions */}
          <div className="space-y-2">
            <button
              onClick={this.handleReload}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary text-primary-foreground h-10 px-4 text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              Reload Page
            </button>

            <button
              onClick={this.handleResetApp}
              className="w-full flex items-center justify-center gap-2 rounded-lg border border-border h-10 px-4 text-sm font-medium hover:bg-accent transition-colors"
            >
              <Trash2 className="h-4 w-4" />
              Reset Session &amp; Go to Login
            </button>

            <button
              onClick={this.handleCopyError}
              className="w-full flex items-center justify-center gap-2 rounded-lg border border-border h-10 px-4 text-sm text-muted-foreground hover:bg-accent transition-colors"
            >
              <Copy className="h-4 w-4" />
              {copied ? "Copied!" : "Copy Error Details"}
            </button>
          </div>

          <p className="text-xs text-center text-muted-foreground">
            Error logs are saved locally. Check browser console for details.
          </p>
        </div>
      </div>
    );
  }
}
