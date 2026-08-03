from backend.browser.pool import browser_pool
from backend.services.logger import AppLogger
from backend.signals import signals


class BrowserService:

    @staticmethod
    def login(account):

        AppLogger.log(f"Đang mở Facebook cho {account.name}...")

        browser = browser_pool.get(account.profile)

        page = browser.start(account.profile)

        page.goto("https://www.facebook.com/")

        if browser.is_logged_in():

            browser.session.logged_in = True

            account.status = "Online"

            AppLogger.log(
                f"{account.name} đăng nhập thành công."
            )

            signals.facebook_login.emit(account)

        else:

            AppLogger.log(
                "Facebook chưa đăng nhập."
            )