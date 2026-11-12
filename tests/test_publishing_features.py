import csv
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from sqlalchemy import create_engine

from backend.services.publishing_service import PublishingService
from backend.workers.browser_worker import BrowserWorker
from backend.workers.reply_suggestion_worker import ReplySuggestionWorker
from frontend.pages.posts import PostPage
from frontend.pages.reports import ReportsPage
from frontend.pages.comment_page import CommentPage


class PublishingFeaturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.engine = create_engine('sqlite://')
        self.service = PublishingService(self.engine)

    def tearDown(self):
        self.app.processEvents()
        self.engine.dispose()

    def test_collections_are_scoped_to_profile_and_updates_persist(self):
        first = self.service.save_collection('Bếp', 'one', ['a', 'a', 'b'])
        self.service.save_collection('Bếp', 'two', ['c'])
        self.assertEqual(self.service.save_collection('Bếp', 'one', ['d']), first)
        reopened = PublishingService(self.engine)
        self.assertEqual(reopened.list_collections('one')[0]['urls'], ['d'])
        self.assertEqual(reopened.list_collections('two')[0]['urls'], ['c'])
        reopened.delete('collections', first)
        self.assertEqual(reopened.list_collections('one'), [])
        with self.assertRaises(ValueError):
            reopened.save_collection('', 'one', ['d'])

    def test_templates_preserve_media_without_targets(self):
        key = self.service.save_template('Mẫu', 'Nội dung', ['D:/ảnh.png'])
        row = PublishingService(self.engine).list_templates()[0]
        self.assertEqual((row['content'], row['media']), ('Nội dung', ['D:/ảnh.png']))
        self.service.delete('templates', key)
        self.assertEqual(self.service.list_templates(), [])

    def test_worker_stops_after_error_and_records_every_remaining_target(self):
        worker = BrowserWorker()
        worker.profile_name = 'one'
        facebook = Mock()
        facebook.publish_post.side_effect = [dict(message='Đã gửi'), RuntimeError('Facebook yêu cầu kiểm tra')]
        targets = [dict(kind='group', url=str(i)) for i in range(3)]
        with patch('backend.workers.browser_worker.browser_pool') as pool, \
             patch('backend.workers.browser_worker.PublishingService', return_value=self.service):
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            pool.get.return_value.facebook = facebook
            worker.publish_posts(dict(content='Bài đã duyệt', targets=targets))
        self.assertFalse(worker.operation_active)
        self.assertEqual(facebook.publish_post.call_count, 2)
        history = self.service.history()
        self.assertEqual({row['status'] for row in history}, {'submitted', 'failed', 'skipped'})
        self.assertTrue(all(row['content'] == 'Bài đã duyệt' for row in history))

    def test_worker_can_cancel_without_closing_profile(self):
        worker = BrowserWorker()
        worker.profile_name = 'one'
        stop = threading.Event()
        facebook = Mock()
        def publish(**_kwargs):
            stop.set()
            return dict(message='Đã gửi')
        facebook.publish_post.side_effect = publish
        with patch('backend.workers.browser_worker.browser_pool') as pool, \
             patch('backend.workers.browser_worker.PublishingService', return_value=self.service):
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            pool.get.return_value.facebook = facebook
            worker.publish_posts(dict(content='Bài', stop_event=stop, delay_seconds=3600,
                                      targets=[dict(kind='group', url=str(i)) for i in range(3)]))
            pool.close.assert_not_called()
        self.assertEqual(facebook.publish_post.call_count, 1)
        self.assertEqual(sum(row['status'] == 'skipped' for row in self.service.history()), 2)
        self.assertFalse(worker.cancel_event.is_set())

    def test_post_modes_dispatch_and_stop_pending_profiles(self):
        workers = {name: SimpleNamespace(operation_active=False, publish_requested=Mock()) for name in ('one', 'two')}
        with patch('frontend.pages.posts.AccountService') as accounts, \
             patch('frontend.pages.posts.GroupService') as groups, \
             patch('frontend.pages.posts.ProfileLabelService') as labels, \
             patch('frontend.pages.posts.PostDraftService') as drafts, \
             patch('frontend.pages.posts.PublishingService', return_value=self.service), \
             patch('frontend.pages.posts.browser_pool') as pool, \
             patch('frontend.pages.posts.QMessageBox.question', return_value=QMessageBox.Yes), \
             patch('frontend.pages.posts.QMessageBox.information'), \
             patch('frontend.pages.posts.QMessageBox.warning'):
            accounts.return_value.get_all.return_value = [SimpleNamespace(profile=name, name=name) for name in workers]
            labels.return_value.get_label.side_effect = lambda x: x
            groups.return_value.get_for_profile.return_value = []
            drafts.return_value.get_all.return_value = []
            drafts.return_value.save.return_value = SimpleNamespace(id=1)
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            pool.get_worker.side_effect = workers.get
            page = PostPage()
            page.content_input.setPlainText('Nội dung đã duyệt')
            for i in range(page.profile_list.count()):
                page.profile_list.item(i).setCheckState(Qt.Checked)
            page.publish_selected()
            self.assertEqual(page._publish_pending, {'one'})
            workers['two'].publish_requested.emit.assert_not_called()
            page.stop_publishing()
            page._on_publish_finished('one', [])
            self.assertTrue(page.publish_button.isEnabled())
            self.assertEqual(self.service.history()[0]['status'], 'skipped')
            page.publish_mode.setCurrentIndex(1)
            page.publish_selected()
            self.assertEqual(page._publish_pending, {'one', 'two'})
            workers['two'].publish_requested.emit.assert_called_once()
            page._on_publish_finished('one', [])
            page._on_publish_finished('two', [])
            page.deleteLater()

    def test_reports_filter_and_csv_use_same_rows(self):
        self.service.record('Bếp Chương', [dict(success=True, target='one', message='Đã gửi')], '=1+1')
        self.service.record('Other', [dict(success=False, target='two', message='Lỗi')], 'Other')
        page = ReportsPage(self.service)
        page.toolbar.search.setText('bep chuong')
        self.assertEqual(len(page._rows), 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.csv'
            with patch('frontend.pages.reports.QFileDialog.getSaveFileName', return_value=(str(path), 'CSV')):
                page.export_csv()
            with path.open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1][-1], "'=1+1")
        page.status_filter.setCurrentIndex(page.status_filter.findData('failed'))
        self.assertEqual(page.table.rowCount(), 0)
        page.deleteLater()

    def test_batch_ai_preserves_per_post_results_and_partial_errors(self):
        worker = ReplySuggestionWorker()
        completed = []
        progress = []
        worker.completed.connect(completed.append)
        worker.progress.connect(lambda done, total: progress.append((done, total)))
        with patch('backend.workers.reply_suggestion_worker.suggest_replies', side_effect=[['Gợi ý 1'], RuntimeError('API lỗi'), ['Gợi ý 3']]):
            worker.suggest(dict(posts=[dict(url=str(i), message=f'Bài {i}') for i in range(3)],
                                cancel_event=threading.Event()))
        self.assertEqual(completed[0][0]['suggestions'], ['Gợi ý 1'])
        self.assertEqual(completed[0][1]['error'], 'API lỗi')
        self.assertEqual(completed[0][2]['post']['url'], '2')
        self.assertEqual(progress[-1], (3, 3))

    def test_batch_ai_cancellation_keeps_completed_suggestions(self):
        worker = ReplySuggestionWorker()
        completed = []
        worker.completed.connect(completed.append)
        stop = threading.Event()
        def suggest(*args, **kwargs):
            stop.set()
            return ['Gợi ý']
        with patch('backend.workers.reply_suggestion_worker.suggest_replies', side_effect=suggest) as call:
            worker.suggest(dict(posts=[dict(message='Bài 1'), dict(message='Bài 2')], cancel_event=stop))
        self.assertEqual(call.call_count, 1)
        self.assertEqual(len(completed[0]), 1)

    def test_comment_collection_sources_never_send_collection_markers_to_browser(self):
        urls = ['https://www.facebook.com/groups/1/', 'https://www.facebook.com/groups/2/']
        self.service.save_collection('Ưu tiên', 'one', [urls[0], 'https://www.facebook.com/groups/999/'])
        worker = SimpleNamespace(operation_active=False, scan_requested=Mock())
        with patch('frontend.pages.comment_page.AccountService') as accounts, \
             patch('frontend.pages.comment_page.GroupService') as groups, \
             patch('frontend.pages.comment_page.PublishingService', return_value=self.service), \
             patch('frontend.pages.comment_page.load_company_catalog', return_value=None), \
             patch('frontend.pages.comment_page.browser_pool') as pool:
            accounts.return_value.get_all.return_value = [SimpleNamespace(profile='one', name='One')]
            groups.return_value.get_for_profile.return_value = [SimpleNamespace(url=url, name=url) for url in urls]
            pool.get_worker.return_value = worker
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            page = CommentPage()
            page.scan_posts()
            self.assertEqual(worker.scan_requested.emit.call_args.args[0]['source_urls'], urls)
            page._set_scanning(False)
            page.source_combo.setCurrentIndex(page.source_combo.count() - 1)
            page.scan_posts()
            self.assertEqual(worker.scan_requested.emit.call_args.args[0]['source_urls'], [urls[0]])
            page._set_scanning(False)
            page.deleteLater()

    def test_batch_review_applies_per_post_and_keeps_concurrent_manual_edits(self):
        with patch('frontend.pages.comment_page.AccountService') as accounts, \
             patch('frontend.pages.comment_page.load_company_catalog', return_value=None), \
             patch('frontend.pages.comment_page.QDialog.exec', return_value=QDialog.Accepted):
            accounts.return_value.get_all.return_value = []
            page = CommentPage()
            page.show_sample_posts()
            page._select_unsent()
            posts = page._selected_posts()[:2]
            self.assertEqual(len(posts), 2)
            second_row = next(i for i in range(page.results.rowCount())
                              if page.results.item(i, 0).data(Qt.UserRole)['url'] == posts[1]['url'])
            page.results.item(second_row, 6).setText('Bản sửa tay cần giữ')
            page._review_batch_replies([dict(post=post, suggestions=[f'AI {i}'], error='') for i, post in enumerate(posts)])
            first_row = next(i for i in range(page.results.rowCount())
                             if page.results.item(i, 0).data(Qt.UserRole)['url'] == posts[0]['url'])
            self.assertEqual(page.results.item(first_row, 6).text(), 'AI 0')
            self.assertEqual(page.results.item(second_row, 6).text(), 'Bản sửa tay cần giữ')
            page.result_search.setText('can mua')
            self.assertTrue(any(not page.results.isRowHidden(i) for i in range(page.results.rowCount())))
            page.deleteLater()


if __name__ == '__main__':
    unittest.main()
