from pathlib import Path
from playwright.sync_api import sync_playwright


class BrowserManager:

    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None

    def start(self, profile_name="default"):

        # Nếu đã mở browser thì dùng lại
        if self.page:
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

        return self.page

    def goto(self, url):
        self.page.goto(url)

    def is_logged_in(self):

        self.goto("https://facebook.com")

        return "login" not in self.page.url

    def stop(self):

        if self.context:
            self.context.close()

        if self.playwright:
            self.playwright.stop()


browser_manager = BrowserManager()