import { useCallback, useRef, useState } from "react";
import { Button } from "./button";

interface ConfirmDialogProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** "destructive" makes the confirm button red */
  variant?: "default" | "destructive";
}

/**
 * Styled confirmation dialog that replaces native browser confirm().
 */
export function ConfirmDialog({
  open,
  onConfirm,
  onCancel,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  variant = "default",
}: ConfirmDialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onCancel}
      onKeyDown={(e) => {
        if (e.key === "Escape") onCancel();
        if (e.key === "Enter") onConfirm();
      }}
      tabIndex={-1}
      ref={(el) => el?.focus()}
    >
      <div
        ref={panelRef}
        className="bg-background border rounded-lg shadow-xl p-6 max-w-sm mx-4 w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold mb-1.5">{title}</h3>
        {description && (
          <p className="text-sm text-muted-foreground mb-4">{description}</p>
        )}
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" size="sm" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            size="sm"
            variant={variant === "destructive" ? "destructive" : "default"}
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * Styled alert dialog that replaces native browser alert().
 * Shows a message with a single "OK" button.
 */
export function AlertDialog({
  open,
  onClose,
  title,
  description,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
}) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      onClick={onClose}
      onKeyDown={(e) => {
        if (e.key === "Escape" || e.key === "Enter") onClose();
      }}
      tabIndex={-1}
      ref={(el) => el?.focus()}
    >
      <div
        className="bg-background border rounded-lg shadow-xl p-6 max-w-sm mx-4 w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-sm font-semibold mb-1.5">{title}</h3>
        {description && (
          <p className="text-sm text-muted-foreground mb-4">{description}</p>
        )}
        <div className="flex justify-end mt-4">
          <Button size="sm" onClick={onClose}>OK</Button>
        </div>
      </div>
    </div>
  );
}

interface ConfirmState {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "default" | "destructive";
}

/**
 * Hook that provides an imperative confirm() replacement.
 *
 * Usage:
 *   const { confirm, confirmDialog } = useConfirmDialog();
 *   // In handler:
 *   const ok = await confirm({ title: "Delete?", variant: "destructive" });
 *   if (ok) doDelete();
 *   // In JSX:
 *   {confirmDialog}
 */
export function useConfirmDialog() {
  const [state, setState] = useState<ConfirmState>({ open: false, title: "" });
  const resolveRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = useCallback(
    (opts: Omit<ConfirmState, "open">): Promise<boolean> => {
      return new Promise((resolve) => {
        resolveRef.current = resolve;
        setState({ ...opts, open: true });
      });
    },
    []
  );

  const handleConfirm = useCallback(() => {
    setState((s) => ({ ...s, open: false }));
    resolveRef.current?.(true);
    resolveRef.current = null;
  }, []);

  const handleCancel = useCallback(() => {
    setState((s) => ({ ...s, open: false }));
    resolveRef.current?.(false);
    resolveRef.current = null;
  }, []);

  const confirmDialog = (
    <ConfirmDialog
      open={state.open}
      onConfirm={handleConfirm}
      onCancel={handleCancel}
      title={state.title}
      description={state.description}
      confirmLabel={state.confirmLabel}
      cancelLabel={state.cancelLabel}
      variant={state.variant}
    />
  );

  return { confirm, confirmDialog };
}

interface AlertState {
  open: boolean;
  title: string;
  description?: string;
}

/**
 * Hook that provides an imperative alert() replacement.
 *
 * Usage:
 *   const { alert, alertDialog } = useAlertDialog();
 *   // In handler:
 *   await alert({ title: "Error", description: "Something failed" });
 *   // In JSX:
 *   {alertDialog}
 */
export function useAlertDialog() {
  const [state, setState] = useState<AlertState>({ open: false, title: "" });
  const resolveRef = useRef<(() => void) | null>(null);

  const alert = useCallback(
    (opts: Omit<AlertState, "open">): Promise<void> => {
      return new Promise((resolve) => {
        resolveRef.current = resolve;
        setState({ ...opts, open: true });
      });
    },
    []
  );

  const handleClose = useCallback(() => {
    setState((s) => ({ ...s, open: false }));
    resolveRef.current?.();
    resolveRef.current = null;
  }, []);

  const alertDialog = (
    <AlertDialog
      open={state.open}
      onClose={handleClose}
      title={state.title}
      description={state.description}
    />
  );

  return { alert, alertDialog };
}
