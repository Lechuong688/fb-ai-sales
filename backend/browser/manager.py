from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright
from backend.browser.facebook import FacebookBrowser
from backend.browser.session import BrowserSession


class BrowserManager:

    def __init__(self):

        self.playwright = None
        self.context = None
        self.page = None
        self.session = None

    def start(self, profile_name, window_bounds=None):

        profile_name = (profile_name or "").strip()
        if (
            not profile_name
            or profile_name in {".", ".."}
            or Path(profile_name).name != profile_name
        ):
            raise ValueError("Tên profile không hợp lệ.")

        # Đã chạy thì dùng lại
        if (
            self.session
            and self.session.running
            and self.is_alive()
        ):
            return self.page

        # Clean up a previous partially started or closed session before
        # creating another Playwright driver for this manager.
        self.stop()

        try:
            self.playwright = sync_playwright().start()

            profile = Path("data/profiles") / profile_name
            profile.mkdir(parents=True, exist_ok=True)

            args = []
            if window_bounds:
                if window_bounds.get("maximized"):
                    args.append("--start-maximized")
                else:
                    args.extend(
                        [
                            f"--window-position={int(window_bounds['x'])},{int(window_bounds['y'])}",
                            f"--window-size={int(window_bounds['width'])},{int(window_bounds['height'])}",
                        ]
                    )
            else:
                args.append("--start-maximized")

            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile),
                headless=False,
                args=args,
                no_viewport=True,
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
        except Exception:
            self.stop()
            raise

    def set_window_bounds(self, bounds):
        """Try to update an already open Chromium window's position and size."""
        if not self.context or not self.page or not bounds:
            return False
        session = None
        try:
            session = self.context.new_cdp_session(self.page)
            window_id = session.send("Browser.getWindowForTarget").get("windowId")
            if window_id is None:
                return False
            target_bounds = (
                {"windowState": "maximized"}
                if bounds.get("maximized")
                else {
                    "left": int(bounds["x"]),
                    "top": int(bounds["y"]),
                    "width": int(bounds["width"]),
                    "height": int(bounds["height"]),
                    "windowState": "normal",
                }
            )
            session.send(
                "Browser.setWindowBounds",
                {
                    "windowId": window_id,
                    "bounds": target_bounds,
                },
            )
            return True
        except Exception:
            return False
        finally:
            if session is not None:
                try:
                    session.detach()
                except Exception:
                    pass

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

        context = self.context
        playwright = self.playwright
        self.context = None
        self.page = None
        self.playwright = None

        try:
            if context:
                context.close()
        except Exception:
            pass
        finally:
            try:
                if playwright:
                    playwright.stop()
            except Exception:
                pass

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

    @property
    def facebook(self):

        return FacebookBrowser(self)
