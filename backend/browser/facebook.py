import re

from playwright.sync_api import TimeoutError


class FacebookBrowser:

    def __init__(self, browser):
        self.browser = browser

    @property
    def page(self):
        return self.browser.page

    # =========================================================
    # LOGIN
    # =========================================================

    def is_logged_in(self):

        try:
            page = self.page

            if page is None:
                return False

            url = page.url.lower()

            if "login" in url:
                return False

            if "checkpoint" in url:
                return False

            # Kiểm tra các dấu hiệu đã đăng nhập
            selectors = [
                '[aria-label="Trang chủ"]',
                '[aria-label="Home"]',
                '[aria-label="Trang cá nhân"]',
                '[aria-label="Profile"]',
                '[aria-label="Tài khoản"]',
                '[role="navigation"]',
            ]

            for selector in selectors:

                try:

                    if page.locator(selector).count() > 0:
                        return True

                except Exception:
                    pass

            return False

        except Exception:

            return False

    # =========================================================
    # PROFILE
    # =========================================================

    def get_profile(self):

        page = self.page

        if page is None:
            raise RuntimeError(
                "Facebook page chưa được mở."
            )

        # -----------------------------------------------------
        # Lấy thông tin từ trang hiện tại trước
        # -----------------------------------------------------

        uid = ""
        name = ""

        try:

            html = page.content()

            patterns = [
                r'"USER_ID":"(\d+)"',
                r'"userID":"(\d+)"',
                r'"user_id":"(\d+)"',
                r'"actorID":"(\d+)"',
                r'"actor_id":"(\d+)"',
                r'"profile_id":"(\d+)"',
            ]

            for pattern in patterns:

                match = re.search(
                    pattern,
                    html
                )

                if match:

                    uid = match.group(1)
                    break

        except Exception:
            pass

        # -----------------------------------------------------
        # Lấy tên
        # -----------------------------------------------------

        selectors = [
            "h1",
            '[role="main"] h1',
        ]

        for selector in selectors:

            try:

                locator = page.locator(
                    selector
                )

                if locator.count() > 0:

                    text = (
                        locator.first
                        .inner_text()
                        .strip()
                    )

                    if text:

                        name = text
                        break

            except Exception:
                pass

        # -----------------------------------------------------
        # Thử /me nếu chưa đủ thông tin
        # -----------------------------------------------------

        if not uid or not name:

            current_url = page.url

            try:

                page.goto(
                    "https://www.facebook.com/me",
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_timeout(2500)

                url = page.url.lower()

                # Không được lấy "www.facebook.com" làm UID
                if (
                    "login" not in url
                    and "checkpoint" not in url
                ):

                    try:

                        html = page.content()

                        patterns = [
                            r'"USER_ID":"(\d+)"',
                            r'"userID":"(\d+)"',
                            r'"user_id":"(\d+)"',
                            r'"profile_id":"(\d+)"',
                        ]

                        for pattern in patterns:

                            match = re.search(
                                pattern,
                                html
                            )

                            if match:

                                uid = match.group(1)
                                break

                    except Exception:
                        pass

                    for selector in selectors:

                        try:

                            locator = page.locator(
                                selector
                            )

                            if locator.count() > 0:

                                text = (
                                    locator.first
                                    .inner_text()
                                    .strip()
                                )

                                if text:

                                    name = text
                                    break

                        except Exception:
                            pass

            except Exception:
                pass

        # -----------------------------------------------------
        # Restore page if necessary
        # -----------------------------------------------------

        if not page.url or "facebook.com" not in page.url:

            try:
                page.goto(
                    "https://www.facebook.com/",
                    wait_until="domcontentloaded",
                    timeout=30000
                )
            except Exception:
                pass

        if uid and not uid.isdigit():
            uid = ""

        return {
            "uid": uid,
            "name": name,
            "url": page.url
        }

    # =========================================================
    # GROUPS
    # =========================================================

    def get_groups(self):

        page = self.page

        if page is None:
            raise RuntimeError(
                "Facebook page chưa được mở."
            )

        urls = [
            "https://www.facebook.com/groups/joins/",
            "https://www.facebook.com/groups/feed/",
        ]

        groups = {}

        for target_url in urls:

            try:

                page.goto(
                    target_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_timeout(4000)

                # Scroll nhiều lần để Facebook load thêm
                for _ in range(8):

                    page.mouse.wheel(
                        0,
                        3000
                    )

                    page.wait_for_timeout(1200)

                links = page.locator(
                    'a[href*="/groups/"]'
                )

                total = links.count()

                for i in range(total):

                    try:

                        link = links.nth(i)

                        href = link.get_attribute(
                            "href"
                        )

                        text = (
                            link
                            .inner_text()
                            .strip()
                        )

                        if not href:
                            continue

                        if not text:
                            continue

                        # Chuẩn hóa URL
                        if href.startswith("/"):

                            href = (
                                "https://www.facebook.com"
                                + href
                            )

                        # Bỏ URL không phải group
                        if "/groups/feed" in href:
                            continue

                        if "/groups/joins" in href:
                            continue

                        if "/groups/discover" in href:
                            continue

                        if "/groups/search" in href:
                            continue

                        # Chuẩn hóa
                        href = href.split("?")[0]

                        # Chỉ nhận URL group
                        match = re.search(
                            r"/groups/([^/]+)",
                            href
                        )

                        if not match:
                            continue

                        group_id = match.group(1)

                        # Loại những route hệ thống
                        if group_id in [
                            "feed",
                            "joins",
                            "discover",
                            "search",
                            "create",
                        ]:
                            continue

                        groups[href] = {
                            "name": text,
                            "url": href
                        }

                    except Exception:
                        continue

            except Exception as e:

                print(
                    f"Group page error: {e}"
                )

        return list(groups.values())