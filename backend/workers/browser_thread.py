from PySide6.QtCore import QThread


class BrowserThread(QThread):
    """Keep Python's thread state alive between queued Playwright operations."""

    def run(self):
        # The default QThread.run() lives in C++. Separate Python slot callbacks
        # can then lose the Python execution context captured by Playwright's
        # greenlets. Keep this Python frame alive from browser start to shutdown.
        self.exec()
