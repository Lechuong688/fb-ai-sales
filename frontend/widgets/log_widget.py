from datetime import datetime

from PySide6.QtWidgets import QListWidget

from backend.services.logger import AppLogger


class LogWidget(QListWidget):

    def __init__(self):
        super().__init__()

        AppLogger.register(self.add_log)

        self.add_log("Application Started")
        self.add_log("Dashboard Loaded")
        self.add_log("Browser Ready")

    def add_log(self, text: str):
        current_time = datetime.now().strftime("%H:%M:%S")

        self.addItem(f"[{current_time}] {text}")

        self.scrollToBottom()