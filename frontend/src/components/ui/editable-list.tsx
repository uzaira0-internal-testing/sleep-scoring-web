import { useState, useRef } from "react";
import { X, Plus } from "lucide-react";
import { Input } from "./input";
import { Button } from "./button";

interface EditableListProps {
  items: string[];
  onChange: (items: string[]) => void;
  placeholder?: string;
  maxItems?: number;
}

/**
 * Editable tag list: add items with input + badge list with remove buttons.
 * Used for groups, timepoints, and similar list-of-strings settings.
 */
export function EditableList({ items, onChange, placeholder = "Add item...", maxItems = 50 }: EditableListProps) {
  const [inputValue, setInputValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const addItem = () => {
    const trimmed = inputValue.trim();
    if (!trimmed || items.includes(trimmed) || items.length >= maxItems) return;
    onChange([...items, trimmed]);
    setInputValue("");
    inputRef.current?.focus();
  };

  const removeItem = (index: number) => {
    onChange(items.filter((_, i) => i !== index));
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addItem();
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          ref={inputRef}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="flex-1"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={addItem}
          disabled={!inputValue.trim() || items.includes(inputValue.trim()) || items.length >= maxItems}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
      {items.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {items.map((item, i) => (
            <span
              key={`${item}-${i}`}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-primary/10 text-primary text-sm"
            >
              {item}
              <button
                type="button"
                onClick={() => removeItem(i)}
                className="hover:bg-primary/20 rounded-full p-0.5 transition-colors"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}
      {items.length >= maxItems && (
        <p className="text-xs text-muted-foreground">Maximum of {maxItems} items reached</p>
      )}
    </div>
  );
}
