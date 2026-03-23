import { Check, X } from "lucide-react";

interface ActionResultProps {
  message: string;
  type: "success" | "error";
  onDismiss: () => void;
}

export function ActionResult({ message, type, onDismiss }: ActionResultProps) {
  return (
    <div className={`flex items-center gap-2 text-sm rounded-md px-3 py-2 ${
      type === "success" ? "bg-green-500/10 text-green-700 dark:text-green-400" : "bg-destructive/10 text-destructive"
    }`}>
      {type === "success" ? <Check className="h-3.5 w-3.5 flex-shrink-0" /> : <X className="h-3.5 w-3.5 flex-shrink-0" />}
      <span className="flex-1">{message}</span>
      <button onClick={onDismiss} className="hover:opacity-70">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
