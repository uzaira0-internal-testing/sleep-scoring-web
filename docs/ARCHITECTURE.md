# Sleep Scoring App Architecture

## Overview

**Application**: PyQt6 desktop application for visual sleep scoring of accelerometer data
**Codebase Stats**: 191 Python files, 66,331 lines of code
**Architecture Grade**: A+ (zero layer violations)

---

## Layered Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  UI Layer (PyQt6)                          14,457 lines     │
│  ├── Widgets (dumb, emit signals only)                      │
│  ├── Connectors (subscribe to store, update widgets)        │
│  └── Coordinators (QTimer, QThread - Qt glue only)          │
├─────────────────────────────────────────────────────────────┤
│  Redux Store (Single Source of Truth)       1,231 lines     │
│  └── Actions → Reducer → State → Subscribers                │
├─────────────────────────────────────────────────────────────┤
│  Services Layer (Headless, no Qt)           9,836 lines     │
│  ├── FileService, MarkerService, DiaryService               │
│  └── Use callbacks, not signals                             │
├─────────────────────────────────────────────────────────────┤
│  Data Layer (Database/Repositories)         5,850 lines     │
│  ├── DatabaseManager, SchemaManager                         │
│  └── Repository pattern for CRUD                            │
├─────────────────────────────────────────────────────────────┤
│  Core Layer (Pure domain logic)             9,000 lines     │
│  ├── Algorithms, Constants, Dataclasses                     │
│  └── No imports from UI or Services                         │
├─────────────────────────────────────────────────────────────┤
│  IO Layer (Unified sources/)                2,099 lines     │
│  └── CSV/GT3X loaders with DatabaseColumn enum              │
└─────────────────────────────────────────────────────────────┘
```

---

## Layer Rules

### 1. UI Layer (`ui/`)
- **Widgets are DUMB**: Emit signals only, no direct service calls
- **Connectors bridge Widget ↔ Store**: Subscribe to state, update widgets
- **Coordinators for Qt glue only**: QTimer, QThread, QSettings mechanics
- **No business logic**: All logic goes through store dispatch or services

### 2. Redux Store (`ui/store.py`)
- **Single source of truth**: All UI state in frozen `UIState` dataclass
- **Actions are frozen dataclasses**: Immutable state changes
- **Pure reducer function**: `ui_reducer(state, action) -> state`
- **Subscribers notified**: Connectors listen for state changes

### 3. Services Layer (`services/`)
- **Headless**: NO PyQt6 imports whatsoever
- **Testable without Qt**: Pure Python, dependency injection
- **Callbacks over signals**: Use function callbacks, not Qt signals
- **Single responsibility**: Each service handles one domain

### 4. Data Layer (`data/`)
- **Repository pattern**: One repository per entity type
- **DatabaseManager facade**: High-level API, delegates to repositories
- **Migrations managed**: Numbered migrations in `migrations_registry.py`

### 5. Core Layer (`core/`)
- **Pure domain logic**: Algorithms, dataclasses, constants
- **No external dependencies**: No UI, no Services, no Data imports
- **StrEnums for constants**: All string constants are StrEnums
- **Frozen dataclasses for configs**: Immutable configuration objects

### 6. IO Layer (`io/sources/`)
- **Unified loaders**: Factory pattern for CSV/GT3X loading
- **Protocol-based**: `DataSourceLoader` protocol for all loaders
- **DatabaseColumn enum**: Consistent column naming

---

## Key Patterns

### Redux Pattern (UI State)
```python
# Store dispatches action
store.dispatch(Actions.file_selected(filename))

# Reducer produces new state
def ui_reducer(state: UIState, action: Action) -> UIState:
    if action.type == ActionType.FILE_SELECTED:
        return replace(state, current_file=action.payload)
    return state

# Connector subscribes and updates widget
class FileConnector:
    def __init__(self, store, widget):
        store.subscribe(self._on_state_change)

    def _on_state_change(self, old, new):
        if old.current_file != new.current_file:
            self.widget.setCurrentFile(new.current_file)
```

### Factory Pattern (Algorithms)
```python
from sleep_scoring_app.core.algorithms import AlgorithmFactory

algorithm = AlgorithmFactory.create(AlgorithmType.SADEH_1994_ACTILIFE)
results = algorithm.score(activity_data)
```

### Repository Pattern (Data)
```python
from sleep_scoring_app.data import DatabaseManager

db = DatabaseManager(path)
metrics = db.get_sleep_metrics_by_filename_and_date(filename, date)
```

### Protocol Pattern (Interfaces)
```python
from sleep_scoring_app.ui.protocols import MainWindowProtocol

class MyConnector:
    def __init__(self, main_window: MainWindowProtocol):
        # Protocol guarantees these attributes exist
        main_window.plot_widget.clear()
```

---

## Directory Structure

```
sleep_scoring_app/
├── core/                    # Pure domain logic (NO external deps)
│   ├── algorithms/          # Sleep/wake, nonwear, sleep period algorithms
│   │   ├── sleep_wake/      # Sadeh, Cole-Kripke
│   │   ├── nonwear/         # Choi algorithm
│   │   └── sleep_period/    # Sleep period detection
│   ├── backends/            # GT3X loading backends
│   ├── constants/           # ALL StrEnums (algorithms, database, io, ui)
│   ├── markers/             # Marker persistence protocols
│   ├── pipeline/            # Processing pipeline orchestration
│   └── dataclasses*.py      # Domain dataclasses (5 files)
│
├── data/                    # Database layer
│   ├── repositories/        # CRUD operations per entity
│   ├── database.py          # DatabaseManager facade
│   ├── database_schema.py   # Schema definitions
│   └── migrations*.py       # Migration management
│
├── io/                      # File loading
│   └── sources/             # CSV, GT3X loaders with factory
│
├── preprocessing/           # Data preprocessing
│   ├── calibration.py       # Accelerometer calibration
│   └── imputation.py        # Gap imputation
│
├── services/                # Business logic (HEADLESS - no Qt)
│   ├── diary/               # Diary subsystem
│   ├── export_service.py    # CSV/Excel export
│   ├── import_service.py    # File import
│   ├── marker_service.py    # Marker CRUD
│   └── ...                  # 20+ service files
│
├── ui/                      # PyQt6 UI layer
│   ├── builders/            # UI construction helpers
│   ├── commands/            # Undo/redo command pattern
│   ├── connectors/          # Store ↔ Widget bridges (planned)
│   ├── coordinators/        # QTimer/QThread glue
│   ├── dialogs/             # Dialog windows
│   ├── widgets/             # Custom widgets
│   ├── workers/             # QThread workers
│   ├── store.py             # Redux store + Actions
│   ├── connectors/          # Store connectors (Redux pattern)
│   ├── main_window.py       # Main application window
│   └── protocols.py         # UI protocols
│
├── utils/                   # Pure Python utilities
│   └── registries/          # Column registries
│
└── web/                     # Web API placeholder (future)
```

---

## Coding Standards (Mandatory)

### 1. StrEnums for ALL String Constants
```python
# CORRECT
from sleep_scoring_app.core.constants import AlgorithmType
algorithm = AlgorithmType.SADEH_1994_ACTILIFE

# WRONG
algorithm = "sadeh_1994"  # NO magic strings
```

### 2. Frozen Dataclasses for Configs
```python
@dataclass(frozen=True)
class AlgorithmConfig:
    threshold: float = 0.5
```

### 3. Type Annotations on All Functions
```python
def calculate_metrics(
    period: SleepPeriod,
    results: list[int],
) -> SleepMetrics | None:
    ...
```

### 4. No hasattr() Abuse
```python
# WRONG - hiding init bugs
if hasattr(self.parent, "plot_widget"):
    self.parent.plot_widget.clear()

# CORRECT - Protocol guarantees
self.parent.plot_widget.clear()
```

### 5. No Backwards Compatibility Shims
```python
# When refactoring:
# - DELETE old code completely
# - NO deprecated wrappers
# - UPDATE all imports
# - GREP for old names
```

---

## File Statistics

| Layer | Files | Lines | % of Codebase |
|-------|-------|-------|---------------|
| UI | 51 | 14,457 | 22% |
| Services | 29 | 11,145 | 17% |
| Core | 50 | 9,000 | 14% |
| Data | 14 | 5,850 | 9% |
| IO | 7 | 2,099 | 3% |
| Utils | 19 | 3,927 | 6% |
| Other | 21 | 19,853 | 30% |
| **Total** | **191** | **66,331** | 100% |

---

## See Also

- [FILE_INVENTORY.md](./FILE_INVENTORY.md) - Complete file listing
- [CLAUDE.md](../CLAUDE.md) - Coding standards and rules
