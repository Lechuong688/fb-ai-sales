import threading
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta

from backend.browser.facebook import FacebookBrowser
from backend.services.comment_rules import suggest_comment
from backend.facebook.parsers.post_date import VIETNAM_TZ


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

    def all_inner_texts(self):
        return [item.inner_text() for item in self.values]


class FakeElement:
    def __init__(self, text="", href=None, timestamp=None):
        self.text = text
        self.href = href
        self.timestamp = timestamp

    def inner_text(self, timeout=None):
        return self.text

    def get_attribute(self, name):
        return self.href if name == "href" else self.timestamp if name == "data-utime" else None


class FakeArticle(FakeElement):
    def locator(self, selector):
        if selector == 'div[data-ad-preview="message"]':
            return FakeLocator([FakeElement(self.text)])
        if selector.startswith('a[href*="/posts/"]'):
            return FakeLocator([FakeElement(href=self.href, timestamp=self.timestamp)] if self.href else [])
        if selector == "h2 a, h3 a":
            return FakeLocator([FakeElement(self.author)])
        return FakeLocator()

    def __init__(self, text, href, author="Người dùng", published="now"):
        super().__init__(text, href)
        self.author = author
        self.timestamp = str(int(datetime.now(VIETNAM_TZ).timestamp())) if published == "now" else published


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

    def wait_for_function(self, *_args, **_kwargs):
        pass

    def locator(self, selector):
        if selector == '[role="article"]':
            return FakeLocator(self.articles)
        return FakeLocator()

    def get_by_role(self, *_args, **_kwargs):
        return FakeLocator()

    def get_by_text(self, *_args, **_kwargs):
        return FakeLocator()


class FakeBrowser:
    def __init__(self, page):
        self.page = page
        self.context = FakeContext()


class BuyerPostScanTests(unittest.TestCase):
    def test_feed_that_never_hydrates_is_an_error_not_zero_customers(self):
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        page = FakePage([])
        facebook = FacebookBrowser(FakeBrowser(page))
        with patch.object(page, 'wait_for_function', side_effect=PlaywrightTimeoutError('fixture')):
            with self.assertRaisesRegex(RuntimeError, 'chưa tải được bài viết'):
                facebook.find_buying_posts('https://facebook.com/groups/demo/', ['cần mua'], group_only=True)
        self.assertEqual(facebook.last_post_scan_stats['reason'], 'feed_unreadable')

    def test_recent_only_skips_old_future_undated_and_keeps_pinned_order(self):
        now = datetime(2026, 11, 1, 12, tzinfo=VIETNAM_TZ)
        def item(number, age=None):
            timestamp = str(int((now - age).timestamp())) if age is not None else None
            return FakeArticle("Cần mua bếp từ", f"https://facebook.com/groups/demo/posts/{number}/", published=timestamp)
        page = FakePage([
            item(1, timedelta(days=100)), item(2, timedelta(days=14)), item(3),
            item(4, timedelta(days=15)), item(5, timedelta(days=15, seconds=1)),
            item(6, timedelta(hours=-1)),
        ])
        browser = FacebookBrowser(FakeBrowser(page))
        posts = browser.find_buying_posts("https://facebook.com/groups/demo", ["cần mua"], now=now, scroll_count=1, group_only=True)
        self.assertEqual({post["id"] for post in posts}, {"2", "4"})
        self.assertTrue(all(post["published_at"] for post in posts))
        self.assertEqual(browser.last_post_scan_stats["skipped_old"], 2)
        self.assertEqual(browser.last_post_scan_stats["skipped_unknown_date"], 1)
        self.assertEqual(browser.last_post_scan_stats["skipped_future"], 1)
        self.assertIn("sorting_setting=CHRONOLOGICAL", page.url)

    def test_ambiguous_two_weeks_is_skipped_until_full_hover_date_is_known(self):
        now = datetime(2026, 11, 1, 12, tzinfo=VIETNAM_TZ)
        class DateLink(FakeElement):
            def hover(self, **_kwargs):
                return None

        class DatedArticle(FakeArticle):
            def locator(self, selector):
                if selector.startswith('a[href*="/posts/"]'):
                    return FakeLocator([DateLink(text="2 tuần", href=self.href)])
                return super().locator(selector)

        page = FakePage([DatedArticle("Cần mua bếp từ", "https://facebook.com/groups/demo/posts/1/")])
        browser = FacebookBrowser(FakeBrowser(page))
        self.assertEqual(browser.find_buying_posts("https://facebook.com/groups/demo", ["cần mua"], now=now, scroll_count=1), [])
        tooltip = FakeElement(text="20 tháng 10, 2026 lúc 10:30")
        tooltip.is_visible = lambda: True
        page.get_by_role = lambda _role: FakeLocator([tooltip])
        posts = browser.find_buying_posts("https://facebook.com/groups/demo", ["cần mua"], now=now, scroll_count=1)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["published_at"], "2026-10-20T10:30:00+07:00")

    def test_group_scan_does_not_use_recommendations_or_comment_dates(self):
        page = FakePage([
            FakeArticle("Cần mua bếp từ", "https://facebook.com/groups/other/posts/1/"),
            FakeArticle("Cần mua bếp từ", "https://facebook.com/groups/demo/posts/2/?comment_id=99"),
            FakeArticle("Cần mua bếp từ", "https://facebook.com/groups/demo/posts/3/"),
        ])
        browser = FacebookBrowser(FakeBrowser(page))
        posts = browser.find_buying_posts("https://facebook.com/groups/demo", ["cần mua"], group_only=True, scroll_count=1)
        self.assertEqual([post["id"] for post in posts], ["3"])

    def test_virtualized_feed_can_find_buyer_after_six_scrolls(self):
        class MovingLocator:
            def __init__(self, page):
                self.page = page

            def count(self):
                return 1

            def nth(self, _index):
                number = self.page.position
                return FakeArticle("Cần mua bếp từ" if number >= 8 else "Bếp từ sẵn kho, tư vấn miễn phí, inbox báo giá",
                                   f"https://facebook.com/groups/demo/posts/{number}/")

        page = FakePage([])
        page.position = 0
        page.locator = lambda selector: MovingLocator(page) if selector == '[role="article"]' else FakeLocator()
        page.mouse.wheel = lambda *_args: setattr(page, "position", page.position + 1)
        progress = []
        browser = FacebookBrowser(FakeBrowser(page))
        posts = browser.find_buying_posts("https://facebook.com/groups/demo", ["cần mua"], max_posts=1,
                                          group_only=True, include_comments=True, progress_callback=progress.append)
        self.assertEqual([post["id"] for post in posts], ["8"])
        self.assertGreater(browser.last_post_scan_stats["scrolls"], 6)
        self.assertTrue(progress)
        self.assertEqual(browser.last_post_scan_stats["reason"], "post_limit")

    def test_stalled_feed_has_an_explicit_reason(self):
        page = FakePage([FakeArticle("Không liên quan", "https://facebook.com/groups/demo/posts/1/")])
        browser = FacebookBrowser(FakeBrowser(page))
        self.assertEqual(browser.find_buying_posts("https://facebook.com/groups/demo", ["cần mua"]), [])
        self.assertEqual(browser.last_post_scan_stats["reason"], "no_new_posts")

    def test_seller_only_feed_keeps_full_search_budget_until_a_customer_is_found(self):
        page = FakePage([
            FakeArticle('Bếp từ sẵn kho, ai cần mua inbox báo giá', 'https://facebook.com/posts/1/'),
            FakeArticle('Mình cần mua bếp từ cho gia đình', 'https://facebook.com/posts/2/'),
        ])
        facebook = FacebookBrowser(FakeBrowser(page))
        # Already past the 55% reservation, but no eligible thread needs it yet.
        with patch('backend.browser.facebook.time.monotonic', side_effect=[0, 0, 0] + [100] * 50):
            posts = facebook.find_buying_posts('https://facebook.com/groups/demo/', ['cần mua'],
                                              max_posts=1, scroll_count=1, include_comments=True, max_seconds=180)
        self.assertEqual([post['id'] for post in posts], ['2'])

    def test_rule_filter_excludes_seller_before_result_limit(self):
        page = FakePage([
            FakeArticle("Bên em bán bếp từ, ai cần mua liên hệ", "https://facebook.com/posts/1"),
            FakeArticle("Cần mua bếp từ cho gia đình", "https://facebook.com/posts/2"),
        ])
        facebook = FacebookBrowser(FakeBrowser(page))
        posts = facebook.find_buying_posts(
            "https://facebook.com/groups/demo", ["cần mua"], max_posts=1, scroll_count=1,
            message_filter=lambda text: suggest_comment(text)["status"] == "draft",
        )
        self.assertEqual([post["id"] for post in posts], ["2"])

    def test_does_not_match_keywords_from_comments_when_post_body_is_missing(self):
        class NoPostBody(FakeArticle):
            def locator(self, selector):
                if selector == 'div[data-ad-preview="message"]':
                    return FakeLocator()
                return super().locator(selector)

        page = FakePage([NoPostBody("Comment: Cần mua bếp từ", "https://facebook.com/posts/1")])
        facebook = FacebookBrowser(FakeBrowser(page))
        self.assertEqual(facebook.find_buying_posts(
            "https://facebook.com/groups/demo", ["cần mua"], scroll_count=1,
        ), [])

    def test_tracking_variants_do_not_count_as_separate_posts(self):
        page = FakePage([
            FakeArticle("Co bac nao co bep tu?", "https://www.facebook.com/groups/demo/posts/45/?ref=share"),
            FakeArticle("Có bác nào có bếp từ?", "https://m.facebook.com/groups/demo/posts/45/#comments"),
        ])
        facebook = FacebookBrowser(FakeBrowser(page))
        posts = facebook.find_buying_posts(
            "https://facebook.com/groups/demo", ["có bác nào có"], scroll_count=1,
        )
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["id"], "45")

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
