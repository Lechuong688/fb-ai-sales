import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PySide6.QtWidgets import QApplication
from backend.utils.task_control import TaskControl, TaskCancellation
from backend.workers.browser_worker import BrowserWorker
from backend.workers.reply_suggestion_worker import ReplySuggestionWorker
from frontend.pages.comment_page import CommentPage
from frontend.pages.groups import GroupsPage


class TaskControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def run_thread(self, callback):
        thread = threading.Thread(target=callback, daemon=True)
        thread.start()
        self.addCleanup(lambda: thread.join(2))
        return thread

    def test_pause_blocks_until_resume_and_preserves_active_budget(self):
        control = TaskControl()
        cancellation = TaskCancellation(control=control)
        control.pause()
        reached = threading.Event()
        before = cancellation.active_time()
        thread = self.run_thread(lambda: (cancellation.is_set(), reached.set()))
        self.assertFalse(reached.wait(0.08))
        self.assertAlmostEqual(cancellation.active_time(), before, delta=0.02)
        control.resume()
        self.assertTrue(reached.wait(1))
        thread.join(1)
        self.assertFalse(cancellation.is_set())

    def test_stop_while_paused_unblocks_and_does_not_stop_profile(self):
        control = TaskControl()
        profile_stop = threading.Event()
        control.pause()
        reached = threading.Event()
        results = []
        cancellation = TaskCancellation(profile_stop, control=control)
        self.run_thread(lambda: (results.append(cancellation.is_set()), reached.set()))
        self.assertFalse(reached.wait(0.04))
        control.stop()
        self.assertTrue(reached.wait(1))
        self.assertEqual(results, [True])
        self.assertFalse(profile_stop.is_set())
        self.assertFalse(control.paused)

    def test_profile_shutdown_also_unblocks_paused_work(self):
        control, shutdown = TaskControl(), threading.Event()
        control.pause()
        done = threading.Event()
        result = []
        self.run_thread(lambda: (result.append(TaskCancellation(shutdown, control=control).is_set()), done.set()))
        shutdown.set()
        self.assertTrue(done.wait(1))
        self.assertEqual(result, [True])

    def test_stop_interrupts_a_long_publish_delay(self):
        control = TaskControl()
        done = threading.Event()
        results = []
        self.run_thread(lambda: (results.append(TaskCancellation(control=control).wait(3600)), done.set()))
        control.stop()
        self.assertTrue(done.wait(1))
        self.assertEqual(results, [True])

    def test_ai_does_not_start_next_post_until_resumed(self):
        worker = ReplySuggestionWorker()
        control = TaskControl()
        first_done = threading.Event()
        second_done = threading.Event()
        def suggest(message, **_kwargs):
            if message == 'one':
                control.pause()
                first_done.set()
            else:
                second_done.set()
            return ['Reply for ' + message]
        with patch('backend.workers.reply_suggestion_worker.suggest_replies', side_effect=suggest) as api:
            thread = self.run_thread(lambda: worker.suggest(dict(posts=[dict(message='one'), dict(message='two')],
                                                              cancel_event=threading.Event(), task_control=control)))
            self.assertTrue(first_done.wait(1))
            self.assertFalse(second_done.wait(0.05))
            control.resume()
            self.assertTrue(second_done.wait(1))
            thread.join(1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(api.call_count, 2)

    def test_ai_single_result_is_held_while_paused_and_can_be_stopped(self):
        worker = ReplySuggestionWorker()
        control = TaskControl()
        returned = threading.Event()
        done = threading.Event()
        completed = []
        worker.completed.connect(completed.append)
        def suggest(*_args, **_kwargs):
            control.pause()
            returned.set()
            return ['Reply']
        with patch('backend.workers.reply_suggestion_worker.suggest_replies', side_effect=suggest):
            thread = self.run_thread(lambda: (worker.suggest(dict(message='one', task_control=control)), done.set()))
            self.assertTrue(returned.wait(1))
            self.assertFalse(done.wait(0.04))
            control.stop()
            self.assertTrue(done.wait(1))
            thread.join(1)
            self.app.processEvents()
            self.assertEqual(completed, [])

    def test_publish_pause_keeps_target_order_without_duplicates(self):
        worker = BrowserWorker()
        worker.profile_name = 'demo'
        control = TaskControl()
        first = threading.Event()
        second = threading.Event()
        calls = []
        def publish(**kwargs):
            calls.append(kwargs['target_url'])
            if len(calls) == 1:
                control.pause()
                first.set()
            else:
                second.set()
            return dict(message='Submitted')
        # Use a mock history store: the worker must not use a real account or database.
        with patch('backend.workers.browser_worker.browser_pool') as pool, \
             patch('backend.workers.browser_worker.PublishingService'):
            pool.get_session.return_value = SimpleNamespace(running=True, logged_in=True)
            pool.get.return_value.facebook.publish_post.side_effect = publish
            thread = self.run_thread(lambda: worker.publish_posts(dict(content='Reviewed', task_control=control,
                                                                      targets=[dict(url=str(i), kind='group') for i in range(2)])))
            self.assertTrue(first.wait(1))
            self.assertFalse(second.wait(0.05))
            control.resume()
            self.assertTrue(second.wait(1))
            thread.join(1)
            self.assertFalse(thread.is_alive())
            self.assertEqual(calls, ['0', '1'])
            pool.close.assert_not_called()

    def test_comment_pause_and_stop_buttons_control_the_same_request(self):
        with patch('frontend.pages.comment_page.AccountService') as accounts, \
             patch('frontend.pages.comment_page.load_company_catalog', return_value=None), \
             patch('frontend.pages.comment_page.browser_pool') as pool:
            accounts.return_value.get_all.return_value = []
            pool.get_worker.return_value = SimpleNamespace(scan_cancel_event=threading.Event())
            page = CommentPage()
            page._set_scanning(True)
            page.pause_scan_button.click()
            self.assertTrue(page._scan_control.paused)
            self.assertIn('Tiếp tục', page.pause_scan_button.text())
            page.pause_scan_button.click()
            self.assertFalse(page._scan_control.paused)
            page.pause_scan_button.click()
            page.stop_scan_button.click()
            self.assertTrue(page._scan_control.stopped)
            self.assertFalse(page._scan_control.paused)
            self.assertFalse(page.pause_scan_button.isEnabled())
            page._set_scanning(False)
            self.assertTrue(page.pause_scan_button.isHidden())
            page.deleteLater()

    def test_groups_stop_while_paused_keeps_profile_cancel_clear(self):
        worker = SimpleNamespace(group_control=TaskControl(), cancel_event=threading.Event())
        with patch('frontend.pages.groups.GroupService') as service, \
             patch('frontend.pages.groups.browser_pool') as pool:
            service.return_value.get_all.return_value = []
            pool.get_worker.return_value = worker
            page = GroupsPage()
            page._pending_profiles = {'demo'}
            page._update_scan_button()
            page.pause_groups_button.click()
            self.assertTrue(worker.group_control.paused)
            page.stop_groups_button.click()
            self.assertTrue(worker.group_control.stopped)
            self.assertFalse(worker.cancel_event.is_set())
            page._scan_cancelled('demo')
            self.assertFalse(page._pending_profiles)
            self.assertTrue(page.pause_groups_button.isHidden())
            page.deleteLater()


if __name__ == '__main__':
    unittest.main()
