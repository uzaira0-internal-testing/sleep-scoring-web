import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "@/components/theme-provider";
import { ErrorBoundary } from "@/components/error-boundary";
import { appendErrorLog } from "@/lib/error-log";
import { queryClient } from "@/query-client";
import App from "./App";
import "./index.css";

// Global unhandled error/rejection logging (persists to localStorage)
window.addEventListener("error", (event) => {
  appendErrorLog({ message: event.message, stack: event.error?.stack });
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason;
  const message = reason instanceof Error ? reason.message : String(reason);
  const stack = reason instanceof Error ? reason.stack : undefined;
  appendErrorLog({ message: `Unhandled rejection: ${message}`, stack });
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider defaultTheme="system" storageKey="sleep-scoring-theme">
          <App />
        </ThemeProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>
);
