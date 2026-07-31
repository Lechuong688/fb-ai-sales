from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QVBoxLayout,
)


class Card(QFrame):

    def __init__(self, title):

        super().__init__()

        self.setObjectName("card")

        layout = QVBoxLayout(self)

        title = QLabel(title)

        title.setObjectName("cardTitle")

        layout.addWidget(title)

        self.body = QVBoxLayout()

        layout.addLayout(self.body)

    def add_widget(self, widget):

        self.body.addWidget(widget)