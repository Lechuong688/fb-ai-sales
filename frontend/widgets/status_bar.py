from PySide6.QtWidgets import (
    QLabel,
    QFrame,
    QHBoxLayout,
)


class StatusBar(QFrame):

    def __init__(self):
        super().__init__()

        self.setFixedHeight(32)

        layout = QHBoxLayout(self)

        self.label = QLabel("Ready")

        layout.addWidget(self.label)

        layout.addStretch()

    def set_status(self, text):
        self.label.setText(text)