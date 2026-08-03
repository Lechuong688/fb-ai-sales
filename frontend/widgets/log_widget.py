from datetime import datetime

from PySide6.QtWidgets import QListWidget

from backend.signals import signals


class LogWidget(QListWidget):

    def __init__(self):
        super().__init__()

        signals.log.connect(self.add_log)

        self.add_log("Application Started")

    def add_log(self, text):

        current = datetime.now().strftime("%H:%M:%S")

        self.addItem(f"[{current}] {text}")

        self.scrollToBottom()