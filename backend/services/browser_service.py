from backend.browser.pool import browser_pool
from backend.services.logger import AppLogger


class BrowserService:

    @staticmethod
    def login(account):

        AppLogger.log(
            f"Đang mở Profile: {account.profile}"
        )

        browser = browser_pool.get(account.profile)

        browser.start(account.profile)

        browser.open_url(
            "https://facebook.com/"
        )

        AppLogger.log(
            "Profile đã được mở."
        )