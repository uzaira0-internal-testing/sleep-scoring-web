# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

block_cipher = None

# Determine platform
is_windows = sys.platform.startswith('win')
is_macos = sys.platform.startswith('darwin')

# All modules that need to be included for sleep-scoring-demo
hidden_imports = [
    # Core Python libraries
    'sqlite3',
    'logging',
    'logging.handlers',
    'json',
    'pathlib',
    'threading',
    'contextlib',
    'functools',
    'typing',
    'dataclasses',
    'datetime',
    'sys',
    're',
    'os',
    'tempfile',
    'shutil',
    'csv',
    'weakref',
    'gc',
    'time',

    # PyQt6 modules
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.sip',
    'PyQt6.QtTest',
    'PyQt6.uic',
    'PyQt6.QtOpenGL',
    'PyQt6.QtNetwork',

    # Scientific computing
    'pandas',
    'pandas._libs',
    'pandas._libs.tslibs',
    'pandas._libs.interval',
    'pandas._libs.hashtable',
    'pandas._libs.algos',
    'pandas._libs.index',
    'pandas._libs.join',
    'pandas._libs.lib',
    'pandas._libs.missing',
    'pandas._libs.ops',
    'pandas._libs.ops_dispatch',
    'pandas._libs.reduction',
    'pandas._libs.reshape',
    'pandas._libs.sparse',
    'pandas._libs.testing',
    'pandas._libs.window',
    'pandas._libs.writers',
    'numpy',
    'numpy._core',
    'numpy._core._multiarray_umath',
    'numpy.linalg',
    'numpy.random',
    'numpy.fft',

    # PyQtGraph for plotting
    'pyqtgraph',
    'pyqtgraph.graphicsItems',
    'pyqtgraph.Qt',
    'pyqtgraph.Qt.QtCore',
    'pyqtgraph.Qt.QtGui',
    'pyqtgraph.Qt.QtWidgets',

    # Date/time handling
    'pytz',
    'dateutil',
    'dateutil.parser',
    'dateutil.tz',
    'dateutil.relativedelta',

    # Excel support
    'openpyxl',
    'openpyxl.styles',
    'openpyxl.formatting',
    'openpyxl.workbook',
    'openpyxl.worksheet',
    'xlsxwriter',

    # Application modules - core
    'sleep_scoring_app',
    'sleep_scoring_app.__main__',
    'sleep_scoring_app.main',
    'sleep_scoring_app.cli',
    'sleep_scoring_app.web',
    'sleep_scoring_app.core',
    'sleep_scoring_app.core.algorithms',
    'sleep_scoring_app.core.algorithms.types',
    'sleep_scoring_app.core.constants',
    'sleep_scoring_app.core.constants.algorithms',
    'sleep_scoring_app.core.constants.database',
    'sleep_scoring_app.core.constants.io',
    'sleep_scoring_app.core.constants.ui',
    'sleep_scoring_app.core.dataclasses',
    'sleep_scoring_app.core.exceptions',

    'sleep_scoring_app.core.validation',

    # Shared callback protocols
    'sleep_scoring_app.core.algorithms.protocols',
    'sleep_scoring_app.core.algorithms.protocols.callbacks',

    # Sleep/wake classification algorithms (protocol + factory colocated)
    'sleep_scoring_app.core.algorithms.sleep_wake',
    'sleep_scoring_app.core.algorithms.sleep_wake.protocol',
    'sleep_scoring_app.core.algorithms.sleep_wake.factory',
    'sleep_scoring_app.core.algorithms.sleep_wake.sadeh',
    'sleep_scoring_app.core.algorithms.sleep_wake.cole_kripke',
    'sleep_scoring_app.core.algorithms.sleep_wake.utils',

    # Nonwear detection algorithms (protocol + factory colocated)
    'sleep_scoring_app.core.algorithms.nonwear',
    'sleep_scoring_app.core.algorithms.nonwear.protocol',
    'sleep_scoring_app.core.algorithms.nonwear.factory',
    'sleep_scoring_app.core.algorithms.nonwear.choi',
    'sleep_scoring_app.core.algorithms.nonwear.van_hees',

    # Sleep period detection algorithms (protocol + factory colocated)
    'sleep_scoring_app.core.algorithms.sleep_period',
    'sleep_scoring_app.core.algorithms.sleep_period.protocol',
    'sleep_scoring_app.core.algorithms.sleep_period.factory',
    'sleep_scoring_app.core.algorithms.sleep_period.config',
    'sleep_scoring_app.core.algorithms.sleep_period.consecutive_epochs',

    # Application modules - data
    'sleep_scoring_app.data',
    'sleep_scoring_app.data.database',
    'sleep_scoring_app.data.database_schema',

    # IO modules - data loaders
    'sleep_scoring_app.io',
    'sleep_scoring_app.io.sources',
    'sleep_scoring_app.io.sources.csv_loader',
    'sleep_scoring_app.io.sources.gt3x_loader',
    'sleep_scoring_app.io.sources.loader_factory',
    'sleep_scoring_app.io.sources.loader_protocol',

    # Preprocessing modules
    'sleep_scoring_app.preprocessing',
    'sleep_scoring_app.preprocessing.calibration',
    'sleep_scoring_app.preprocessing.imputation',

    # Application modules - services
    'sleep_scoring_app.services',
    'sleep_scoring_app.services.batch_scoring_service',
    'sleep_scoring_app.services.data_service',
    'sleep_scoring_app.services.diary_mapper',
    'sleep_scoring_app.services.diary_service',
    'sleep_scoring_app.services.export_service',
    'sleep_scoring_app.services.format_detector',
    'sleep_scoring_app.services.import_service',
    'sleep_scoring_app.services.import_worker',
    'sleep_scoring_app.services.marker_service',
    'sleep_scoring_app.services.memory_service',
    'sleep_scoring_app.services.nonwear_import_worker',
    'sleep_scoring_app.services.nonwear_service',
    'sleep_scoring_app.services.nwt_correlation_service',
    'sleep_scoring_app.services.unified_data_service',

    # Application modules - ui
    'sleep_scoring_app.ui',
    'sleep_scoring_app.ui.main_window',
    'sleep_scoring_app.ui.analysis_tab',
    'sleep_scoring_app.ui.config_dialog',
    'sleep_scoring_app.ui.data_settings_tab',
    'sleep_scoring_app.ui.diary_integration',
    'sleep_scoring_app.ui.export_dialog',
    'sleep_scoring_app.ui.export_tab',
    'sleep_scoring_app.ui.file_navigation',
    'sleep_scoring_app.ui.column_selection_dialog',
    'sleep_scoring_app.ui.marker_table',
    'sleep_scoring_app.ui.study_settings_tab',
    'sleep_scoring_app.ui.time_fields',
    'sleep_scoring_app.ui.window_state',

    # Application modules - ui widgets
    'sleep_scoring_app.ui.widgets',
    'sleep_scoring_app.ui.widgets.activity_plot',
    'sleep_scoring_app.ui.widgets.analysis_dialogs',
    'sleep_scoring_app.ui.widgets.file_selection_table',
    'sleep_scoring_app.ui.widgets.plot_algorithm_manager',
    'sleep_scoring_app.ui.widgets.plot_data_manager',
    'sleep_scoring_app.ui.widgets.plot_marker_renderer',
    'sleep_scoring_app.ui.widgets.plot_overlay_renderer',
    'sleep_scoring_app.ui.widgets.plot_state_manager',
    'sleep_scoring_app.ui.widgets.plot_state_serializer',
    'sleep_scoring_app.ui.widgets.popout_table_window',

    # Application modules - utils
    'sleep_scoring_app.utils',
    'sleep_scoring_app.utils.column_registry',
    'sleep_scoring_app.utils.config',
    'sleep_scoring_app.utils.participant_extractor',
    'sleep_scoring_app.utils.resource_resolver',
    'sleep_scoring_app.utils.table_helpers',
    'sleep_scoring_app.utils.thread_safety',

    # Platform-specific modules that PyInstaller might miss
    'platform',
    'locale',
    'encodings',
    'encodings.utf_8',
    'encodings.cp1252',
    'encodings.latin1',

    # Import hooks and utilities
    'importlib',
    'importlib.util',
    'importlib.metadata',
]


# Initialize datas list

datas = []
# Add demo data folder to bundle
demo_path = Path('demo_data')
if demo_path.exists():
    datas.append((str(demo_path), 'demo_data'))


# Add Qt platform plugins
import PyQt6
qt_path = Path(PyQt6.__file__).parent
qt_plugins_path = qt_path / 'Qt6' / 'plugins'
if qt_plugins_path.exists():
    if (qt_plugins_path / 'platforms').exists():
        datas.append((str(qt_plugins_path / 'platforms'), 'PyQt6/Qt6/plugins/platforms'))
    if (qt_plugins_path / 'imageformats').exists():
        datas.append((str(qt_plugins_path / 'imageformats'), 'PyQt6/Qt6/plugins/imageformats'))
    if (qt_plugins_path / 'styles').exists():
        datas.append((str(qt_plugins_path / 'styles'), 'PyQt6/Qt6/plugins/styles'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports + ['scipy'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        '_tkinter', 'tcl', 'tk', 'tkinter',
        'IPython', 'jupyter',
        # Exclude PyQt5 to avoid conflicts with PyQt6
        'PyQt5', 'PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets',
        'PyQt5.uic', 'PyQt5.QtTest', 'PyQt5.QtOpenGL', 'PyQt5.QtNetwork',
        # Exclude matplotlib backends that might pull in PyQt5
        'matplotlib.backends.backend_qt5agg',
        'matplotlib.backends.qt5_compat',
        'matplotlib.backends.backend_qt5',
        'matplotlib.backends._backend_qt5',
        # Exclude scipy to reduce size
        # 'scipy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
    compress=True
)

# Windows EXE configuration
if is_windows:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='sleep-scoring-demo',
        debug=True,
        bootloader_ignore_signals=True,
        strip=False,
        upx=False,
        upx_exclude=['vcruntime140.dll', 'python*.dll', '*.pyd'],
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon='sleep_scoring_app/ui/resources/icon.ico' if Path('sleep_scoring_app/ui/resources/icon.ico').exists() else None,
        uac_admin=False,
        version='version_info.txt' if Path('version_info.txt').exists() else None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=['vcruntime140.dll', 'python*.dll', '*.pyd'],
        name='sleep-scoring-demo',
    )

# macOS App configuration
if is_macos:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='sleep-scoring-demo',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon='sleep_scoring_app/ui/resources/icon.icns' if Path('sleep_scoring_app/ui/resources/icon.icns').exists() else None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        name='sleep-scoring-demo',
    )

    app = BUNDLE(
        coll,
        name='Sleep Scoring Demo.app',
        icon='sleep_scoring_app/ui/resources/icon.icns' if Path('sleep_scoring_app/ui/resources/icon.icns').exists() else None,
        bundle_identifier='com.sleepresearch.sleepscoringdemo',
        info_plist={
            'NSPrincipalClass': 'NSApplication',
            'NSAppleScriptEnabled': False,
            'NSHighResolutionCapable': True,
            'CFBundleDisplayName': 'Sleep Scoring Demo',
            'CFBundleName': 'Sleep Scoring Demo',
            'CFBundleShortVersionString': '0.1.0',
            'CFBundleVersion': '0.1.0',
            'LSMinimumSystemVersion': '10.13',
            'NSRequiresAquaSystemAppearance': False,
        },
    )
