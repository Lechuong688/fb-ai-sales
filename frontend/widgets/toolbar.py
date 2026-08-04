from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
)


class Toolbar(QWidget):

    searchChanged = Signal(str)

    def __init__(self, buttons=None, has_search=True):
        super().__init__()

        self.setObjectName("toolbar")

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 12)
        self.layout.setSpacing(10)

        self.buttons = []

        # ================= Buttons =================

        if buttons:

            for text, callback in buttons:
                self.add_button(text, callback)

        self.layout.addStretch()

        # ================= Search =================

        self.search = None

        if has_search:

            self.search = QLineEdit()

            self.search.setObjectName("toolbarSearch")

            self.search.setPlaceholderText(
                "🔍 Tìm kiếm..."
            )

            self.search.setFixedWidth(260)

            self.search.textChanged.connect(
                self.searchChanged.emit
            )

            self.layout.addWidget(self.search)

    # ============================================
    # Add button
    # ============================================

    def add_button(self, text, callback):

        button = QPushButton(text)

        button.setObjectName("toolbarButton")

        button.setMinimumHeight(36)

        if callback:
            button.clicked.connect(callback)

        self.layout.addWidget(button)

        self.buttons.append(button)

        return button

    # ============================================
    # Search
    # ============================================

    def text(self):

        if self.search:
            return self.search.text()

        return ""

    def clear_search(self):

        if self.search:
            self.search.clear()

    def set_search_visible(self, visible: bool):

        if self.search:
            self.search.setVisible(visible)