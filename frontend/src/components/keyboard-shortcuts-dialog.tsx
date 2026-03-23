import { Keyboard } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

interface KeyboardShortcutsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Renders a styled keyboard key */
function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[26px] h-7 px-2 font-mono text-xs font-semibold bg-muted border border-border rounded shadow-[0_1px_0_1px_rgba(0,0,0,0.08)] dark:shadow-[0_1px_0_1px_rgba(255,255,255,0.05)]">
      {children}
    </kbd>
  );
}

const SHORTCUT_SECTIONS = [
  {
    title: "Marker Placement",
    shortcuts: [
      { keys: ["Click"], description: "Place onset, then offset (2-click)" },
      { keys: ["Esc"], description: "Cancel marker creation in progress" },
      { keys: ["Right-Click"], description: "Cancel marker creation" },
    ],
  },
  {
    title: "Marker Editing",
    shortcuts: [
      { keys: ["Q"], description: "Move onset/start LEFT 1 minute" },
      { keys: ["E"], description: "Move onset/start RIGHT 1 minute" },
      { keys: ["A"], description: "Move offset/end LEFT 1 minute" },
      { keys: ["D"], description: "Move offset/end RIGHT 1 minute" },
      { keys: ["Del"], description: "Delete selected marker" },
      { keys: ["C"], description: "Delete selected marker" },
    ],
  },
  {
    title: "Navigation",
    shortcuts: [
      { keys: ["\u2190"], description: "Previous date" },
      { keys: ["\u2192"], description: "Next date" },
      { keys: ["Scroll"], description: "Zoom in/out on plot" },
      { keys: ["Drag"], description: "Pan plot horizontally" },
    ],
  },
  {
    title: "View & Controls",
    shortcuts: [
      { keys: ["Ctrl", "S"], description: "Save markers" },
      { keys: ["Ctrl", "Z"], description: "Undo marker change" },
      { keys: ["Ctrl", "Shift", "Z"], description: "Redo marker change" },
      { keys: ["Ctrl", "Y"], description: "Redo marker change (alt)" },
      { keys: ["Ctrl", "4"], description: "Toggle 24h / 48h view" },
      { keys: ["Ctrl", "Shift", "C"], description: "Clear all markers" },
    ],
  },
] as const;

/**
 * Keyboard shortcuts reference dialog.
 */
export function KeyboardShortcutsDialog({ open, onOpenChange }: KeyboardShortcutsDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Keyboard className="h-5 w-5" />
            Keyboard Shortcuts
          </DialogTitle>
          <DialogDescription>
            Quick reference for all available shortcuts
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 max-h-[60vh] overflow-y-auto pr-1">
          {SHORTCUT_SECTIONS.map((section) => (
            <section key={section.title}>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
                {section.title}
              </h3>
              <div className="space-y-1.5">
                {section.shortcuts.map((shortcut) => (
                  <div
                    key={shortcut.description}
                    className="flex items-center justify-between py-1"
                  >
                    <span className="text-sm">{shortcut.description}</span>
                    <div className="flex items-center gap-1 ml-4 flex-shrink-0">
                      {shortcut.keys.map((key, i) => (
                        <span key={i} className="flex items-center gap-0.5">
                          {i > 0 && <span className="text-muted-foreground text-xs mx-0.5">+</span>}
                          <Kbd>{key}</Kbd>
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>

        <div className="text-xs text-muted-foreground text-center pt-2 border-t">
          Marker editing shortcuts work when a marker is selected
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Button to open the keyboard shortcuts dialog */
export function KeyboardShortcutsButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8"
      onClick={onClick}
      title="Keyboard shortcuts"
      aria-label="Keyboard shortcuts"
    >
      <Keyboard className="h-4 w-4" />
    </Button>
  );
}
