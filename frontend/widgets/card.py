from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
)


class Card(QFrame):

    def __init__(self, title: str = ""):
        super().__init__()

        self.setObjectName("card")

        layout = QVBoxLayout(self)

        layout.setContentsMargins(18, 18, 18, 18)

        layout.setSpacing(15)

        self.title = QLabel(title)

        self.title.setObjectName("cardTitle")

        layout.addWidget(self.title)

        self.body = QVBoxLayout()

        self.body.setSpacing(10)

        layout.addLayout(self.body)

        layout.addStretch()

    def add_widget(self, widget):

        self.body.addWidget(widget)

    def clear(self):

        while self.body.count():

            item = self.body.takeAt(0)

            widget = item.widget()

            if widget:

                widget.deleteLater()

    def set_title(self, text):

        self.title.setText(text)