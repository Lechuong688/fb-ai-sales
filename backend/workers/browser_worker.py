from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from backend.services.browser_service import BrowserService


class BrowserWorker(QObject):

    finished = Signal()

    error = Signal(str)

    @Slot(object)
    def open_profile(self, account):

        try:

            BrowserService.login(account)

            self.finished.emit()

        except Exception as e:

            self.error.emit(str(e))