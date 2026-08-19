"""QLabs Track Editor modular OOP entry point."""

import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import TrackEditorWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("QLabs Track Editor")

    window = TrackEditorWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
