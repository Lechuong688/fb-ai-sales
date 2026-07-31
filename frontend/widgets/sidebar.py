from PySide6.QtWidgets import QListWidget, QListWidgetItem

from frontend.router import PAGES


class Sidebar(QListWidget):

    def __init__(self):
        super().__init__()

        self.setFixedWidth(220)

        for title, _ in PAGES:
            self.addItem(QListWidgetItem(title))