from pathlib import Path
from playwright.sync_api import sync_playwright


class BrowserManager:
    def __init__(self):
        self.profile = Path("data/user_data")

    def launch(self):
        playwright = sync_playwright().start()

        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.profile),
            headless=False,
            args=[
                "--start-maximized",
            ],
            no_viewport=True,
        )

        return playwright, context