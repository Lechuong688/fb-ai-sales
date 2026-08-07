import time

from PySide6.QtCore import QObject
from PySide6.QtCore import Signal
from PySide6.QtCore import Slot

from backend.browser.pool import browser_pool
from backend.services.account_service import AccountService
from backend.services.group_service import GroupService
from backend.services.logger import AppLogger


class SyncWorker(QObject):

    finished = Signal()

    error = Signal(str)

    @Slot(str)
    def sync(self, profile):

        try:

            browser = browser_pool.get(profile)

            facebook = browser.facebook

            AppLogger.log("Đang chờ đăng nhập Facebook...")

            while True:

                if facebook.is_logged_in():
                    break

                time.sleep(2)

            AppLogger.log("Đã phát hiện đăng nhập Facebook.")

            info = facebook.get_profile()

            account = AccountService().get_by_profile(profile)

            if account:

                account.uid = info["uid"]
                account.name = info["name"]
                account.status = "Online"

                AccountService().update(account)

            AppLogger.log("Đang đồng bộ Groups...")

            groups = facebook.get_groups()

            service = GroupService()

            for g in groups:

                service.create(
                    g["name"],
                    g["url"]
                )

            AppLogger.log(
                f"Đồng bộ {len(groups)} nhóm."
            )

            self.finished.emit()

        except Exception as e:

            self.error.emit(str(e))