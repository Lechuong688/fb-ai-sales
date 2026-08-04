from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from backend.signals import signals


class StatusBar(QLabel):

    def __init__(self):
        super().__init__()

        self.setObjectName("statusBar")

        self.setAlignment(
            Qt.AlignLeft | Qt.AlignVCenter
        )

        self.setMinimumHeight(34)

        self.set_status("🟢 Ready")

        signals.status.connect(
            self.set_status
        )

    def set_status(self, text: str):

        self.setText(f"  {text}")