from PySide6.QtWidgets import QLabel
from backend.signals import signals


class StatusBar(QLabel):

    def __init__(self):
        super().__init__()

        self.setText("Ready")

        signals.status.connect(
            self.set_status
        )

    def set_status(self, text):

        self.setText(text)