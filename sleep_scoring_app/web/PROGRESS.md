# Sleep Scoring Web Application - Progress Tracker

**Start Date**: January 2, 2026
**Plan Document**: `C:\Users\u248361\.claude\plans\happy-stargazing-kite.md`

---

## Quick Reference

### Tech Stack (2025/2026)

**Backend:**
```
Python 3.12 + FastAPI 0.115 + Pydantic v2
├── Database: PostgreSQL (asyncpg) + SQLite (aiosqlite)
├── ORM: SQLAlchemy 2.0 (async) + Alembic
├── Auth: FastAPI-Users (JWT + OAuth ready)
├── Files: python-multipart + aiofiles
├── Data: Pandas 2.2 + NumPy 2.x
├── Cache: cachetools
└── Testing: pytest + httpx + factory-boy
```

**Frontend:**
```
React 19 + TypeScript 5.7 + Vite 6
├── UI: shadcn/ui + Tailwind v4 + Framer Motion
├── State: Zustand (client) + TanStack Query v5 (server)
├── Forms: React Hook Form + Zod
├── Tables: TanStack Table v8
├── Routing: TanStack Router
├── Charts: uPlot + DOM overlay markers
├── Dates: date-fns v4
├── Events: RxJS (for complex streams)
├── Storage: localStorage + idb-keyval (IndexedDB)
├── API: openapi-fetch (generated from Pydantic)
└── Testing: Playwright + Vitest + MSW
```

**Key Patterns**: Gang of Four, WCAG 2.1 AA accessibility

### Key Decisions
- [x] Columnar JSON for data transfer (confirmed from benchmark POC)
- [x] uPlot + DOM overlay for markers (confirmed from benchmark POC)
- [x] shadcn/ui for beautiful 2025/2026 UI
- [x] Pydantic + OpenAPI as single source of truth
- [x] Multi-user consensus system (from screenshot-annotator)
- [x] No GT3X support initially (CSV only)
- [x] React 19 (latest stable)

---

## Phase 1: Foundation (Backend Core)

### Status: COMPLETE

| Task | Status | Notes |
|------|--------|-------|
| Set up FastAPI project structure | [x] | `sleep_scoring_web/` directory |
| Define Pydantic models | [x] | Port from desktop dataclasses |
| Set up SQLAlchemy + Alembic | [x] | PostgreSQL primary, SQLite backup |
| Implement JWT auth | [x] | Custom JWT with passlib/python-jose |
| Implement file upload endpoint | [x] | CSV only |
| Port CSV loader | [x] | From `io/sources/csv_loader.py` |
| Implement activity data endpoint | [x] | Columnar JSON format |
| Generate OpenAPI spec | [x] | Auto from Pydantic at `/openapi.json` |

### Files Created
- [x] `sleep_scoring_web/__init__.py`
- [x] `sleep_scoring_web/main.py`
- [x] `sleep_scoring_web/config.py`
- [x] `sleep_scoring_web/schemas/__init__.py`
- [x] `sleep_scoring_web/schemas/enums.py`
- [x] `sleep_scoring_web/schemas/models.py`
- [x] `sleep_scoring_web/api/__init__.py`
- [x] `sleep_scoring_web/api/deps.py`
- [x] `sleep_scoring_web/api/auth.py`
- [x] `sleep_scoring_web/api/files.py`
- [x] `sleep_scoring_web/api/activity.py`
- [x] `sleep_scoring_web/db/__init__.py`
- [x] `sleep_scoring_web/db/session.py`
- [x] `sleep_scoring_web/db/models.py`
- [x] `sleep_scoring_web/services/__init__.py`
- [x] `sleep_scoring_web/services/loaders/__init__.py`
- [x] `sleep_scoring_web/services/loaders/csv_loader.py`
- [x] `sleep_scoring_web/services/algorithms/__init__.py`
- [x] `sleep_scoring_web/services/algorithms/sadeh.py`

### Tests
- [ ] Unit tests for CSV loader
- [ ] API tests for file upload
- [ ] API tests for activity data
- [ ] Playwright: Can upload file and see data

---

## Phase 2: Scoring Engine

### Status: PARTIAL

| Task | Status | Notes |
|------|--------|-------|
| Port Sadeh algorithm | [x] | Implemented in `services/algorithms/sadeh.py` |
| Port Cole-Kripke algorithm | [ ] | Already pure Python |
| Port Choi nonwear detection | [ ] | Already pure Python |
| Create algorithm service | [ ] | Strategy pattern |
| Add scoring endpoint | [x] | `/activity/{file_id}/{date}/sadeh` |
| Cache algorithm results | [ ] | Store in database |

---

## Phase 3: Frontend Shell

### Status: NOT STARTED

| Task | Status | Notes |
|------|--------|-------|
| Set up React 19 + Vite | [ ] | TypeScript strict mode |
| Install shadcn/ui | [ ] | With Tailwind CSS |
| Set up theme system | [ ] | Dark/Light/System modes |
| Generate TypeScript client | [ ] | From OpenAPI spec |
| Implement Zustand store | [ ] | Mirror desktop Redux |
| Build ActivityPlot | [ ] | uPlot + DOM overlay |
| Build FileNav component | [ ] | File/date selection |
| Set up accessibility | [ ] | WCAG 2.1 AA |
| Implement settings persistence | [ ] | localStorage + IndexedDB |

---

## Phase 4: Marker System

### Status: NOT STARTED

| Task | Status | Notes |
|------|--------|-------|
| Implement DragHandle component | [ ] | From benchmark POC |
| Implement MarkerRegion shading | [ ] | CSS + DOM overlay |
| Implement marker creation | [ ] | Two-click pattern |
| Implement overlap prevention | [ ] | Validation logic |
| Add marker API endpoints | [ ] | CRUD operations |
| Connect markers to store | [ ] | Zustand integration |
| Implement autosave | [ ] | Debounced saves |
| Add keyboard shortcuts | [ ] | Customizable bindings |
| Add undo/redo | [ ] | Command + Memento patterns |

---

## Phase 5: Multi-User Consensus

### Status: NOT STARTED

| Task | Status | Notes |
|------|--------|-------|
| Implement user_annotations table | [ ] | One per user per date |
| Implement consensus_results table | [ ] | Calculated when 2+ annotations |
| Port ConsensusService | [ ] | From screenshot-annotator |
| Add consensus API endpoints | [ ] | Compare, resolve |
| Build ConsensusDashboard | [ ] | Overview page |
| Build comparison view | [ ] | Side-by-side |
| Implement dispute resolution | [ ] | Admin only |

---

## Phase 6: Export & Metrics

### Status: NOT STARTED

| Task | Status | Notes |
|------|--------|-------|
| Port MetricsCalculationService | [ ] | From desktop |
| Implement export endpoints | [ ] | Streaming CSV/Excel |
| Build export UI | [ ] | Modal with options |
| Add metrics display | [ ] | In scoring view |

---

## Phase 7: Polish & Parity

### Status: NOT STARTED

| Task | Status | Notes |
|------|--------|-------|
| Sleep diary integration | [ ] | |
| Batch processing UI | [ ] | |
| Study configuration | [ ] | |
| Admin file preload | [ ] | |
| SQLite backup system | [ ] | |
| Cross-browser testing | [ ] | |
| Performance optimization | [ ] | |

---

## Accessibility Checklist

### Theme Support
- [ ] Dark mode
- [ ] Light mode
- [ ] System preference detection
- [ ] High contrast mode

### Color Accessibility
- [ ] Color blind palettes (8 options)
- [ ] Custom marker colors
- [ ] Non-color indicators (patterns/shapes)

### Screen Reader
- [ ] ARIA labels on all interactive elements
- [ ] Live regions for dynamic updates
- [ ] Semantic HTML with proper landmarks

### Keyboard Navigation
- [ ] Visible focus indicators
- [ ] Logical tab order
- [ ] Skip links
- [ ] Full keyboard control
- [ ] Customizable shortcuts

### Motor Accessibility
- [ ] 44x44px minimum touch targets
- [ ] Click-to-place alternative to drag
- [ ] Reduced motion support

---

## Design Patterns Implementation

### Creational
- [ ] Factory Method: LoaderFactory
- [ ] Abstract Factory: AlgorithmFactory
- [ ] Builder: ExportBuilder
- [ ] Singleton: SettingsService

### Structural
- [ ] Adapter: DatabaseAdapter
- [ ] Facade: ScoringFacade
- [ ] Composite: MarkerCollection
- [ ] Decorator: CachingDecorator
- [ ] Proxy: LazyDataProxy

### Behavioral
- [ ] Observer: Zustand subscriptions
- [ ] Strategy: ScoringStrategy
- [ ] Command: MarkerCommand (undo/redo)
- [ ] State: ConsensusState
- [ ] Template Method: BaseLoader
- [ ] Chain of Responsibility: ValidationChain
- [ ] Mediator: ConsensusMediator
- [ ] Memento: MarkerMemento

---

## Notes & Decisions Log

### January 2, 2026
- Initial plan created
- Confirmed: uPlot + DOM overlay for markers
- Confirmed: Columnar JSON for data transfer
- Confirmed: React 19, shadcn/ui, WCAG 2.1 AA
- Confirmed: No GT3X support initially (CSV only)
- Confirmed: Multi-user consensus from screenshot-annotator pattern
- **Phase 1 Complete**: Backend foundation implemented
  - FastAPI 0.115+ with Pydantic v2 schemas
  - SQLAlchemy 2.0 async with SQLite (PostgreSQL ready)
  - JWT authentication (register, login, refresh, /me)
  - File upload with CSV parsing
  - Activity data API with columnar JSON format
  - Sadeh algorithm implemented and exposed via API
  - OpenAPI 3.1 spec auto-generated

---

## Blocked / Needs Discussion

*None currently*

---

## Completed

### Phase 1: Foundation (Backend Core)
- FastAPI project structure: `sleep_scoring_web/`
- Pydantic models for all domain types
- SQLAlchemy models with async support
- JWT auth with access/refresh tokens
- File upload endpoint with CSV processing
- Activity data endpoint returning columnar JSON
- OpenAPI spec at `/openapi.json`

**Run the server:**
```bash
uv pip install -e ".[web]"
uv run uvicorn sleep_scoring_web.main:app --reload --port 8000
```

**API Documentation:** http://localhost:8000/docs
