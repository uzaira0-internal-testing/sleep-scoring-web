# Sleep Scoring App Demo

![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)
![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)
![Status: Beta](https://img.shields.io/badge/Status-Beta-yellow.svg)

## Overview

This visual sleep scoring application was originally developed internally by the P01HD109876 Digital Assessment Core to implement a user-friendly, semi-automated, and replicable version of a manual sleep scoring workflow for sleep and nap scoring of actigraphy data from a 3-5 year old sample. It is in the process of being updated to include additional features for different kinds of sleep scoring workflows. It has also been preliminarily validated for interrater, metric, and algorithmic reliability. **Although this is a "demo" repository of the application with synthetic data, it has full functionality if your manual sleep scoring workflow is similar.** For more general workflows, there will be future releases soon. Please contact at uzair.alam@bcm.edu if you have any questions.

## Features

- **Actigraphy Visualization**: Interactive time-series plots with zoom and pan and different axes
- **Semi-Automated Sleep Scoring**: Apply Sadeh algorithm for sleep/wake classification and onset/offset rules for assistance
- **Nonwear Detection**: Visualize periods when the device was possibly not worn (Choi algorithm, nonwear sensor data)
- **Interactive Markers**: Place and adjust sleep onset/offset markers with mouse
- **Sleep Diary Integration**: Import and visualize sleep diary data alongside actigraphy
- **Multi-Participant Support**: Manage multiple participants and files
- **Data Export**: Export results to CSV with customizable columns
- **Secure Storage**: SQLite file database that can be easily backed up or shared

## Installation

### Requirements

- Windows, macOS, or Linux (with Python 3.12+)

### Running the Application

**Running as Executable on Windows/macOS**: Download the latest release from the [GitHub releases page](https://github.com/uzaira0/sleep-scoring-demo/releases) and run the executable.

**Running from CLI on Linux/Windows/macOS**: `uv run python -m sleep_scoring_app`

### Demo Data

Sample data is included in the `demo_data/` folder for testing the application.

### Demo Start

1. **Load Data**: The Study Settings tab is already set up for the demo, so use the Data Settings tab to import any of the actigraphy CSV files, nonwear file, and diary file
2. **View Activity**: Go to the analysis tab, and click on the loaded file in the table. The main plot will update and show activity counts over time. You can adjust which axis/VM is displayed, or adjust between 24 and 48 hour views. Choi algorithm nonwear is shown as purple, nonwear time sensor nonwear is shown as orange, and their overlap is shown as blue.
3. **Place Primary Sleep Markers**: Click twice on the plot to place sleep onset (blue) and offset (orange) markers, or you can click on the diary onset or offset for it to place the markers for you.
4. **Move Markers to Arrows**: Arrows are shown to guide you to the closest series which matches the 3/5 minute sleep scoring rules for onset and offset, and you can drag the markers or **right** click on the left and right table rows to jump to them.
4. **Place and Move Nap Markers if Appropriate**: Some days will have naps in the diary, if valid you can click twice on the plot after placing main sleep markers or click the diary nap onset or offset to place a nap.
5. **Save Markers**: Click "Save Markers" to save markers, or you will be prompted to save before proceeding to the next date.
6. **Finish Scoring and Export**: Continue until you are finished scoring, then go to the export tab. You can export all of your results here.

The scored sleep data is saved as CSV with all metrics including:
- Sleep onset/offset times
- Total time in bed
- Total sleep time
- Sleep efficiency
- Wake after sleep onset (WASO)
- Number of awakenings
- Nonwear overlap information

## Configuration

### Settings

Application settings are managed through the Study Settings tab:
- Algorithm parameters (Sadeh threshold, Choi axis)
- Export preferences

Data import settings are managed in the Data Settings tab:
- Specify columns for date and/or time, which columns to use for each axis, etc.
- Import manual nonwear sensor data with specific column format if available
- Import sleep diary data with specific column format if available

## Sleep/Wake Algorithm/Rule References

### Sadeh Algorithm
> Sadeh, A., Sharkey, K. M., & Carskadon, M. A. (1994). Activity-based sleep-wake identification: An empirical test of methodological issues. *Sleep*, 17(3), 201-207.

> [ActiLife Implementation](https://actigraphcorp.my.site.com/support/s/article/Where-can-I-find-documentation-for-the-Sadeh-and-Cole-Kripke-algorithms)

The Sadeh algorithm uses an 11-minute sliding window to classify each epoch as sleep or wake based on activity counts. A score > threshold indicates sleep. Both the original (threshold = 0) and ActiLife (threshold = -4) implementations are supported.

### Choi Nonwear Algorithm
> Choi, L., Liu, Z., Matthews, C. E., & Buchowski, M. S. (2011). Validation of accelerometer wear and nonwear time classification algorithm. *Medicine and Science in Sports and Exercise*, 43(2), 357-364.

The Choi algorithm detects nonwear periods by identifying consecutive epochs with zero activity counts, allowing for small spikes within the window. The newest version of the Choi algorithm is used.

### Tudor-Locke Sleep Period Detection and Metrics
> Tudor-Locke, C., et al. (2014). Fully automated waist-worn accelerometer algorithm for detecting children's sleep-period time. *Applied Physiology, Nutrition, and Metabolism*, 39(1), 53-57.

The Tudor-Locke algorithm detects sleep period boundaries (onset/offset) using consecutive epoch rules, then calculates comprehensive sleep quality metrics including sleep efficiency, fragmentation indices, and awakening statistics.

### Cole-Kripke Algorithm


## Project Structure

```
sleep_scoring_app/
├── core/           # Core algorithms and business logic
├── data/           # Database and data access layer
├── services/       # Business services (import, export, etc.)
├── ui/             # PyQt6 user interface components
└── utils/          # Configuration and utilities
```

## License

This project is licensed under the GPL-3.0 License - see the [LICENSE](LICENSE) file for details.

# Disclaimer

Not affiliated with Ametris/ActiGraph.
