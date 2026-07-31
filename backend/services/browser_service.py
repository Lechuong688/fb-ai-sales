from backend.services.logger import AppLogger
from backend.services.dashboard_service import DashboardService


class BrowserService:

    @staticmethod
    def login():

        AppLogger.log("Opening Facebook...")

        # Playwright sẽ được thêm sau

        DashboardService.set_facebook_status("Online")

        AppLogger.log("Facebook Login Success")