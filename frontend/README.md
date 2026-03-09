# Sleep Scoring Frontend

React + TypeScript + Bun frontend for the sleep scoring web application.

## Prerequisites

- Bun 1.3+
- Backend API running (default: `http://localhost:8500`)

## Development

```bash
bun run dev
```

Frontend default URL: `http://localhost:8501`

## Quality Checks

```bash
bun run typecheck
bun run lint
```

## E2E

```bash
bun run test:e2e
```

## API Types

```bash
bun run generate:types
```

This generates `src/api/schema.ts` from the backend OpenAPI schema.
