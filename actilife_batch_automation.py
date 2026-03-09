#!/usr/bin/env python3

import time
from enum import StrEnum
from pathlib import Path

import keyboard
import pyautogui
import pygetwindow as gw


class SleepAlgorithm(StrEnum):
    """Supported sleep scoring algorithms."""

    SADEH = "sadeh"
    COLE_KRIPKE = "cole-kripke"


class ActiLifeBatchAutomation:
    """Automates ActiLife GUI operations."""

    def __init__(self, algorithm: SleepAlgorithm = SleepAlgorithm.SADEH) -> None:
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.25
        self.screenshots_dir = Path("screenshots")
        self.screenshots_dir.mkdir(exist_ok=True)

        # Store selected algorithm
        self.algorithm = algorithm
        self.algorithm_display_name = "Sadeh" if algorithm == SleepAlgorithm.SADEH else "Cole-Kripke"

        # Set up button images folder
        self.button_images_dir = Path("buttons")
        if not self.button_images_dir.exists():
            pass

        # Emergency stop functionality
        self.should_stop = False
        self.setup_emergency_stop()

    def setup_emergency_stop(self):
        """Set up emergency stop hotkeys and monitoring."""

        # Set up global hotkey listener
        def on_emergency_hotkey():
            self.should_stop = True

        try:
            # Register Ctrl+Shift+Q as emergency stop
            keyboard.add_hotkey("ctrl+shift+q", on_emergency_hotkey)
        except Exception as e:
            pass

    def check_emergency_stop(self):
        """Check if emergency stop has been triggered."""
        if self.should_stop:
            return True

        # Check for bottom-right corner failsafe (custom)
        x, y = pyautogui.position()
        screen_width, screen_height = pyautogui.size()

        # If mouse is in bottom-right corner (within 10 pixels)
        if x >= screen_width - 10 and y >= screen_height - 10:
            return True

        return False

    def find_actilife_window(self):
        """Find and activate ActiLife window."""
        try:
            windows = gw.getWindowsWithTitle("ActiLife")
            if not windows:
                return False

            window = windows[0]
            if window.isMinimized:
                window.restore()
            window.activate()
            time.sleep(1)
            return True
        except Exception as e:
            return False

    def get_agd_files(self, folder_path, output_folder=None):
        """Get list of AGD files from folder (recursive), excluding those already processed."""
        folder = Path(folder_path)
        if not folder.exists():
            return []

        # Determine output folder (default to same as input folder)
        if output_folder is None:
            output_folder = folder
        else:
            output_folder = Path(output_folder)
            if not output_folder.exists():
                return []

        # Recursively find all AGD files
        agd_files = list(folder.rglob("*.agd"))
        if not agd_files:
            return []

        # Check which files need processing
        files_to_process = []
        skipped_files = []

        for agd_file in agd_files:
            # Generate expected output filename based on selected algorithm
            base_name = agd_file.stem
            output_filename = f"{base_name} {self.algorithm_display_name} Sleep Epochs.csv"
            output_path = output_folder / output_filename

            # Show relative path for files in subfolders
            try:
                rel_path = agd_file.relative_to(folder)
            except ValueError:
                rel_path = agd_file.name

            if output_path.exists():
                skipped_files.append(str(agd_file))
            else:
                files_to_process.append(str(agd_file))

        if skipped_files:
            pass

        return files_to_process

    def click_element(self, image_file, description, confidence=0.8):
        """Click an element using image recognition."""
        # Check for emergency stop before each action
        if self.check_emergency_stop():
            return False

        try:
            image_path = self.button_images_dir / image_file
            if not image_path.exists():
                return False

            element = pyautogui.locateOnScreen(str(image_path), confidence=confidence)
            if element:
                pyautogui.click(pyautogui.center(element))
                return True
            return False
        except Exception as e:
            return False

    def type_filename(self, image_file, filename, description):
        """Type filename in a field."""
        try:
            image_path = self.button_images_dir / image_file
            if not image_path.exists():
                return False

            field = pyautogui.locateOnScreen(str(image_path), confidence=0.8)
            if field:
                pyautogui.click(pyautogui.center(field))
                time.sleep(0.25)
                pyautogui.hotkey("ctrl", "a")  # Select all
                pyautogui.typewrite(filename)
                return True
            return False
        except Exception as e:
            return False

    def select_dataset(self, filename):
        """Step 1 & 2: Click Select dataset and type filename."""
        # Click Select dataset button
        if not self.click_element("select_dataset_btn.png", "Select dataset button"):
            return False

        # Wait for dataset dialog to appear
        time.sleep(1)

        # Verify dataset dialog opened
        try:
            dialog_path = self.button_images_dir / "dataset_dialog.png"
            if dialog_path.exists():
                dialog = pyautogui.locateOnScreen(str(dialog_path), confidence=0.8)
                if not dialog:
                    pass
                else:
                    pass
            else:
                pass
        except Exception as e:
            pass

        # Type filename in the dataset field
        if not self.type_filename("dataset_filename_field.png", filename, "dataset filename field"):
            return False

        # Press Enter to load the file
        pyautogui.press("enter")
        time.sleep(2.5)  # Step 3: Wait 2.5 seconds

        return True

    def check_if_algorithm_selected(self):
        """
        Check if the target algorithm is already selected.

        The dropdown shows the currently selected algorithm text.
        - sleep_algorithm_dropdown.png shows Cole-Kripke selected
        - sadeh_dropdown.png shows Sadeh selected
        """
        try:
            # Determine image file based on algorithm
            if self.algorithm == SleepAlgorithm.SADEH:
                image_file = "sadeh_dropdown.png"
            else:
                # sleep_algorithm_dropdown.png already shows Cole-Kripke
                image_file = "sleep_algorithm_dropdown.png"

            image_path = self.button_images_dir / image_file
            if not image_path.exists():
                return False

            element = pyautogui.locateOnScreen(str(image_path), confidence=0.8)
            if element:
                return True
            return False
        except Exception as e:
            return False

    def select_sleep_algorithm(self):
        """Step 4: Select the configured sleep algorithm from dropdown."""
        # Wait longer for interface to stabilize after file loading
        time.sleep(3)  # Increased from 2 to 3 seconds

        # Check if algorithm is already selected
        algorithm_already_selected = self.check_if_algorithm_selected()
        if algorithm_already_selected:
            return True

        # Click the sleep algorithm dropdown
        # Try both dropdown images since we don't know which algorithm is currently shown
        # sleep_algorithm_dropdown.png = Cole-Kripke selected
        # sadeh_dropdown.png = Sadeh selected
        dropdown_clicked = False
        for dropdown_image in ["sleep_algorithm_dropdown.png", "sadeh_dropdown.png"]:
            if self.click_element(dropdown_image, "Sleep algorithm dropdown", confidence=0.8):
                dropdown_clicked = True
                break

        if not dropdown_clicked:
            return False

        time.sleep(0.5)

        # Click the appropriate algorithm option
        if self.algorithm == SleepAlgorithm.SADEH:
            option_image = "sadeh_option.png"
            option_description = "Sadeh algorithm option"
        else:
            option_image = "cole_kripke_option.png"
            option_description = "Cole-Kripke algorithm option"

        if not self.click_element(option_image, option_description):
            return False

        time.sleep(0.5)
        return True

    def open_sleep_epochs_dialog(self):
        """Step 5 & 6: Open Sleep Epochs dialog and select Show ALL epochs."""
        # Click Show Sleep Epochs button
        if not self.click_element("show_sleep_epochs_btn.png", "Show Sleep Epochs button"):
            return False

        time.sleep(1)

        # Click Show ALL epochs radio button
        if not self.click_element("show_all_epochs_radio.png", "Show ALL epochs radio button"):
            return False

        time.sleep(0.5)
        return True

    def export_to_csv(self, output_filename):
        """Step 7, 8, 9: Export to CSV with custom filename."""
        # Click Save Every Epoch to CSV button
        if not self.click_element("save_every_epoch_csv_btn.png", "Save Every Epoch to CSV button"):
            return False

        time.sleep(1)

        # Enter the output filename
        if not self.type_filename("filename_field.png", output_filename, "save filename field"):
            return False

        time.sleep(0.5)

        # Click Save button
        if not self.click_element("save_button.png", "Save button"):
            return False

        time.sleep(1)
        return True

    def handle_confirmation_dialogs(self):
        """Step 10 & 11: Click No on open dialog, Close on Sleep Epoch dialog."""
        # Wait longer for save completion and dialog to appear
        time.sleep(2)

        # Click No on "do you want to open file?" dialog
        if not self.click_element("no_button.png", "No button (don't open file)", confidence=0.7):
            pass

        time.sleep(0.5)

        # Click Close on Sleep Epoch List dialog
        if not self.click_element("close_button.png", "Close button (Sleep Epoch dialog)", confidence=0.7):
            pyautogui.press("escape")

        time.sleep(0.5)
        return True

    def process_single_file(self, filename):
        """Process a single AGD file through the complete workflow."""
        # Step 1-3: Select dataset and load file
        if not self.select_dataset(filename):
            return False

        # Step 4: Select sleep algorithm
        if not self.select_sleep_algorithm():
            return False

        # Step 5-6: Open Sleep Epochs dialog and select Show ALL
        if not self.open_sleep_epochs_dialog():
            return False

        # Create output filename: remove .agd extension, add algorithm name
        base_name = Path(filename).stem
        output_filename = f"{base_name} {self.algorithm_display_name} Sleep Epochs"

        # Step 7-9: Export to CSV
        if not self.export_to_csv(output_filename):
            return False

        # Step 10-11: Handle confirmation dialogs
        self.handle_confirmation_dialogs()

        return True

    def batch_process(self, agd_folder, output_folder=None):
        """Process all AGD files in the folder."""
        if output_folder:
            pass
        else:
            pass

        # Find ActiLife window
        if not self.find_actilife_window():
            return False

        # Get list of AGD files (excluding already processed ones)
        agd_files = self.get_agd_files(agd_folder, output_folder)
        if not agd_files:
            return True

        time.sleep(3)

        # Process each file
        successful = 0
        failed = 0

        for i, filename in enumerate(agd_files, 1):
            # Check for emergency stop before processing each file
            if self.check_emergency_stop():
                break

            if self.process_single_file(filename):
                successful += 1
            else:
                failed += 1

            # Short pause between files
            time.sleep(1)

        # Summary

        return successful > 0

    def cleanup(self):
        """Clean up resources."""
        try:
            keyboard.unhook_all()
        except Exception as e:
            pass


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch export sleep epochs from ActiLife AGD files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python actilife_batch_automation.py C:/Data/AGD_Files
  python actilife_batch_automation.py C:/Data/AGD_Files -o C:/Data/Output
  python actilife_batch_automation.py C:/Data/AGD_Files --algorithm cole-kripke
  python actilife_batch_automation.py C:/Data/AGD_Files -a sadeh -o C:/Data/Output

Button images will be loaded from: buttons/
If output folder is not specified, will check for existing files in the AGD folder.

Required button images:
  Existing (for Cole-Kripke):
    - sleep_algorithm_dropdown.png (dropdown showing Cole-Kripke selected)
    - cole_kripke_option.png (dropdown menu option)

  For Sadeh, also need:
    - sadeh_dropdown.png (dropdown showing Sadeh selected)
    - sadeh_option.png (dropdown menu option) [already exists]
        """,
    )
    parser.add_argument("agd_folder", help="Path to folder containing AGD files")
    parser.add_argument("-o", "--output", dest="output_folder", help="Output folder for CSV files (default: same as AGD folder)")
    parser.add_argument(
        "-a", "--algorithm", choices=["sadeh", "cole-kripke"], default="sadeh", help="Sleep scoring algorithm to use (default: sadeh)"
    )

    args = parser.parse_args()

    # Convert algorithm string to enum
    algorithm = SleepAlgorithm.SADEH if args.algorithm == "sadeh" else SleepAlgorithm.COLE_KRIPKE

    automation = ActiLifeBatchAutomation(algorithm=algorithm)
    try:
        automation.batch_process(args.agd_folder, args.output_folder)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        pass
    finally:
        automation.cleanup()


if __name__ == "__main__":
    main()
