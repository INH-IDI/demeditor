"""
dem_editor/ui/styles.py
Modern minimalist stylesheet and visual themes for DEM Editor.
"""

DARK_THEME = """
QMainWindow {
    background-color: #1e1e24;
    color: #e0e0e0;
}
QWidget {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: #e0e0e0;
}
QToolBar {
    background-color: #25252d;
    border-bottom: 1px solid #383842;
    padding: 4px;
    spacing: 6px;
}
QToolButton {
    background-color: transparent;
    color: #f0f0f0;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 9px;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #383845;
    border: 1px solid #4a4a5a;
}
QToolButton:pressed {
    background-color: #2d2d38;
}
QToolButton:disabled {
    color: #666677;
}
QTableView {
    background-color: #18181c;
    alternate-background-color: #1f1f25;
    color: #f0f0f0;
    gridline-color: #2c2c36;
    selection-background-color: #2a52be;
    selection-color: #ffffff;
    border: none;
}
QHeaderView::section {
    background-color: #262630;
    color: #a0a0b5;
    padding: 4px 6px;
    border: 1px solid #1f1f26;
    font-weight: 600;
    font-size: 12px;
}
QHeaderView::section:checked {
    background-color: #333342;
    color: #ffffff;
}
QStatusBar {
    background-color: #1a1a20;
    color: #9a9ab0;
    border-top: 1px solid #2e2e3a;
    font-size: 12px;
    padding: 2px 8px;
}
QDockWidget {
    color: #f0f0f0;
    font-weight: 600;
    titlebar-close-icon: url(close.png);
}
QDockWidget::title {
    background: #25252d;
    padding: 6px 10px;
    border-bottom: 1px solid #383842;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #2a2a35;
    border: 1px solid #3e3e4f;
    border-radius: 4px;
    padding: 4px 8px;
    color: #f0f0f0;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
    border: 1px solid #5a5a75;
}
QComboBox::drop-down {
    border: none;
}
QPushButton {
    background-color: #2e5cb8;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #3b6fd6;
}
QPushButton:pressed {
    background-color: #254a96;
}
QPushButton:disabled {
    background-color: #333340;
    color: #777788;
}
QGroupBox {
    border: 1px solid #383846;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #8cafff;
}
"""

LIGHT_THEME = """
QMainWindow {
    background-color: #f5f6f8;
    color: #222222;
}
QWidget {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: #222222;
}
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #dcdfe4;
    padding: 4px;
    spacing: 6px;
}
QToolButton {
    background-color: transparent;
    color: #333333;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 5px 9px;
    font-weight: 500;
}
QToolButton:hover {
    background-color: #e9ecef;
    border: 1px solid #ced4da;
}
QToolButton:pressed {
    background-color: #dde1e5;
}
QToolButton:disabled {
    color: #a0a0a0;
}
QTableView {
    background-color: #ffffff;
    alternate-background-color: #f8f9fa;
    color: #1a1a1a;
    gridline-color: #e2e5e9;
    selection-background-color: #3b82f6;
    selection-color: #ffffff;
    border: none;
}
QHeaderView::section {
    background-color: #eaedf1;
    color: #495057;
    padding: 4px 6px;
    border: 1px solid #d4d8de;
    font-weight: 600;
    font-size: 12px;
}
QStatusBar {
    background-color: #ffffff;
    color: #495057;
    border-top: 1px solid #dcdfe4;
    font-size: 12px;
    padding: 2px 8px;
}
QDockWidget::title {
    background: #eaedf1;
    padding: 6px 10px;
    border-bottom: 1px solid #dcdfe4;
    font-weight: 600;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: #ffffff;
    border: 1px solid #ced4da;
    border-radius: 4px;
    padding: 4px 8px;
    color: #212529;
}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QLineEdit:hover {
    border: 1px solid #86b7fe;
}
QPushButton {
    background-color: #0d6efd;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 6px 12px;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #0b5ed7;
}
QPushButton:pressed {
    background-color: #0a58ca;
}
QPushButton:disabled {
    background-color: #e9ecef;
    color: #adb5bd;
}
QGroupBox {
    border: 1px solid #ced4da;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #0d6efd;
}
"""
