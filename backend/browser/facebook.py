from playwright.sync_api import TimeoutError


class FacebookBrowser:

    def __init__(self, browser):
        self.browser = browser

    @property
    def page(self):
        return self.browser.page

    def is_logged_in(self):

        try:

            self.page.goto(
                "https://www.facebook.com/me",
                wait_until="domcontentloaded"
            )

            self.page.wait_for_timeout(2000)

            url = self.page.url.lower()

            if "login" in url:
                return False

            if "checkpoint" in url:
                return False

            return True

        except:

            return False

    def get_profile(self):

        self.page.goto(
            "https://www.facebook.com/me",
            wait_until="networkidle"
        )

        self.page.wait_for_timeout(2000)

        url = self.page.url.rstrip("/")

        uid = url.split("/")[-1]

        name = ""

        selectors = [
            "h1",
            'h1 span',
            '[data-pagelet="ProfileTilesFeed_0"] h1'
        ]

        for selector in selectors:

            try:

                if self.page.locator(selector).count():

                    text = self.page.locator(selector).first.inner_text()

                    if text:

                        name = text

                        break

            except:
                pass

        return {
            "uid": uid,
            "name": name
        }

    def get_groups(self):

        self.page.goto(
            "https://www.facebook.com/groups/feed/",
            wait_until="networkidle"
        )

        self.page.wait_for_timeout(5000)

        groups = []

        links = self.page.locator(
            'a[href*="/groups/"]'
        )

        for i in range(links.count()):

            try:

                href = links.nth(i).get_attribute("href")

                text = links.nth(i).inner_text().strip()

                if not href:
                    continue

                if "/groups/feed" in href:
                    continue

                if "/discover/" in href:
                    continue

                if text == "":
                    continue

                groups.append({
                    "name": text,
                    "url": href
                })

            except:
                pass

        unique = {}

        for g in groups:

            unique[g["url"]] = g

        return list(unique.values())