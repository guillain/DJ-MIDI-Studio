"""Application-wide DJ booth theme for Qt windows and dialogs."""

from PySide6.QtWidgets import QApplication

DJ_THEME = """
QMainWindow, QDialog, QDockWidget, QWidget {
    background: #0d121b;
    color: #e8eef7;
}
QMenuBar {
    background: #111a28;
    color: #dce7f5;
    border-bottom: 1px solid #2b3b53;
    padding: 3px;
}
QMenuBar::item {
    background: transparent;
    padding: 6px 10px;
    border-radius: 5px;
}
QMenuBar::item:selected, QMenu::item:selected {
    background: #d33c72;
    color: #ffffff;
}
QMenu {
    background: #151e2b;
    color: #e8eef7;
    border: 1px solid #3a506d;
    padding: 5px;
}
QMenu::item {
    padding: 7px 24px 7px 12px;
    border-radius: 4px;
}
QTabWidget::pane {
    background: #101925;
    border: 1px solid #2b3b53;
}
QTabBar::tab {
    background: #182437;
    color: #aebed1;
    border: 1px solid #30445f;
    padding: 8px 13px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #d33c72;
    color: #ffffff;
    border-color: #f26395;
}
QGroupBox {
    background: #151e2b;
    border: 1px solid #2b3b53;
    border-radius: 9px;
    margin-top: 12px;
    padding: 12px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: #8fe8ff;
    background: #0d121b;
}
QPushButton {
    background: #26364d;
    color: #e8eef7;
    border: 1px solid #405875;
    border-radius: 6px;
    padding: 7px 11px;
    font-weight: 600;
}
QPushButton:hover {
    background: #334b68;
    border-color: #00c2e8;
}
QPushButton:pressed {
    background: #d33c72;
}
QPushButton:disabled {
    background: #1a2432;
    color: #64758b;
    border-color: #273649;
}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QListWidget,
QSpinBox, QDoubleSpinBox {
    background: #0e1724;
    color: #e8eef7;
    border: 1px solid #334963;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #d33c72;
    selection-color: #ffffff;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QComboBox:focus, QListWidget:focus {
    border-color: #00c2e8;
}
QComboBox QAbstractItemView, QListView {
    background: #0e1724;
    color: #e8eef7;
    border: 1px solid #334963;
    selection-background-color: #d33c72;
    selection-color: #ffffff;
}
QCheckBox, QLabel, QRadioButton {
    color: #c9d5e4;
}
QTableWidget, QTableView, QTreeView {
    background: #0e1724;
    alternate-background-color: #121e2d;
    color: #dce7f5;
    border: 1px solid #2b3b53;
    selection-background-color: #d33c72;
    selection-color: #ffffff;
}
QHeaderView::section {
    background: #202d42;
    color: #b9c9dc;
    border: 0;
    border-bottom: 1px solid #3a506d;
    padding: 7px;
    font-weight: 600;
}
QStatusBar {
    background: #111a28;
    color: #9fb2c8;
    border-top: 1px solid #2b3b53;
}
QDockWidget {
    color: #e8eef7;
    titlebar-close-icon: none;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #111a28;
    border: none;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #405875;
    border-radius: 5px;
    min-height: 24px;
    min-width: 24px;
}
QScrollBar::handle:hover {
    background: #00b9d9;
}
QToolTip {
    background: #202d42;
    color: #ffffff;
    border: 1px solid #00c2e8;
    padding: 6px;
}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the shared palette once to every application window."""
    app.setStyleSheet(DJ_THEME)


__all__ = ["DJ_THEME", "apply_theme"]
