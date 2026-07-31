import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from frontend.main_window import MainWindow


def load_styles(app):
    qss = Path("frontend/styles/theme.qss")

    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))


def main():
    app = QApplication(sys.argv)

    load_styles(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()