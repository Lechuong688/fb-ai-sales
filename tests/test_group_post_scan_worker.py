from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from backend.workers.browser_worker import BrowserWorker


class GroupPostScanWorkerTests(unittest.TestCase):
    def setUp(self):
        self.worker = BrowserWorker()
        self.worker.profile_name = "demo"
        self.groups = [SimpleNamespace(name=f"Hội bếp từ {number}", url=f"https://www.facebook.com/groups/{number}/") for number in (1, 2)]
        self.facebook = Mock()
        self.facebook.last_post_scan_stats = dict(seen_posts=20, found=1, skipped_old=3,
                                                  skipped_unknown_date=2, skipped_future=0, reason="no_new_posts")
        self.request = dict(phrases=["cần mua"], max_posts=100, max_age_days=999, min_ad_comments=25)

    def run_scan(self, request=None, storage_error=None):
        with patch("backend.workers.browser_worker.browser_pool") as pool, \
             patch("backend.workers.browser_worker.GroupService") as service, \
             patch("backend.workers.browser_worker.AppLogger"), \
             patch("backend.workers.browser_worker.signals") as events:
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            pool.get.return_value.facebook = self.facebook
            service.return_value.get_for_profile.return_value = self.groups
            with patch("backend.workers.browser_worker.LeadService") as lead_service:
                lead_service.return_value.capture_scan.return_value = {"saved": 1}
                if storage_error:
                    lead_service.return_value.capture_scan.side_effect = storage_error
                self.worker.scan_buying_posts(request or self.request)
            return pool, service, events

    def post(self, group):
        return dict(url=f"https://www.facebook.com/groups/{group}/posts/100/", message="Cần mua bếp từ",
                    published_at="2026-11-01T10:00:00+07:00")

    def test_all_owned_groups_use_strict_fifteen_days_and_deeper_scanning(self):
        self.facebook.find_buying_posts.side_effect = [[self.post(1)], [self.post(2)]]
        pool, service, events = self.run_scan()
        self.assertEqual(self.facebook.find_buying_posts.call_count, 2)
        service.return_value.get_for_profile.assert_called_once_with("demo")
        for call in self.facebook.find_buying_posts.call_args_list:
            self.assertEqual(call.kwargs["max_age_days"], 15)
            self.assertEqual(call.kwargs["scroll_count"], 120)
            self.assertEqual(call.kwargs["max_seconds"], 180)
            self.assertTrue(call.kwargs["group_only"])
            self.assertEqual(call.kwargs['min_ad_comments'], 25)
            self.assertNotEqual(call.kwargs["source_url"], "https://www.facebook.com/")
        self.assertEqual(len(events.buying_posts_found.emit.call_args.args[1]), 2)
        summary = events.buying_posts_progress.emit.call_args.args[1]
        self.assertEqual(summary["groups_scanned"], 2)
        self.assertEqual(summary["skipped_old"], 6)
        self.assertEqual(summary["skipped_unknown_date"], 4)
        pool.close.assert_not_called()
        self.assertFalse(self.worker.operation_active)

    def test_unrelated_groups_are_skipped_before_opening_any_feed(self):
        self.groups.extend([
            SimpleNamespace(name='Rơi giấy tờ Hà Nội', url='https://www.facebook.com/groups/3/'),
            SimpleNamespace(name='Tuyển dụng PT fitness', url='https://www.facebook.com/groups/4/'),
            SimpleNamespace(name='', url='https://www.facebook.com/groups/5/'),
        ])
        self.facebook.find_buying_posts.return_value = []
        _pool, _service, events = self.run_scan()
        self.assertEqual([call.kwargs['source_url'] for call in self.facebook.find_buying_posts.call_args_list],
                         [group.url for group in self.groups[:2]])
        summary = events.buying_posts_progress.emit.call_args.args[1]
        self.assertEqual(summary['groups_requested'], 5)
        self.assertEqual(summary['groups_total'], 2)
        self.assertEqual(summary['groups_skipped_unrelated'], 3)

    def test_explicit_unrelated_group_is_skipped_without_browser_access(self):
        self.groups[0].name = 'Mua bán bất động sản'
        pool, _service, events = self.run_scan(dict(self.request, source_urls=[self.groups[0].url]))
        pool.get.assert_not_called()
        self.facebook.find_buying_posts.assert_not_called()
        events.buying_posts_error.emit.assert_not_called()
        summary = events.buying_posts_progress.emit.call_args.args[1]
        self.assertEqual(summary['reason'], 'no_relevant_groups')
        self.assertEqual(summary['groups_skipped_unrelated'], 1)

    def test_changed_product_scope_changes_groups_scanned(self):
        self.groups.append(SimpleNamespace(name='Hội máy lọc nước', url='https://www.facebook.com/groups/3/'))
        self.facebook.find_buying_posts.return_value = []
        self.run_scan(dict(self.request, products=['máy lọc nước']))
        self.facebook.find_buying_posts.assert_called_once()
        self.assertEqual(self.facebook.find_buying_posts.call_args.kwargs['source_url'], self.groups[-1].url)

    def test_stop_preserves_results_and_does_not_stop_profile(self):
        def stop_after_first(**_kwargs):
            self.worker.scan_cancel_event.set()
            return [self.post(1)]
        self.facebook.find_buying_posts.side_effect = stop_after_first
        pool, _service, events = self.run_scan()
        self.assertEqual(self.facebook.find_buying_posts.call_count, 1)
        self.assertEqual(len(events.buying_posts_found.emit.call_args.args[1]), 1)
        self.assertEqual(events.buying_posts_progress.emit.call_args.args[1]["reason"], "cancelled")
        self.assertFalse(self.worker.cancel_event.is_set())
        pool.close.assert_not_called()

    def test_error_in_one_group_does_not_prevent_scanning_next_group(self):
        self.facebook.find_buying_posts.side_effect = [RuntimeError("Không có quyền truy cập"), [self.post(2)]]
        _pool, _service, events = self.run_scan()
        self.assertEqual(self.facebook.find_buying_posts.call_count, 2)
        self.assertEqual(events.buying_posts_progress.emit.call_args.args[1]["failed_groups"], 1)
        events.buying_posts_error.emit.assert_not_called()

    def test_feed_and_unowned_groups_are_rejected_without_browser_access(self):
        for url in ("https://www.facebook.com/", "https://www.facebook.com/groups/other/"):
            with self.subTest(url=url):
                pool, _service, events = self.run_scan(dict(self.request, source_urls=[url]))
                pool.get.assert_not_called()
                events.buying_posts_error.emit.assert_called_once()

    def test_selected_single_group_and_global_result_limit(self):
        self.facebook.find_buying_posts.return_value = [self.post(2)]
        self.run_scan(dict(self.request, source_urls=[self.groups[1].url], max_posts=1))
        self.facebook.find_buying_posts.assert_called_once()
        self.assertEqual(self.facebook.find_buying_posts.call_args.kwargs["source_url"], self.groups[1].url)

    def test_no_groups_reports_error_instead_of_scanning_home(self):
        self.groups = []
        pool, _service, events = self.run_scan()
        pool.get.assert_not_called()
        events.buying_posts_error.emit.assert_called_once()

    def test_database_error_keeps_scan_results_and_reports_unsaved_count(self):
        self.facebook.find_buying_posts.side_effect = [[self.post(1)], [self.post(2)]]
        _pool, _service, events = self.run_scan(storage_error=RuntimeError("Không ghi được database"))
        self.assertEqual(len(events.buying_posts_found.emit.call_args.args[1]), 2)
        summary = events.buying_posts_progress.emit.call_args.args[1]
        self.assertEqual(summary["save_errors"], 2)
        self.assertEqual(summary["saved_posts"], 0)
        events.buying_posts_error.emit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
