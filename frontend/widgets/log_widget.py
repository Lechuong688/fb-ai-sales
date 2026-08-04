from datetime import datetime

from PySide6.QtWidgets import QListWidget

from backend.signals import signals


class LogWidget(QListWidget):

    MAX_LOGS = 300

    def __init__(self):
        super().__init__()

        self.setObjectName("logWidget")

        signals.log.connect(self.add_log)

        self.add_log(
            "SYSTEM",
            "Application Started"
        )

    def add_log(
        self,
        category: str,
        message: str = None
    ):

        # Cho phép gọi add_log("text")
        if message is None:
            message = category
            category = "INFO"

        current = datetime.now().strftime("%H:%M:%S")

        text = f"[{current}] [{category}] {message}"

        self.addItem(text)

        while self.count() > self.MAX_LOGS:
            self.takeItem(0)

        self.scrollToBottom()

    def info(self, message):

        self.add_log("INFO", message)

    def success(self, message):

        self.add_log("SUCCESS", message)

    def warning(self, message):

        self.add_log("WARNING", message)

    def error(self, message):

        self.add_log("ERROR", message)