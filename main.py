"""QLabs Track Editor modular OOP entry point."""

import sys

from PySide6.QtWidgets import QApplication, QStyleFactory

from ui.main_window import TrackEditorWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("QLabs Track Editor")
    # Fusion keeps spin-box step controls functional and consistently stacked
    # on Windows while the application stylesheet supplies the visual theme.
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")

    window = TrackEditorWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
