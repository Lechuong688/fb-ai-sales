from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

from backend.browser.session import BrowserSession


class BrowserManager:

    def __init__(self):

        self.playwright = None
        self.context = None
        self.page = None
        self.session = None

    def start(self, profile_name):

        # Đã chạy thì dùng lại
        if (
            self.session
            and self.session.running
            and self.is_alive()
        ):
            return self.page

        self.playwright = sync_playwright().start()

        profile = Path(f"data/profiles/{profile_name}")

        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile),
            headless=False
        )

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()

        self.session = BrowserSession(
            profile=profile_name,
            context=self.context,
            page=self.page,
            running=True,
            started_at=datetime.now(),
            last_active=datetime.now()
        )

        return self.page

    def goto(self, url):

        self.page.goto(url)

    def is_logged_in(self):

        try:

            self.page.wait_for_load_state("networkidle")

            return self.page.locator(
                '[aria-label="Trang chủ"], [aria-label="Home"]'
            ).count() > 0

        except Exception:

            return False

    def stop(self):

        if self.context:
            self.context.close()

        if self.playwright:
            self.playwright.stop()

        self.context = None
        self.page = None
        self.playwright = None

        if self.session:
            self.session.running = False
            self.session.logged_in = False

    def get_session(self):

        return self.session
    
    def open_url(self, url):

        if self.page is None:
            raise RuntimeError(
                "Browser chưa được khởi động."
            )

        self.page.goto(url)

        if self.session:
            self.session.last_active = datetime.now()

    def new_tab(self):

        page = self.context.new_page()

        self.page = page

        self.session.page = page

        return page
    
    def close_current_tab(self):

        if len(self.context.pages) <= 1:
            return

        self.page.close()

        self.page = self.context.pages[0]

        self.session.page = self.page

    def is_alive(self):

        if self.page is None:
            return False

        try:
            self.page.title()
            return True

        except Exception:
            return False