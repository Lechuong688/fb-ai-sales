from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
)


class PageToolbar(QWidget):

    def __init__(self, button_text="Add"):
        super().__init__()

        layout = QHBoxLayout(self)

        self.add_btn = QPushButton(button_text)

        self.refresh_btn = QPushButton("🔄 Refresh")

        self.delete_btn = QPushButton("🗑 Delete")

        self.export_btn = QPushButton("Export")

        self.search = QLineEdit()

        self.search.setPlaceholderText("Search...")

        layout.addWidget(self.add_btn)
        layout.addWidget(self.refresh_btn)
        layout.addWidget(self.delete_btn)
        layout.addWidget(self.export_btn)

        layout.addStretch()

        layout.addWidget(self.search)