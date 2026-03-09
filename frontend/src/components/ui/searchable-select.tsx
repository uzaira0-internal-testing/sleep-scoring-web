import * as React from "react";
import { ChevronDown, Search, X } from "lucide-react";
import { cn } from "@/lib/utils";

export interface SearchableSelectProps {
  options: Array<{
    value: string;
    label: string;
    disabled?: boolean;
  }>;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

/**
 * Select with search/filter input.
 * Opens a dropdown list filtered by typed text.
 */
const SearchableSelect = React.forwardRef<HTMLDivElement, SearchableSelectProps>(
  ({ options, value, onChange, placeholder = "Select...", className, disabled }, ref) => {
    const [open, setOpen] = React.useState(false);
    const [search, setSearch] = React.useState("");
    const containerRef = React.useRef<HTMLDivElement>(null);
    const inputRef = React.useRef<HTMLInputElement>(null);

    // Close on outside click
    React.useEffect(() => {
      const handler = (e: MouseEvent) => {
        if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
          setOpen(false);
          setSearch("");
        }
      };
      document.addEventListener("mousedown", handler);
      return () => document.removeEventListener("mousedown", handler);
    }, []);

    const filtered = options.filter((o) =>
      o.label.toLowerCase().includes(search.toLowerCase())
    );

    const selectedLabel = options.find((o) => o.value === value)?.label;

    return (
      <div ref={ref} className={cn("relative", className)}>
        <div
          ref={containerRef}
          className={cn(
            "relative",
            disabled && "opacity-50 pointer-events-none"
          )}
        >
          {/* Trigger button */}
          <button
            type="button"
            className={cn(
              "flex h-9 w-full items-center justify-between rounded-lg border border-input bg-background px-3 text-sm leading-tight shadow-sm transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
              "disabled:cursor-not-allowed disabled:opacity-50",
              !value && "text-muted-foreground"
            )}
            onClick={() => {
              setOpen(!open);
              if (!open) {
                setTimeout(() => inputRef.current?.focus(), 0);
              }
            }}
            disabled={disabled}
          >
            <span className="block min-w-0 flex-1 truncate text-left">
              {selectedLabel || placeholder}
            </span>
            <ChevronDown className="ml-2 h-4 w-4 shrink-0 opacity-40" />
          </button>

          {/* Dropdown */}
          {open && (
            <div className="absolute z-[1000] mt-1 w-full min-w-[300px] rounded-lg border border-border bg-popover shadow-md">
              {/* Search input */}
              <div className="flex items-center border-b px-2 py-1.5">
                <Search className="h-3.5 w-3.5 text-muted-foreground mr-1.5 shrink-0" />
                <input
                  ref={inputRef}
                  className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                  placeholder="Search files..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Escape") {
                      setOpen(false);
                      setSearch("");
                    }
                  }}
                />
                {search && (
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-foreground"
                    onClick={() => setSearch("")}
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              {/* Options list */}
              <div className="max-h-[300px] overflow-y-auto py-1">
                {filtered.length === 0 ? (
                  <div className="px-3 py-2 text-sm text-muted-foreground">
                    No files match
                  </div>
                ) : (
                  filtered.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      className={cn(
                        "flex w-full items-center px-3 py-1.5 text-sm text-left hover:bg-accent hover:text-accent-foreground transition-colors whitespace-nowrap",
                        option.value === value && "bg-accent/50 font-medium",
                        option.disabled && "opacity-50 pointer-events-none"
                      )}
                      onClick={() => {
                        onChange(option.value);
                        setOpen(false);
                        setSearch("");
                      }}
                      disabled={option.disabled}
                    >
                      <span className="block min-w-0 flex-1 truncate">{option.label}</span>
                    </button>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }
);
SearchableSelect.displayName = "SearchableSelect";

export { SearchableSelect };
