# Scoring Page Smoothness — Design Spec

**Date:** 2026-03-17
**Scope:** Performance fixes + perceived smoothness improvements for the scoring page
**Files:** `frontend/src/components/activity-plot.tsx`, `frontend/src/pages/scoring.tsx`, `frontend/src/index.css`

---

## Goal

Make the scoring page feel extremely modern, smooth, and fast — including on slow computers and 30fps displays.

Two categories of work:
1. **Real bottleneck removal** — eliminate jank that exists today
2. **Perceived smoothness** — micro-interactions that make the app feel alive

---

## Part 1: Performance Fixes

### 1a. rAF-gate Drag Style Updates

**Problem:** In `createMarkerLine`'s `onMouseMove` handler, `element.style.left/width/height` is mutated directly on every event. Mice fire at 60–240Hz; on a slow machine or 30fps display the browser queues more mutations than it can paint. `detectSleepOnsetOffset()` also runs synchronously on every event.

**Fix — coalesce pattern:**

```ts
let dragRafId: number | null = null;
let pendingDragLeft = 0;  // latest target position

const onMouseMove = (e: MouseEvent) => {
  // compute new position (cheap)
  pendingDragLeft = computeNewLeft(e);

  // coalesce: cancel old rAF, schedule new one
  if (dragRafId !== null) cancelAnimationFrame(dragRafId);
  dragRafId = requestAnimationFrame(() => {
    dragRafId = null;
    // apply ALL style mutations here
    line.style.left = pendingDragLeft + 'px';
    // update region width, label position, etc.
    // rerun detectSleepOnsetOffset() here
  });
};
```

Both style mutations and `detectSleepOnsetOffset()` move inside the rAF callback. Cancel-and-reschedule (not skip-if-pending) ensures the latest mouse position is always applied within one frame.

**Cleanup:** In `onMouseUp`, cancel any pending `dragRafId` and apply the final position **synchronously** (no rAF) so the last frame is never dropped. Since `onMouseUp` runs after the last `mousemove`, a pending rAF may or may not have already fired — cancelling and applying synchronously guarantees the correct final state regardless of timing.

### 1b. Marker DOM Update In-Place

**Problem:** `renderMarkers()` runs on every marker state change. Each call does `querySelectorAll → removeAll → recreate all nodes`, causing 100–300 DOM node create/destroy cycles per state change.

**Fix — maintain a live element map:**

```ts
// Keyed by stable marker identity string
type MarkerKey = string; // e.g. "sleep-1704067200" (type + onset timestamp)
interface MarkerElements {
  line?: HTMLDivElement;
  region?: HTMLDivElement;
  label?: HTMLDivElement;
}
// Stored as a ref inside wheelZoomPlugin (or passed in):
const markerElMap = new Map<MarkerKey, MarkerElements>();
```

**Key format:** `${markerType}-${onsetTimestamp}` — onset timestamp is stable across re-renders.

**Render loop:**
1. Build a `Set<MarkerKey>` of all keys that should exist this frame
2. For keys in the map but NOT in this frame's set: remove those elements from DOM and delete from map
3. For keys in this frame's set but NOT in the map: create elements, append to DOM, add to map
4. For keys in both: update `style.left`, `style.width`, `style.color` in-place (no DOM creation)

**Cleanup on destroy:** In the uPlot `destroy` hook, iterate `markerElMap`, remove all elements from DOM, then clear the map. This prevents stale nodes surviving a chart rebuild.

**Lifecycle across chart rebuild:** When the chart is destroyed and a new one is created, `markerElMap` is cleared in `destroy`. The first `renderMarkers()` call on the new chart therefore treats every marker key as new (step 3 — create and append). This is correct: the old DOM nodes are gone, new ones must be created. The `animatedMarkerKeysRef` is NOT cleared on chart rebuild so the spring animation does not re-fire for markers that were already present before the rebuild.

**`detectSleepOnsetOffset()` in drag:** This call is also moved inside the rAF callback alongside the style mutations. It does not need its own separate gating — one rAF per frame covers both.

---

## Part 2: Perceived Smoothness

### 2a. Date Navigation — Ghost Cross-Fade

**Problem:** Clicking prev/next date blanks the plot while activity data loads. User sees an empty chart.

**Design:**

- **Never blank:** Keep the current plot visible until new data is ready
- **Stale indicator:** If new data hasn't arrived within 300ms of navigation, dim the plot to `opacity: 0.4` (signals stale, not broken)
- **Fade in:** When new data arrives, fade the plot to `opacity: 1` over 150ms

**Progress bar:** A 2px-tall indeterminate shimmer bar positioned absolutely at the top edge of the plot container, visible only while `isLoadingDate` is true. Animated as a sliding gradient (`background-position` keyframe) using the theme accent color at 60% opacity. Disappears instantly when data arrives (no fade needed — the plot fade-in is the signal).

**`isStale` prop on `ActivityPlot`:**

```ts
// ActivityPlotProps addition:
isStale?: boolean;

// Applied in ActivityPlot's container div:
<div
  ref={containerRef}
  className="w-full h-full"
  style={{ opacity: isStale ? 0.4 : 1, transition: 'opacity 0.15s' }}
/>
```

**State management in `ScoringPage`:**

```ts
const staleTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
const [isStale, setIsStale] = useState(false);

// On navigation:
const handleNavigate = (delta: number) => {
  // clear any existing stale timeout
  if (staleTimeoutRef.current) clearTimeout(staleTimeoutRef.current);
  // schedule stale dim after 300ms
  staleTimeoutRef.current = setTimeout(() => setIsStale(true), 300);
  navigateDate(delta);
};

// When activity query settles (data arrived):
useEffect(() => {
  if (!activityQuery.isLoading) {
    if (staleTimeoutRef.current) clearTimeout(staleTimeoutRef.current);
    staleTimeoutRef.current = null;
    setIsStale(false);
  }
}, [activityQuery.isLoading]);

// Cleanup on unmount:
useEffect(() => () => {
  if (staleTimeoutRef.current) clearTimeout(staleTimeoutRef.current);
}, []);
```

**Double-navigation:** Each navigation clears and restarts the stale timeout. The plot stays visible throughout. No flash because opacity only moves 1→0.4, never 1→0.

### 2b. Marker Placement — Spring Scale-In Animation

**Problem:** Newly placed markers appear instantly, feeling abrupt.

**Design:** When an onset or offset line is first placed (not drag-repositioned), play a spring scale-in:

```css
/* frontend/src/index.css */
@keyframes marker-spring-in {
  0%   { transform: scaleY(0);    transform-origin: top center; }
  70%  { transform: scaleY(1.08); transform-origin: top center; }
  100% { transform: scaleY(1.0);  transform-origin: top center; }
}

.marker-spring-in {
  animation: marker-spring-in 200ms ease-out forwards;
}
```

**Tracking in `activity-plot.tsx`:**

```ts
// Ref so it survives re-renders without triggering them
const animatedMarkerKeysRef = useRef<Set<string>>(new Set());
```

**When creating a DOM element for a new key (step 3 of 1b's render loop):**
```ts
if (!animatedMarkerKeysRef.current.has(key)) {
  lineEl.classList.add('marker-spring-in');
  animatedMarkerKeysRef.current.add(key);
  lineEl.addEventListener('animationend', () => {
    lineEl.classList.remove('marker-spring-in');
  }, { once: true });
}
```

**Clearing:** When a marker is removed from the map (step 2 of 1b's render loop), also delete its key from `animatedMarkerKeysRef.current`. This ensures if the same onset timestamp is reused (unlikely but possible), the animation replays.

**Drag-repositioned lines:** Animation does NOT fire on position updates (step 4), only on first creation. No spring on nonwear or adjacent-day markers — only user-placed sleep/nap onset and offset lines.

---

## Future Work (Not in Scope)

### Canvas Overlay for Markers

Replace all marker DOM nodes with a single `<canvas>` overlay drawn via uPlot's `draw` hook. Eliminates DOM thrashing entirely — marker rendering becomes as fast as drawing lines on a canvas.

**Why deferred:** ~600 lines of DOM-creation code rewritten, marker interaction (click targets, drag hit areas) requires manual hit-testing against canvas coordinates. The in-place DOM update fix (1b) achieves most of the benefit with far less risk.

**When to revisit:** If visible marker count grows significantly (>50), or if 1b proves insufficient on lowest-end target hardware.

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/components/activity-plot.tsx` | rAF-gate drag (1a), marker DOM map (1b), spring animation tracking (2b) |
| `frontend/src/pages/scoring.tsx` | stale timeout logic, `isStale` prop, `isLoadingDate` progress bar visibility (2a) |
| `frontend/src/index.css` | `@keyframes marker-spring-in`, `.marker-spring-in`, progress bar shimmer keyframe (2b, 2a) |

---

## Success Criteria

- Dragging a marker on a 30fps display feels smooth (no visible stutter)
- Date navigation never shows a blank plot
- Newly placed markers animate in with a spring feel
- No regressions in marker placement accuracy, drag behavior, or existing tests
