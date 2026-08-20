"""System-aware Windows 11 inspired visual theme."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication


def system_uses_dark_theme() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    return app.styleHints().colorScheme() == Qt.ColorScheme.Dark


def app_stylesheet(dark: bool) -> str:
    if dark:
        c = dict(
            bg="#1b1d21", surface="#20242c", card="#282c35", field="#252932",
            hover="#303746", selected="#243d59", border="#393f4a",
            text="#f1f3f5", muted="#aeb6c2", disabled="#69717d",
            accent="#60b8ff", accent_text="#9bd3ff", tooltip="#313640",
        )
    else:
        c = dict(
            bg="#e7ebee", surface="#eef1f3", card="#f4f6f7", field="#fafbfc",
            hover="#e1e8ed", selected="#d6eaf5", border="#bec8cf",
            text="#26323c", muted="#5d6a74", disabled="#9aa5ad",
            accent="#1678a5", accent_text="#12678f", tooltip="#263640",
        )

    return f"""
QMainWindow, QWidget {{ background-color: {c['bg']}; color: {c['text']}; font-family: "Segoe UI"; font-size: 10pt; }}
QMenuBar {{ background: {c['surface']}; color: {c['text']}; border-bottom: 1px solid {c['border']}; padding: 2px 6px; }}
QMenuBar::item {{ padding: 6px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {c['hover']}; color: {c['accent_text']}; }}
QMenu {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 5px; }}
QMenu::item {{ padding: 7px 26px 7px 10px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c['selected']}; color: {c['text']}; }}
#topControlBar {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; }}
#inspectorPanel {{ background: {c['bg']}; }}
#selectionSummary {{ background: {c['field']}; color: {c['text']}; padding: 10px; border: 1px solid {c['border']}; border-radius: 6px; }}
QGroupBox {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; margin-top: 13px; padding: 13px 8px 8px 8px; font-weight: 600; color: {c['muted']}; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 6px; color: {c['accent_text']}; background: {c['surface']}; letter-spacing: 1px; }}
QLabel {{ background: transparent; color: {c['text']}; }}
QLabel:disabled {{ color: {c['disabled']}; }}
QLabel#toolCategory {{ color: {c['accent_text']}; background: {c['selected']}; border: 1px solid {c['border']}; border-radius: 4px; padding: 3px 6px; font-size: 9px; font-weight: 700; }}
QCheckBox {{ spacing: 6px; background: transparent; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid {c['border']}; border-radius: 3px; background: {c['field']}; }}
QCheckBox::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {c['field']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 6px; min-height: 28px; padding: 1px 8px; selection-background-color: {c['accent']}; }}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {c['muted']}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {c['accent']}; }}
QComboBox::drop-down {{ width: 24px; border: 0; border-left: 1px solid {c['border']}; }}
QComboBox QAbstractItemView {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; selection-background-color: {c['selected']}; outline: 0; }}
QPushButton, QToolButton {{ background: {c['card']}; color: {c['text']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 4px 8px; }}
QPushButton:hover, QToolButton:hover {{ background: {c['hover']}; border-color: {c['accent']}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {c['selected']}; }}
QPushButton:checked, QToolButton:checked {{ background: {c['selected']}; border: 1px solid {c['accent']}; color: {c['accent_text']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {c['disabled']}; border-color: {c['border']}; }}
QTabWidget::pane {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 7px; top: -1px; }}
QTabBar::tab {{ background: {c['bg']}; color: {c['muted']}; border: 1px solid {c['border']}; border-bottom: none; padding: 7px 19px; margin-right: 3px; border-top-left-radius: 7px; border-top-right-radius: 7px; font-weight: 600; }}
QTabBar::tab:hover {{ background: {c['hover']}; color: {c['accent_text']}; }}
QTabBar::tab:selected {{ background: {c['surface']}; color: {c['accent_text']}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: {c['bg']}; }}
QScrollBar:vertical {{ background: {c['bg']}; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 30px; border-radius: 5px; }}
QScrollBar::handle:vertical:hover {{ background: {c['muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: {c['bg']}; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: {c['border']}; min-width: 30px; border-radius: 5px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QStatusBar {{ background: {c['surface']}; color: {c['muted']}; border-top: 1px solid {c['border']}; }}
QToolTip {{ background: {c['tooltip']}; color: #ffffff; border: 1px solid {c['border']}; padding: 5px; }}
"""
