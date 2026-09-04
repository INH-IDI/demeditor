#!/usr/bin/env python3
"""
DEM Editor - Scientific Bathymetry and Elevation Grid Editor.
Usage:
    python main.py [optional_path_to_dem_file]
"""

import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

# Ensure current directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dem_editor.ui.main_window import MainWindow


def main():
    # Enable High DPI scaling
    if hasattr(Qt.ApplicationAttribute, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt.ApplicationAttribute, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("DEM Editor")
    app.setOrganizationName("Scientific Hydrodynamics")

    target_file = sys.argv[1] if len(sys.argv) > 1 else None
    window = MainWindow(target_file)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
