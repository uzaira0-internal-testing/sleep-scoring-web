# Sleep Scoring App - File Inventory

Complete listing of all Python files organized by architectural layer.

---

## Core Layer (`core/`) - 50 files, ~9,000 lines

### Root Files
| File | Lines | Purpose | Key Exports |
|------|-------|---------|-------------|
| `__init__.py` | 10 | Package init | - |
| `dataclasses.py` | 500 | Main dataclasses | `AppConfig`, `FileInfo`, `ParticipantInfo` |
| `dataclasses_analysis.py` | 183 | Analysis data | `AlignedActivityData`, `AlgorithmDataset` |
| `dataclasses_config.py` | 419 | Config objects | `ColumnMapping`, `ActiLifeSadehConfig` |
| `dataclasses_daily.py` | 314 | Daily containers | `DailyData`, `ParticipantData`, `StudyData` |
| `dataclasses_diary.py` | 325 | Diary data | `DiaryEntry`, `DiaryImportResult` |
| `dataclasses_markers.py` | 687 | Marker data | `SleepPeriod`, `DailySleepMarkers`, `DailyNonwearMarkers` |
| `exceptions.py` | 125 | Custom exceptions | `ValidationError`, `DatabaseError` |
| `nonwear_data.py` | 238 | Nonwear containers | `NonwearData`, `NonwearDataFactory` |
| `validation.py` | 478 | Input validation | `InputValidator` |

### Constants (`core/constants/`) - 5 files
| File | Lines | Purpose | Key Exports |
|------|-------|---------|-------------|
| `__init__.py` | 210 | Re-exports | All constants |
| `algorithms.py` | 335 | Algorithm enums | `AlgorithmType`, `NonwearAlgorithm`, `SleepPeriodDetectorType` |
| `database.py` | 173 | Database enums | `DatabaseTable`, `DatabaseColumn` |
| `io.py` | 339 | IO enums | `ImportStatus`, `FileSourceType`, `ExportColumn` |
| `ui.py` | 732 | UI enums | `FeatureFlags`, `TimeFormat`, `PlotConstants`, `UIColors` |

### Algorithms (`core/algorithms/`) - 21 files
| Directory | Files | Purpose |
|-----------|-------|---------|
| `sleep_wake/` | 6 | Sadeh, Cole-Kripke algorithms |
| `nonwear/` | 4 | Choi nonwear detection |
| `sleep_period/` | 6 | Sleep period detection |
| `protocols/` | 2 | Callback protocols |
| Root | 3 | Compatibility, types |

### Backends (`core/backends/`) - 7 files
| File | Lines | Purpose |
|------|-------|---------|
| `gt3x_rs_backend.py` | 663 | Rust-based GT3X loader |
| `pygt3x_backend.py` | 532 | Pure Python GT3X loader |
| `factory.py` | 374 | Backend factory |
| `protocol.py` | 533 | ComputeBackend protocol |
| `data_types.py` | 282 | Backend data types |
| `capabilities.py` | 165 | Backend capabilities |

### Markers (`core/markers/`) - 3 files
| File | Lines | Purpose |
|------|-------|---------|
| `persistence.py` | 430 | JSON serialization |
| `protocol.py` | 337 | Marker protocols |

### Pipeline (`core/pipeline/`) - 5 files
| File | Lines | Purpose |
|------|-------|---------|
| `orchestrator.py` | 434 | Pipeline orchestration |
| `detector.py` | 408 | Data source detection |
| `types.py` | 186 | Pipeline types |
| `exceptions.py` | 229 | Pipeline exceptions |

---

## Services Layer (`services/`) - 29 files, ~11,000 lines

### Main Services
| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `export_service.py` | 1,044 | CSV/Excel export | OK |
| `diary_mapper.py` | 991 | Diary column mapping | OK |
| `import_service.py` | 773 | File import orchestration | OK |
| `batch_scoring_service.py` | 671 | Batch processing | OK |
| `marker_service.py` | 650 | Marker CRUD | OK |
| `data_loading_service.py` | 644 | Data loading | OK |
| `memory_service.py` | 489 | Memory monitoring | OK |
| `nonwear_service.py` | 425 | Nonwear operations | OK |
| `metrics_calculation_service.py` | 381 | Sleep metrics | OK |
| `cache_service.py` | 379 | Data caching | OK |
| `csv_data_transformer.py` | 365 | CSV transformation | OK |
| `format_detector.py` | 296 | Format detection | OK |
| `algorithm_service.py` | 275 | Algorithm factory wrapper | OK |
| `epoching_service.py` | 263 | Epoch conversion | OK |
| `unified_data_service.py` | 243 | Unified data access | OK |
| `data_service.py` | 246 | Legacy data service | OK |
| `file_service.py` | 240 | File operations | OK |
| `pattern_validation_service.py` | 218 | Pattern validation | OK |
| `import_progress_tracker.py` | 180 | Progress tracking | OK |
| `file_format_detector.py` | 165 | Format detection | OK |
| `diary_service.py` | 158 | Diary service | OK |
| `data_query_service.py` | 103 | Data queries | OK |
| `protocols.py` | 561 | Service protocols | OK |

### Diary Subsystem (`services/diary/`) - 5 files
| File | Lines | Purpose |
|------|-------|---------|
| `import_orchestrator.py` | 627 | Diary import |
| `data_extractor.py` | 389 | Diary extraction |
| `query_service.py` | 239 | Diary queries |
| `progress.py` | 41 | Import progress |

---

## Data Layer (`data/`) - 14 files, ~5,850 lines

### Database Management
| File | Lines | Purpose |
|------|-------|---------|
| `database_schema.py` | 735 | Schema definitions |
| `migrations_registry.py` | 649 | Migration scripts (5 migrations) |
| `database.py` | 589 | DatabaseManager facade |
| `migrations.py` | 327 | Migration runner |
| `migration_cli.py` | 168 | CLI commands |
| `config.py` | 17 | DB config |

### Repositories (`data/repositories/`) - 7 files
| File | Lines | Purpose |
|------|-------|---------|
| `sleep_metrics_repository.py` | 625 | Metrics CRUD |
| `file_registry_repository.py` | 514 | File registry |
| `diary_repository.py` | 382 | Diary CRUD |
| `nonwear_repository.py` | 316 | Nonwear CRUD |
| `activity_data_repository.py` | 275 | Activity data |
| `base_repository.py` | 246 | Base class |

---

## IO Layer (`io/sources/`) - 7 files, ~2,100 lines

| File | Lines | Purpose |
|------|-------|---------|
| `csv_loader.py` | 529 | CSV loading |
| `gt3x_loader.py` | 567 | GT3X loading (pygt3x) |
| `gt3x_rs_loader.py` | 467 | GT3X loading (Rust) |
| `loader_factory.py` | 350 | Loader factory |
| `loader_protocol.py` | 178 | Loader protocol |

---

## UI Layer (`ui/`) - 51 files, ~14,500 lines

### Main UI Files
| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `connectors/` | 12 files | Store/widget connector modules | COMPLETED |
| `main_window.py` | 2,367 | Main window | OK |
| `study_settings_tab.py` | 1,505 | Study settings | OK |
| `analysis_tab.py` | 1,471 | Analysis tab | OK |
| `data_settings_tab.py` | 1,332 | Data settings | OK |
| `store.py` | 1,231 | Redux store | OK |
| `window_state.py` | 703 | Window state | OK |
| `config_dialog.py` | 613 | Config dialog | OK |
| `marker_table.py` | 608 | Marker table | OK |
| `algorithm_compatibility_ui.py` | 405 | Algorithm UI | OK |
| `protocols.py` | 348 | UI protocols | OK |
| `export_tab.py` | 340 | Export tab | OK |
| `export_dialog.py` | 284 | Export dialog | OK |
| `shortcut_manager.py` | 203 | Shortcuts | OK |
| `file_navigation.py` | 180 | File nav | OK |
| `column_selection_dialog.py` | 142 | Column dialog | OK |

### Widgets (`ui/widgets/`) - 16 files
| File | Lines | Purpose |
|------|-------|---------|
| `activity_plot.py` | 2,169 | Main plot widget |
| `plot_marker_renderer.py` | 1,287 | Marker rendering |
| `plot_algorithm_manager.py` | 644 | Algorithm display |
| `analysis_dialogs.py` | 589 | Analysis dialogs |
| `plot_overlay_renderer.py` | 553 | Overlay rendering |
| `plot_state_serializer.py` | 507 | State serialization |
| `marker_interaction_handler.py` | 379 | Marker interactions |
| `file_selection_table.py` | 363 | File table |
| `plot_state_manager.py` | 262 | Plot state |
| `popout_table_window.py` | 226 | Popout windows |
| `plot_data_manager.py` | 219 | Plot data |
| `marker_drawing_strategy.py` | 206 | Drawing strategy |
| `marker_editor.py` | 131 | Marker editing |
| `file_management_widget.py` | 106 | File management |
| `drag_drop_list.py` | 82 | Drag/drop widget |

### Coordinators (`ui/coordinators/`) - 10 files
| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `diary_integration_manager.py` | 620 | Diary integration | RENAME to Coordinator |
| `import_ui_coordinator.py` | 575 | Import UI | OK |
| `autosave_coordinator.py` | 438 | Autosave | OK |
| `session_state_manager.py` | 367 | Session state | MOVE to services/ |
| `seamless_source_switcher.py` | 340 | Source switching | OK |
| `diary_table_manager.py` | 253 | Diary table | RENAME to Connector |
| `marker_loading_coordinator.py` | 147 | Marker loading | OK |
| `time_field_manager.py` | 133 | Time field | RENAME to Coordinator |
| `ui_state_coordinator.py` | 75 | UI state | OK |

### Builders (`ui/builders/`) - 9 files
| File | Lines | Purpose |
|------|-------|---------|
| `file_column_mapping_builder.py` | 529 | Column mapping |
| `valid_values_builder.py` | 439 | Valid values |
| `algorithm_section_builder.py` | 417 | Algorithm section |
| `data_source_config_builder.py` | 263 | Data source config |
| `pattern_section_builder.py` | 230 | Pattern section |
| `import_settings_builder.py` | 209 | Import settings |
| `data_paradigm_builder.py` | 199 | Data paradigm |
| `activity_preferences_builder.py` | 164 | Activity prefs |

### Dialogs (`ui/dialogs/`) - 3 files
| File | Lines | Purpose |
|------|-------|---------|
| `column_mapping_dialog.py` | 474 | Column mapping |
| `delete_file_dialog.py` | 128 | Delete confirmation |

### Workers (`ui/workers/`) - 3 files
| File | Lines | Purpose |
|------|-------|---------|
| `import_worker.py` | 176 | Import QThread |
| `nonwear_import_worker.py` | 133 | Nonwear QThread |

### Commands (`ui/commands/`) - 3 files
| File | Lines | Purpose |
|------|-------|---------|
| `marker_commands.py` | 157 | Marker undo/redo |
| `base.py` | 70 | Command base class |

### Constants (`ui/constants/`) - 1 file
| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `__init__.py` | 95 | Re-exports | DELETE (backwards compat) |

---

## Utils Layer (`utils/`) - 19 files, ~3,900 lines

### Pure Python Utils (Keep in utils/)
| File | Lines | Purpose | Has Qt? |
|------|-------|---------|---------|
| `calculations.py` | 101 | Math calculations | NO |
| `date_range.py` | 174 | Date utilities | NO |
| `participant_extractor.py` | 215 | ID extraction | NO |
| `resource_resolver.py` | 191 | Path resolution | NO |
| `profiling.py` | 265 | Performance | NO |
| `column_registry.py` | 176 | Column registry | NO |
| `config_builder.py` | 368 | Config building | NO |

### Qt-Dependent Utils (Move to ui/utils/)
| File | Lines | Purpose | Has Qt? |
|------|-------|---------|---------|
| `config.py` | 710 | ConfigManager | YES (QSettings) |
| `table_helpers.py` | 571 | Table utilities | YES (QTableWidget) |
| `thread_safety.py` | 72 | Thread safety | YES (QThread) |
| `qt_context_managers.py` | 63 | Qt contexts | YES (QWidget) |

### Registries (`utils/registries/`) - 7 files
| File | Lines | Purpose |
|------|-------|---------|
| `diary_columns.py` | 284 | Diary columns |
| `activity_columns.py` | 208 | Activity columns |
| `sleep_columns.py` | 164 | Sleep columns |
| `metadata_columns.py` | 157 | Metadata columns |
| `nonwear_columns.py` | 94 | Nonwear columns |
| `marker_columns.py` | 73 | Marker columns |

---

## Other

### Preprocessing (`preprocessing/`) - 3 files
| File | Lines | Purpose |
|------|-------|---------|
| `calibration.py` | 323 | Accelerometer calibration |
| `imputation.py` | 199 | Gap imputation |

### CLI (`cli/`) - 1 file
| File | Lines | Purpose |
|------|-------|---------|
| `__init__.py` | 29 | CLI stub |

### Web (`web/`) - 1 file
| File | Lines | Purpose | Status |
|------|-------|---------|--------|
| `__init__.py` | 42 | Flask placeholder | KEEP (future) |

### Root Files
| File | Lines | Purpose |
|------|-------|---------|
| `main.py` | 106 | Entry point |
| `app_bootstrap.py` | 46 | Logging setup |
| `__main__.py` | 41 | Module entry |

---

## Action Items Summary

| Item | Location | Action |
|------|----------|--------|
| `ui/connectors/` split | ui/ | COMPLETED |
| Coordinator renames (`diary_table_connector.py`, `time_field_coordinator.py`, `diary_integration_coordinator.py`) | ui/coordinators/ | COMPLETED |
| Qt utility moves (`config.py`, `table_helpers.py`, `thread_safety.py`, `qt_context_managers.py`) | ui/utils/ | COMPLETED |
| Keep inventory in sync with tree state | docs/ | ONGOING |
