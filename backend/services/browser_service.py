from backend.browser.pool import browser_pool
from backend.services.logger import AppLogger
from backend.signals import signals


class BrowserService:

    @staticmethod
    def login(account):

        AppLogger.log(f"Đang mở Facebook cho {account.name}...")

        browser = browser_pool.get(account.profile)

        browser.start(account.profile)

        if browser.is_logged_in():

            account.status = "Online"

            AppLogger.log(
                f"{account.name} đăng nhập thành công."
            )

            signals.facebook_login.emit(account)

            signals.log.emit(
                f"{account.name} đã Online."
            )

            signals.status.emit(
                "Facebook Connected"
            )

        else:

            AppLogger.log(
                "Facebook chưa đăng nhập."
            )