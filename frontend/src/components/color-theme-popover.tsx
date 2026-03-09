import { Palette, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { useColorTheme } from "@/store";
import { COLOR_PRESETS, PRESET_LABELS } from "@/lib/color-themes";

const COLOR_FIELDS: Array<{ key: string; label: string }> = [
  { key: "onset", label: "Onset" },
  { key: "offset", label: "Offset" },
  { key: "sleepOverlay", label: "Sleep Overlay" },
  { key: "nonwear", label: "Nonwear" },
  { key: "sensorNonwear", label: "Sensor Nonwear" },
  { key: "choiNonwear", label: "Choi Nonwear" },
  { key: "activityLine", label: "Activity Line" },
];

export function ColorThemePopover() {
  const { colorTheme, setColorTheme, applyColorPreset, resetColorTheme } =
    useColorTheme();

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          title="Color theme"
          data-testid="color-theme-btn"
        >
          <Palette className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64" align="end">
        <div className="space-y-3">
          <div className="text-sm font-medium">Color Theme</div>

          {/* Preset selector */}
          <div>
            <label className="text-xs text-muted-foreground">Preset</label>
            <select
              className="w-full mt-1 h-8 rounded-md border border-border bg-background px-2 text-sm"
              value={colorTheme.preset}
              onChange={(e) => applyColorPreset(e.target.value)}
            >
              {Object.entries(PRESET_LABELS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
              {!PRESET_LABELS[colorTheme.preset] && (
                <option value="custom" disabled>
                  Custom
                </option>
              )}
            </select>
          </div>

          {/* Individual color pickers */}
          <div className="space-y-1.5">
            {COLOR_FIELDS.map(({ key, label }) => (
              <div key={key} className="flex items-center gap-2">
                <input
                  type="color"
                  value={colorTheme[key as keyof typeof colorTheme] as string}
                  onChange={(e) =>
                    setColorTheme({ [key]: e.target.value })
                  }
                  className="h-6 w-6 rounded border border-border cursor-pointer bg-transparent"
                />
                <span className="text-xs">{label}</span>
              </div>
            ))}
          </div>

          {/* Reset button */}
          <Button
            variant="outline"
            size="sm"
            className="w-full h-7 text-xs gap-1"
            onClick={resetColorTheme}
          >
            <RotateCcw className="h-3 w-3" />
            Reset to Default
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
