import { HelpCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { MARKER_TYPES } from "@/api/types";
import { useSleepScoringStore } from "@/store";
import { hexToRgba } from "@/lib/color-themes";

interface ColorLegendDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Color legend dialog explaining marker colors and algorithm meanings.
 */
export function ColorLegendDialog({ open, onOpenChange }: ColorLegendDialogProps) {
  const colorTheme = useSleepScoringStore((state) => state.colorTheme);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Color Legend</DialogTitle>
          <DialogDescription>
            Understanding the colors and markers in the activity plot
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6">
          {/* Sleep Markers */}
          <section>
            <h3 className="font-semibold mb-2">Sleep Markers</h3>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded" style={{ backgroundColor: colorTheme.sleepOverlay }} />
                <span><strong>{MARKER_TYPES.MAIN_SLEEP}</strong> - Primary sleep period (overnight sleep)</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded" style={{ backgroundColor: colorTheme.sleepOverlay, opacity: 0.6 }} />
                <span><strong>{MARKER_TYPES.NAP}</strong> - Daytime nap or secondary sleep</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-1 h-4" style={{ backgroundColor: colorTheme.onset }} />
                <span><strong>Onset Line</strong> - Sleep start time</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-1 h-4" style={{ backgroundColor: colorTheme.offset }} />
                <span><strong>Offset Line</strong> - Sleep end time (wake time)</span>
              </div>
            </div>
          </section>

          {/* Nonwear Markers */}
          <section>
            <h3 className="font-semibold mb-2">Nonwear Markers</h3>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded" style={{ backgroundColor: colorTheme.sensorNonwear }} />
                <span><strong>Nonwear Sensor</strong> - Sensor-detected nonwear (from CSV data)</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded" style={{ backgroundColor: hexToRgba(colorTheme.choiNonwear, 0.3), border: `1px solid ${colorTheme.choiNonwear}` }} />
                <span><strong>Choi Nonwear</strong> - Algorithm-detected nonwear (hatched)</span>
              </div>
            </div>
          </section>

          {/* Algorithm Colors */}
          <section>
            <h3 className="font-semibold mb-2">Algorithm Results</h3>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded" style={{ backgroundColor: hexToRgba(colorTheme.sleepOverlay, 0.4) }} />
                <span><strong>Sleep</strong> - Algorithm scored as sleep (low activity)</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 bg-amber-500/40 rounded" />
                <span><strong>Wake</strong> - Algorithm scored as wake (high activity)</span>
              </div>
            </div>
          </section>

          {/* Data Table Colors */}
          <section>
            <h3 className="font-semibold mb-2">Data Table Colors</h3>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded" style={{ backgroundColor: hexToRgba(colorTheme.sleepOverlay, 0.3), borderLeft: `4px solid ${colorTheme.sleepOverlay}` }} />
                <span><strong>Current Marker Row</strong> - Selected marker timestamp</span>
              </div>
              <div className="flex items-center gap-3">
                <span style={{ color: colorTheme.sleepOverlay }}>Purple text</span>
                <span>- Sleep scored epochs</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-amber-600">Amber text</span>
                <span>- Wake scored epochs</span>
              </div>
              <div className="flex items-center gap-3">
                <span style={{ color: colorTheme.choiNonwear }}>Red text</span>
                <span>- Choi nonwear detected</span>
              </div>
              <div className="flex items-center gap-3">
                <span style={{ color: colorTheme.nonwear }}>Orange text</span>
                <span>- Manual nonwear overlap</span>
              </div>
            </div>
          </section>

        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Button to open the color legend dialog.
 */
export function ColorLegendButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={onClick}
      title="Show color legend and keyboard shortcuts"
      aria-label="Show color legend"
      data-testid="color-legend-btn"
    >
      <HelpCircle className="h-4 w-4" />
    </Button>
  );
}
