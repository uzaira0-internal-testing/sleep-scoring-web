# Sleep Scoring Web App - Current Status

**Last Updated:** February 10, 2026

## Overview

The web application covers the core sleep scoring workflow with algorithms, marker placement, metrics, diary integration, and export. Some desktop features are not yet ported (see gaps below).

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (React 19 + TypeScript + Bun)                     │
│  ├── Pages: login, scoring, export, settings, data-settings │
│  ├── Components: activity-plot, metrics-panel, diary-panel  │
│  ├── State: Zustand store                                   │
│  └── Charts: uPlot with custom marker overlay               │
├─────────────────────────────────────────────────────────────┤
│  Backend (FastAPI + Pydantic v2)                            │
│  ├── API: auth, files, activity, markers, export, diary     │
│  ├── Algorithms: Sadeh, Cole-Kripke, Choi nonwear           │
│  └── Services: metrics, export, file watcher                │
├─────────────────────────────────────────────────────────────┤
│  Database (PostgreSQL 16)                                   │
│  └── Tables: users, files, activity, markers, diary, settings│
├─────────────────────────────────────────────────────────────┤
│  Docker (docker-compose)                                    │
│  └── Services: frontend (8501), backend (8500), postgres    │
└─────────────────────────────────────────────────────────────┘
```

---

## Implemented Features

### Sleep Scoring
| Feature | Status | Location |
|---------|--------|----------|
| Sadeh Algorithm (Original + ActiLife) | DONE | `services/algorithms/sadeh.py` |
| Cole-Kripke Algorithm (Original + ActiLife) | DONE | `services/algorithms/cole_kripke.py` |
| Algorithm Selection Dropdown | DONE | `pages/scoring.tsx` |
| 24h/48h View Toggle | DONE | `pages/scoring.tsx` |

### Markers
| Feature | Status | Location |
|---------|--------|----------|
| Sleep Marker Creation (click-to-create) | DONE | `components/activity-plot.tsx` |
| Nonwear Marker Creation | DONE | `components/activity-plot.tsx` |
| Marker Type Selection (MAIN_SLEEP/NAP) | DONE | `pages/scoring.tsx` |
| Marker Persistence (auto-save) | DONE | `hooks/useMarkerAutoSave.ts` |
| Marker Deletion | DONE | `pages/scoring.tsx` |
| Marker Dragging (fine-tune position) | DONE | `components/activity-plot.tsx` |
| Arrow Guides (algorithm-detected onset/offset) | DONE | `components/activity-plot.tsx` |
| Adjacent Day Markers (dashed lines) | DONE | `components/activity-plot.tsx` |
| Diary-Click Marker Placement | DONE | `components/diary-panel.tsx` |

### Nonwear Detection
| Feature | Status | Location |
|---------|--------|----------|
| Choi Algorithm | DONE | `services/algorithms/choi.py` |
| Choi Visualization (striped overlay) | DONE | `components/activity-plot.tsx` |
| User Nonwear Markers | DONE | `components/activity-plot.tsx` |

### Metrics
| Feature | Status | Location |
|---------|--------|----------|
| Tudor-Locke Metrics Calculator | DONE | `services/metrics.py` |
| Metrics Panel (TST, WASO, SE, etc.) | DONE | `components/metrics-panel.tsx` |
| Per-Period Metrics Display | DONE | `components/metrics-panel.tsx` |

### Data Tables
| Feature | Status | Location |
|---------|--------|----------|
| Onset/Offset Data Tables | DONE | `components/marker-data-table.tsx` |
| Click-to-Move Timestamps | DONE | `components/marker-data-table.tsx` |
| Popout 48h Table Dialog | DONE | `components/popout-table-dialog.tsx` |

### Export
| Feature | Status | Location |
|---------|--------|----------|
| CSV Export | DONE | `services/export_service.py` |
| File Multi-Select | DONE | `pages/export.tsx` |
| Column Selection by Category | DONE | `pages/export.tsx` |
| Column Presets (minimal/standard/full) | DONE | `pages/export.tsx` |
| Date Range Filtering | DONE | `pages/export.tsx` + `api/export.py` |
| Export API | DONE | `api/export.py` |

### Diary Integration
| Feature | Status | Location |
|---------|--------|----------|
| Diary Entry CRUD | DONE | `api/diary.py` |
| Diary Panel Display | DONE | `components/diary-panel.tsx` |
| Diary CSV Upload | DONE | `api/diary.py` |
| Place Markers from Diary Times | DONE | `components/diary-panel.tsx` |

### Data Settings
| Feature | Status | Location |
|---------|--------|----------|
| Device Preset Selection | DONE | `pages/data-settings.tsx` |
| Skip Rows / Epoch Length | DONE | `pages/data-settings.tsx` |
| Settings Persistence (backend) | DONE | `api/settings.py` + `pages/data-settings.tsx` |
| Per-User Skip Rows Applied on Upload | DONE | `api/files.py` |

### Study Settings
| Feature | Status | Location |
|---------|--------|----------|
| Algorithm Selection | DONE | `pages/study-settings.tsx` |
| Sleep Detection Rule | DONE | `pages/study-settings.tsx` |
| Night Hours Configuration | DONE | `pages/study-settings.tsx` |
| Regex Patterns (persisted via extra_settings) | DONE | `pages/study-settings.tsx` |
| Settings Persistence (backend) | DONE | `api/settings.py` |

### UI/UX
| Feature | Status | Location |
|---------|--------|----------|
| Keyboard Shortcuts (Q/E/A/D, arrows, etc.) | DONE | `hooks/useKeyboardShortcuts.ts` |
| Color Legend Dialog | DONE | `components/color-legend-dialog.tsx` |
| Dark/Light Theme Toggle | DONE | `components/theme-toggle.tsx` |
| Responsive Layout | DONE | `components/layout.tsx` |

---

## E2E Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| `auth.spec.ts` | 5 | Configured |
| `scoring-page.spec.ts` | 10 | Configured |
| `settings-persistence.spec.ts` | 9 | Configured |
| `export.spec.ts` | 10 | Configured |
| `diary.spec.ts` | 9 | Configured |
| `metrics-panel.spec.ts` | 4 | Configured |
| `keyboard-shortcuts.spec.ts` | 10 | Configured |
| `marker-tables.spec.ts` | 8 | Configured |
| `nonwear-visualization.spec.ts` | 3 | Configured |
| `files.spec.ts` | 4 | Configured |
| `navigation.spec.ts` | 8 | Configured |
| **Total** | **78** | **Configured** |

---

## Running the Application

### Docker (Recommended)
```bash
cd docker
docker compose up -d

# Access:
# Frontend: http://localhost:8501
# Backend API: http://localhost:8500
# API Docs: http://localhost:8500/docs
```

### Running E2E Tests
```bash
cd frontend
npx playwright test
```

---

## Not Implemented (Gaps vs Desktop)

These features exist in the desktop PyQt6 application but are not in the web version:

| Feature | Notes |
|---------|-------|
| GT3X file support | Desktop supports raw GT3X via pygt3x; web is CSV/XLSX only |
| Van Hees 2015 SIB algorithm | Requires raw accelerometer data (GT3X prerequisite) |
| Raw accelerometer paradigm | Web only supports epoch-based data |
| Nonwear sensor data import | Desktop has separate NWT sensor import workflow |
| Participant groups/timepoints | Desktop persists valid groups/timepoints lists with drag-drop |
| Undo/redo (command pattern) | Desktop has PlaceMarker/MoveMarker/DeleteMarker commands |
| Multi-user consensus UI | Schema exists in DB but no UI for dispute resolution |
| Automated marker placement rules | Desktop has 8 rule-based placement algorithms with feature extraction |
| Batch scoring across files | Score one file at a time in web |
| Config import/export | Desktop can serialize/deserialize full study config |

---

## Known Issues

1. Frontend lint reports two non-blocking `react-hooks/exhaustive-deps` warnings in `src/components/activity-plot.tsx`.
2. Backend and desktop type checks are warning-only in several legacy paths; there are no current blocking type errors.

---

*Document maintained as part of sleep-scoring-demo project.*
