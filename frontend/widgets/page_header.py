from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)


class PageHeader(QWidget):

    def __init__(self, title: str, description: str = ""):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 18)
        layout.setSpacing(4)

        self.title = QLabel(title)
        self.title.setObjectName("pageTitle")

        self.description = QLabel(description)
        self.description.setObjectName("pageDescription")

        layout.addWidget(self.title)

        if description:
            layout.addWidget(self.description)

    def set_title(self, text: str):
        self.title.setText(text)

    def set_description(self, text: str):
        self.description.setText(text)
        self.description.setVisible(bool(text))