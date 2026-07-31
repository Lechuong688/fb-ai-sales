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
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm kiếm...")

        layout.addWidget(self.add_btn)
        layout.addStretch()
        layout.addWidget(self.search)