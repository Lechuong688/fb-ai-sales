from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
)

from frontend.router import PAGES


class Sidebar(QListWidget):

    def __init__(self):
        super().__init__()

        self.setObjectName("sidebar")

        self.setFixedWidth(200)

        self.setSpacing(4)

        self.setFocusPolicy(Qt.NoFocus)

        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )

        for title, _ in PAGES:

            item = QListWidgetItem(title)

            item.setSizeHint(item.sizeHint())

            self.addItem(item)