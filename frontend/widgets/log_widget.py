from PySide6.QtWidgets import QListWidget


class LogWidget(QListWidget):

    def __init__(self):
        super().__init__()

        self.add_log("Application Started")
        self.add_log("Dashboard Loaded")
        self.add_log("Browser Ready")

    def add_log(self, text):

        self.addItem(text)

        self.scrollToBottom()