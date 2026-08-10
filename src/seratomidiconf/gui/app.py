from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from seratomidiconf.gui.main_window import MainWindow


def run() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
