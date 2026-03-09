<objective>
Fix the inconsistent uPlot rendering and restructure the web app navigation to match user requirements. The plot currently renders inconsistently (sometimes blank, requires page refresh). The app architecture needs to change from separate Files/Scoring pages to a unified Scoring page with file dropdown.
</objective>

<context>
This is a sleep-scoring web application (React frontend with FastAPI backend).

Current state:
- Activity plot (uPlot) renders inconsistently - sometimes shows data, sometimes blank
- Fix was added for X scale range calculation but rendering is still unreliable
- App has Files page and Scoring page as separate routes

Required changes:
1. Fix uPlot rendering to be 100% reliable
2. Remove Files page entirely - files should be a dropdown in Scoring page
3. Add Study Settings and Data Settings tabs before Scoring

Read these files for context:
@frontend/src/components/activity-plot.tsx - Current plot implementation with X scale fix
@frontend/src/pages/scoring.tsx - Current scoring page
@frontend/src/pages/files.tsx - Files page to be removed/converted to dropdown
@frontend/src/store/index.ts - Zustand store for state management
@frontend/src/App.tsx - Router configuration
</context>

<requirements>
## Part 1: Fix Plot Rendering

1. Diagnose why uPlot renders inconsistently:
   - Check if data is loaded before chart creation
   - Verify chartData memoization dependencies
   - Ensure chart is only created when container is mounted AND data is available
   - Check for race conditions between data loading and chart initialization

2. Implement robust rendering:
   - Add explicit checks for valid data before creating chart
   - Use useLayoutEffect instead of useEffect if timing is the issue
   - Consider adding a loading state that prevents chart creation until data is fully ready
   - Add error boundaries around the chart component

3. Test the fix:
   - Chart should render on first load every time
   - Chart should persist through date navigation
   - Chart should update cleanly when switching files

## Part 2: Restructure Navigation

1. Remove Files page as a separate route:
   - Files should become a dropdown/select in the Scoring page header
   - Show file name, participant ID, and row count in dropdown
   - Auto-select first file on initial load

2. Create new tab structure (in order):
   - **Study Settings** tab - placeholder for study configuration
   - **Data Settings** tab - placeholder for data configuration
   - **Scoring** tab - the main activity plot and marker interface (current scoring page content)

3. Update routing:
   - /settings/study → Study Settings tab
   - /settings/data → Data Settings tab
   - /scoring → Scoring tab (default)
   - Remove /files route entirely

4. Update sidebar navigation:
   - Study Settings
   - Data Settings
   - Scoring (default/active)

## Part 3: File Selector in Scoring Header

1. Add file dropdown in scoring page header:
   - Position: Left side of header, after back button (or replace back button)
   - Shows: Currently selected filename
   - Dropdown content: All available files with metadata
   - On select: Load that file's data

2. Maintain existing header elements:
   - Date navigation (keep on right side)
   - File info display
</requirements>

<implementation>
Technical approach:

1. For plot reliability:
   - Wrap chart creation in explicit data availability check
   - Use a ref to track if chart was successfully initialized
   - Add re-initialization logic if chart fails to render
   - Consider using uPlot's setData() for updates instead of destroying/recreating

2. For navigation:
   - Create TabLayout component with Study Settings, Data Settings, Scoring tabs
   - Move file selection into Scoring page as a shadcn Select component
   - Update store to handle file selection from dropdown

3. File structure changes:
   - DELETE: frontend/src/pages/files.tsx
   - MODIFY: frontend/src/pages/scoring.tsx (add file dropdown)
   - CREATE: frontend/src/pages/study-settings.tsx (placeholder)
   - CREATE: frontend/src/pages/data-settings.tsx (placeholder)
   - MODIFY: frontend/src/App.tsx (update routes)
   - MODIFY: frontend/src/components/layout.tsx (update sidebar)

DO NOT:
- Break existing marker functionality
- Remove any working features
- Add unnecessary complexity
</implementation>

<output>
Files to create/modify:
- `./frontend/src/components/activity-plot.tsx` - Fix rendering reliability
- `./frontend/src/pages/scoring.tsx` - Add file dropdown, restructure
- `./frontend/src/pages/study-settings.tsx` - New placeholder page
- `./frontend/src/pages/data-settings.tsx` - New placeholder page
- `./frontend/src/App.tsx` - Update routes
- `./frontend/src/components/layout.tsx` - Update sidebar navigation
- DELETE `./frontend/src/pages/files.tsx` after migrating file list logic
</output>

<verification>
Before declaring complete:

1. Plot rendering test:
   - Fresh page load shows plot with data immediately
   - No blank plots on any load
   - Date navigation updates plot correctly
   - File switching loads new data correctly

2. Navigation test:
   - Sidebar shows: Study Settings, Data Settings, Scoring
   - Default route goes to Scoring
   - File dropdown in scoring header works
   - No /files route exists

3. Run E2E test:
   - `cd frontend && npx playwright test e2e/scoring-page.spec.ts --project=chromium`

4. Visual verification:
   - Take screenshot and confirm plot is visible with data
</verification>

<success_criteria>
- Plot renders correctly 100% of the time on page load
- Files are selectable via dropdown in Scoring page (no separate Files page)
- Three tabs in sidebar: Study Settings, Data Settings, Scoring
- All existing marker functionality still works
- E2E tests pass
</success_criteria>
