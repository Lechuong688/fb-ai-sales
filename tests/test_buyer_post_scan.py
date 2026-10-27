import threading
import unittest

from backend.browser.facebook import FacebookBrowser


class FakeLocator:
    def __init__(self, values=()):
        self.values = list(values)

    @property
    def first(self):
        return self.nth(0)

    def count(self):
        return len(self.values)

    def nth(self, index):
        return self.values[index]


class FakeElement:
    def __init__(self, text="", href=None):
        self.text = text
        self.href = href

    def inner_text(self, timeout=None):
        return self.text

    def get_attribute(self, name):
        return self.href if name == "href" else None


class FakeArticle(FakeElement):
    def locator(self, selector):
        if selector == 'div[data-ad-preview="message"]':
            return FakeLocator([FakeElement(self.text)])
        if selector.startswith('a[href*="/posts/"]'):
            return FakeLocator([FakeElement(href=self.href)] if self.href else [])
        if selector == "h2 a, h3 a":
            return FakeLocator([FakeElement(self.author)])
        return FakeLocator()

    def __init__(self, text, href, author="Người dùng"):
        super().__init__(text, href)
        self.author = author


class FakeMouse:
    def wheel(self, _x, _y):
        pass


class FakeContext:
    def cookies(self, _url):
        return [{"name": "c_user", "value": "123456"}]


class FakePage:
    def __init__(self, articles):
        self.url = "https://www.facebook.com/groups/demo"
        self.articles = articles
        self.mouse = FakeMouse()

    def goto(self, url, **_kwargs):
        self.url = url

    def wait_for_timeout(self, _milliseconds):
        pass

    def locator(self, selector):
        if selector == '[role="article"]':
            return FakeLocator(self.articles)
        return FakeLocator()


class FakeBrowser:
    def __init__(self, page):
        self.page = page
        self.context = FakeContext()


class BuyerPostScanTests(unittest.TestCase):
    def test_matches_buyer_phrases_case_insensitively(self):
        self.assertTrue(
            FacebookBrowser.matches_buying_intent(
                "Mình CẦN MUA máy lọc nước", ["cần mua"]
            )
        )
        self.assertFalse(
            FacebookBrowser.matches_buying_intent(
                "Thanh lý máy lọc nước giá tốt", ["cần mua", "ai bán"]
            )
        )

    def test_scan_returns_matching_posts_and_deduplicates_links(self):
        url = "https://www.facebook.com/groups/demo/posts/45/"
        page = FakePage(
            [
                FakeArticle("Cần mua máy lọc nước", url, "Lan"),
                FakeArticle("Thanh lý máy lọc nước", "https://facebook.com/posts/46"),
                FakeArticle("Mình cần mua máy lọc nước", url, "Lan"),
            ]
        )
        facebook = FacebookBrowser(FakeBrowser(page))

        posts = facebook.find_buying_posts(
            "https://www.facebook.com/groups/demo",
            ["cần mua"],
            scroll_count=1,
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["url"], url)
        self.assertEqual(posts[0]["id"], "45")
        self.assertEqual(posts[0]["author"], "Lan")

    def test_scan_respects_cancellation(self):
        page = FakePage([FakeArticle("Cần mua máy", "https://facebook.com/posts/45")])
        facebook = FacebookBrowser(FakeBrowser(page))
        cancellation = threading.Event()
        cancellation.set()

        posts = facebook.find_buying_posts(
            "https://www.facebook.com/groups/demo",
            ["cần mua"],
            scroll_count=1,
            cancel_event=cancellation,
        )

        self.assertEqual(posts, [])


if __name__ == "__main__":
    unittest.main()
