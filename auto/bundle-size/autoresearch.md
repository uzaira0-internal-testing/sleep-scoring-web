# Autoresearch: Reduce Frontend Bundle Size

## Objective
Reduce total JS+CSS bundle size after Vite production build. The agent runs an autonomous experiment loop: edit → commit → benchmark → keep/discard.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `bundle_kb` (KB, lower is better)
- **Secondary**: individual chunk sizes, largest deps

## How to Run
`./auto/bundle-size/autoresearch.sh` — builds frontend, measures total JS+CSS in dist/.

## Files in Scope
- `frontend/src/**/*.ts` — All TypeScript source files
- `frontend/src/**/*.tsx` — All React components
- `frontend/src/services/` — Service layer
- `frontend/src/store/` — Zustand stores
- `frontend/src/hooks/` — React hooks
- `frontend/src/lib/` — Utility libraries
- `frontend/src/api/` — API client and types
- `frontend/vite.config.ts` — Vite build configuration
- `frontend/package.json` — Dependencies

## Off Limits
- `frontend/src/wasm/` — WASM bindings (built separately)
- `tests/` — Test files
- `auto/` — Autoresearch infrastructure
- `frontend/src/api/schema.ts` — Generated OpenAPI types

## Constraints
- All TypeScript checks must pass (`npx tsc -p tsconfig.app.json --noEmit`)
- No functionality removal
- No breaking UI changes
- Use `npx` not `bun` for all commands
- Semantic correctness must be preserved

## Strategic Direction
- Run `ANALYZE=1 npx vite build` to generate bundle treemap
- lucide-react: use named imports only, check for barrel imports
- date-fns: use subpath imports (`date-fns/format` not `date-fns`)
- React.lazy() for heavy routes (scoring page, admin, etc.)
- Check for duplicate copies of the same library
- Consider if react-resizable-panels, @uppy/*, @tanstack/react-query can be lazy loaded
- Tree-shake unused exports from services/ and lib/
- Evaluate if any devDependencies leak into production bundle

## Baseline
- **Commit**: 73784ab
- **bundle_kb**: (fill in after first run)

## What's Been Tried

## Current Best
- **bundle_kb**: (updated automatically by the loop)
