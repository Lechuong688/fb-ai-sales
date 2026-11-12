import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.browser.facebook import FacebookBrowser
from backend.database.db import Base
from backend.database.models.group import Group
from backend.database.models.profile_group import ProfileGroup
from backend.database.repositories.group_repository import GroupRepository
from backend.facebook.parsers.group_parser import normalize_group_url
from backend.services.group_service import GroupService


def group(number, name=None):
    return {"name": name or f"Nhóm {number}", "url": f"https://www.facebook.com/groups/{number}/"}


class GroupURLTests(unittest.TestCase):
    def test_preserves_real_name_punctuation_and_numeric_suffixes(self):
        name = "Hội bếp · Nội thất (2026)"
        self.assertEqual(FacebookBrowser._clean_group_name(name), name)
        self.assertEqual(GroupService.clean_group_name(name), name)

    def test_removes_activity_metadata_from_name(self):
        self.assertEqual(FacebookBrowser._clean_group_name("Hội bếp · 2 ngày trước"), "Hội bếp")
        self.assertEqual(FacebookBrowser._clean_group_name("Hội bếp\nLast active: 2 days ago"), "Hội bếp")

    def test_canonicalizes_mobile_relative_and_tracking_links(self):
        for value in (
            "/groups/123/?ref=share#about",
            "https://m.facebook.com/groups/123",
            "http://facebook.com/groups/123/",
        ):
            self.assertEqual(normalize_group_url(value), group(123)["url"])

    def test_rejects_non_group_and_external_links(self):
        for value in (
            "", "https://facebook.com.evil.test/groups/123/",
            "https://evil.test/groups/123/", "javascript:alert(1)",
            "/groups/search/", "/groups/notifications/", "/groups/joins/",
            "/groups/123/posts/456/", "/groups/123%2Fposts/",
            "https://user@facebook.com/groups/123/", "/groups/../",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_group_url(value)


class GroupSyncTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine, tables=[Group.__table__, ProfileGroup.__table__])
        self.factory = sessionmaker(bind=self.engine, autoflush=False)
        self.repo = GroupRepository(session_factory=self.factory)
        self.service = GroupService.__new__(GroupService)
        self.service.repo = self.repo

    def tearDown(self):
        self.engine.dispose()

    def urls(self, profile):
        with self.factory() as db:
            return {
                row.url for row in db.query(Group)
                .join(ProfileGroup, ProfileGroup.group_id == Group.id)
                .filter(ProfileGroup.profile == profile).all()
            }

    def sync(self, profile, groups, complete=False, expected=None):
        return self.service.sync_discovered_groups(profile, groups, complete, expected)

    def test_unknown_total_never_removes_old_memberships(self):
        self.sync("a", [group(1)])
        result = self.sync("a", [group(2)], True, None)
        self.assertFalse(result["complete"])
        self.assertEqual(self.urls("a"), {group(1)["url"], group(2)["url"]})

    def test_partial_scan_never_removes_old_memberships(self):
        self.sync("a", [group(1)])
        result = self.sync("a", [group(2)], True, 3)
        self.assertFalse(result["complete"])
        self.assertEqual(len(self.urls("a")), 2)

    def test_complete_snapshot_replaces_only_its_profile(self):
        self.sync("a", [group(1)])
        self.sync("b", [group(1)])
        result = self.sync("a", [group(2)], True, 1)
        self.assertTrue(result["complete"])
        self.assertEqual(self.urls("a"), {group(2)["url"]})
        self.assertEqual(self.urls("b"), {group(1)["url"]})

    def test_empty_unknown_snapshot_keeps_old_groups(self):
        self.sync("a", [group(1)])
        self.sync("a", [], True, None)
        self.assertEqual(self.urls("a"), {group(1)["url"]})

    def test_confirmed_empty_snapshot_can_clear_membership(self):
        self.sync("a", [group(1)])
        self.sync("a", [], True, 0)
        self.assertEqual(self.urls("a"), set())

    def test_normalizes_duplicates_before_counting_and_saving(self):
        result = self.sync("a", [group(1), {"name": "Nhóm một", "url": "/groups/1?ref=share"}], True, 1)
        self.assertEqual(result, {"added": 1, "count": 1, "complete": True})
        self.assertEqual(len(self.urls("a")), 1)

    def test_invalid_scan_record_does_not_partially_save(self):
        self.sync("a", [group(1)])
        with self.assertRaises(ValueError):
            self.sync("a", [group(2), {"name": "Sai", "url": "https://evil.test/groups/3/"}], True, 2)
        self.assertEqual(self.urls("a"), {group(1)["url"]})

    def test_transaction_rolls_back_group_updates_and_new_memberships(self):
        self.sync("a", [group(1)])
        with self.assertRaises(KeyError):
            self.repo.sync_discovered_groups("a", [group(1, "Tên mới"), group(2), {"url": group(3)["url"]}], True)
        self.assertEqual(self.urls("a"), {group(1)["url"]})
        with self.factory() as db:
            self.assertEqual(db.query(Group).count(), 1)
            self.assertEqual(db.query(Group).first().name, "Nhóm 1")

    def test_display_does_not_unlink_groups_with_unknown_names(self):
        self.service.profile_groups = Mock()
        self.service.profile_groups.get_groups_for_profile.return_value = [
            SimpleNamespace(id=1, name="", url=group(1)["url"])
        ]
        self.assertEqual(len(self.service.get_for_profile("a")), 1)
        self.service.profile_groups.unlink_many.assert_not_called()

    def test_display_filters_legacy_navigation_urls_without_deleting(self):
        repository = Mock()
        self.service.repo = repository
        repository.get_all.return_value = [
            SimpleNamespace(id=1, **group(1)),
            SimpleNamespace(id=2, name="Khám phá", url="https://www.facebook.com/groups/discover/"),
            SimpleNamespace(id=3, name="Bản sao", url="https://m.facebook.com/groups/1?ref=share"),
        ]
        self.assertEqual(len(self.service.get_all()), 1)
        repository.delete.assert_not_called()
        repository.update.assert_not_called()


class FakeLink:
    def __init__(self, item):
        self.item = item

    def get_attribute(self, attribute):
        return self.item["url"] if attribute == "href" else None

    def inner_text(self, **_kwargs):
        return self.item["name"]


class FakeList:
    def __init__(self, items):
        self._items = items

    @property
    def items(self):
        return self._items() if callable(self._items) else self._items

    @property
    def first(self):
        return self.items[0]

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class FakeGroupPage:
    """Expose a fixed-size DOM whose cards change as its container scrolls."""
    def __init__(self, batches):
        self.batches = batches
        self.index = 0
        self.url = ""
        self.first = self

    def goto(self, url, **_kwargs):
        self.url = url

    def wait_for_timeout(self, _timeout):
        return None

    def count(self):
        return 1

    def locator(self, selector):
        if selector == 'a[href*="/groups/"]':
            return FakeList(lambda: [FakeLink(item) for item in self.batches[self.index]])
        return self

    def evaluate(self, _script):
        self.index = min(self.index + 1, len(self.batches) - 1)
        return {"atBottom": self.index == len(self.batches) - 1}


class GroupScanTests(unittest.TestCase):
    def scan(self, batches, expected, logged_in=True):
        browser = FacebookBrowser(SimpleNamespace(page=FakeGroupPage(batches)))
        with patch.object(browser, "is_logged_in", return_value=logged_in), \
             patch.object(browser, "_expected_joined_group_count", return_value=expected), \
             patch.object(browser, "_open_all_joined_groups"), \
             patch.object(browser, "_expand_group_list"):
            results = browser.get_groups()
        return browser, results

    def test_collects_virtualized_cards_without_dom_count_growth(self):
        browser, results = self.scan([[group(1)], [group(2)], [group(3)]], 3)
        self.assertEqual(len(results), 3)
        self.assertTrue(browser.last_group_scan_complete)

    def test_unknown_count_is_partial_even_at_bottom(self):
        browser, results = self.scan([[group(1)]], None)
        self.assertEqual(len(results), 1)
        self.assertFalse(browser.last_group_scan_complete)

    def test_missing_cards_are_partial(self):
        browser, _ = self.scan([[group(1)]], 2)
        self.assertFalse(browser.last_group_scan_complete)

    def test_logged_out_session_raises_instead_of_returning_empty_success(self):
        with self.assertRaisesRegex(RuntimeError, "đăng xuất"):
            self.scan([[]], 0, logged_in=False)

    def test_cancelled_scan_cannot_be_complete(self):
        browser = FacebookBrowser(SimpleNamespace(page=FakeGroupPage([[]])))
        event = threading.Event()
        event.set()
        with self.assertRaises(InterruptedError):
            browser.get_groups(cancel_event=event)
        self.assertFalse(browser.last_group_scan_complete)

    def test_navigation_failure_is_reported(self):
        page = FakeGroupPage([[]])
        page.goto = Mock(side_effect=RuntimeError("network failed"))
        browser = FacebookBrowser(SimpleNamespace(page=page))
        with self.assertRaisesRegex(RuntimeError, "network failed"):
            browser.get_groups()

    def test_redirect_away_from_joined_list_is_rejected(self):
        page = FakeGroupPage([[]])
        page.goto = lambda *_args, **_kwargs: setattr(page, "url", "https://www.facebook.com/groups/discover/")
        browser = FacebookBrowser(SimpleNamespace(page=page))
        with patch.object(browser, "is_logged_in", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "không mở danh sách"):
                browser.get_groups()

    def test_unnamed_duplicate_anchor_does_not_invalidate_named_card(self):
        browser, results = self.scan([[group(1), {"name": "", "url": group(1)["url"]}]], 1)
        self.assertEqual(len(results), 1)
        self.assertTrue(browser.last_group_scan_complete)

    def test_unnamed_unique_group_cannot_make_snapshot_complete(self):
        browser, results = self.scan([[group(1), {"name": "", "url": group(2)["url"]}]], 1)
        self.assertEqual(len(results), 1)
        self.assertFalse(browser.last_group_scan_complete)


class GroupWorkerTests(unittest.TestCase):
    def test_passive_identity_read_never_navigates_browser(self):
        page = Mock()
        page.url = "https://www.facebook.com/"
        page.content.return_value = '"profile_id":"999"'
        page.locator.return_value.count.return_value = 0
        context = Mock()
        context.cookies.return_value = [{"name": "c_user", "value": "123"}]
        browser = FacebookBrowser(SimpleNamespace(page=page, context=context))
        result = browser.get_profile(allow_navigation=False)
        self.assertEqual(result["uid"], "123")
        self.assertEqual(result["name"], "")
        page.goto.assert_not_called()

    def test_group_scan_runs_only_when_explicitly_requested(self):
        from backend.workers.browser_worker import BrowserWorker

        worker = BrowserWorker()
        worker.profile_name = "a"
        worker._sync_groups = Mock(return_value=0)
        with patch("backend.workers.browser_worker.browser_pool") as pool:
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            worker.groups_sync_requested.emit()
        worker._sync_groups.assert_called_once_with()
        self.assertFalse(worker.operation_active)

    def test_open_profile_stays_idle_without_scanning_groups(self):
        from backend.workers.browser_worker import BrowserWorker

        module = "backend.workers.browser_worker"
        account = SimpleNamespace(profile="a", uid="", name="", status="Offline")
        worker = BrowserWorker()
        ready = []
        synced = []
        worker.ready.connect(ready.append)
        worker.groups_synced.connect(synced.append)
        worker._sync_groups = Mock(side_effect=RuntimeError("scan failed"))
        with patch(f"{module}.browser_pool") as pool, \
             patch(f"{module}.AccountService"), \
             patch(f"{module}.AppLogger"), \
             patch(f"{module}.signals") as events:
            facebook = pool.get.return_value.facebook
            facebook.wait_for_login.return_value = True
            facebook.get_profile.return_value = {"uid": "123", "name": "Demo"}
            worker.open_profile(account)
            pool.close.assert_not_called()
            facebook.get_profile.assert_called_once_with(allow_navigation=False)
            facebook.get_groups.assert_not_called()
            worker._sync_groups.assert_not_called()
            events.groups_sync_failed.emit.assert_not_called()
        self.assertEqual(ready, ["a"])
        self.assertEqual(synced, [])
        self.assertEqual(account.status, "Online")
        self.assertFalse(worker.operation_active)


if __name__ == "__main__":
    unittest.main()
