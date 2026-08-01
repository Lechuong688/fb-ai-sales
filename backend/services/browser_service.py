from backend.services.logger import AppLogger
from backend.services.dashboard_service import DashboardService


class BrowserService:

    @staticmethod
    def login(account):

        AppLogger.log(f"Đang đăng nhập {account.name}...")

        # TODO: Playwright sẽ được thêm ở Sprint sau

        account.status = "Online"

        DashboardService.set_facebook_status("🟢 Online")

        AppLogger.log(f"{account.name} đăng nhập thành công.")