"""Exercise worker signals with a real Qt event loop in an isolated process.

A native Qt crash must fail this test without killing the whole test runner.
Facebook and database access use controlled fixtures; no user profile is opened.
"""

import os
import subprocess
import sys
import textwrap
import unittest


class GroupScanUITests(unittest.TestCase):
    def test_scans_and_errors_update_gui_on_main_thread(self):
        script = textwrap.dedent("""
            from types import SimpleNamespace
            from unittest.mock import patch
            from PySide6.QtCore import QThread, QTimer, qInstallMessageHandler
            from PySide6.QtWidgets import QApplication
            from backend.signals import signals
            from backend.workers.browser_worker import BrowserWorker
            from backend.workers.browser_thread import BrowserThread
            from frontend.pages.groups import GroupsPage
            from frontend.widgets.activity_widget import ActivityWidget
            from frontend.widgets.log_widget import LogWidget

            app = QApplication([])
            main_thread = QThread.currentThread()
            messages = []
            qInstallMessageHandler(lambda kind, context, message: messages.append(message))
            errors = []
            records = [SimpleNamespace(
                id=i, name=f'Group {i:03}', url=f'https://www.facebook.com/groups/{i}/',
                member_count='0', privacy='Unknown', status=f'status-{i}'
            ) for i in range(173, 0, -1)]
            sessions = {name: SimpleNamespace(profile=name, running=True, logged_in=True)
                        for name in ('success', 'failure')}
            workers = {}
            threads = []
            reads = []
            scans = []

            def read_groups():
                reads.append(QThread.currentThread() == main_thread)
                return records

            def get_groups(profile, **kwargs):
                scans.append((profile, QThread.currentThread() == workers[profile].thread()))
                if profile == 'failure':
                    raise RuntimeError('simulated listing failure')
                for i in range(20):
                    signals.log.emit(f'Scan progress {i}')
                return [{'name': row.name, 'url': row.url} for row in records]

            def manager(profile):
                return SimpleNamespace(facebook=SimpleNamespace(
                    get_groups=lambda **kwargs: get_groups(profile, **kwargs),
                    last_group_scan_complete=True, last_group_scan_expected=173,
                ))

            with patch('frontend.pages.groups.GroupService') as ui_service, \\
                 patch('backend.workers.browser_worker.GroupService') as sync_service, \\
                 patch('frontend.pages.groups.browser_pool') as pool, \\
                 patch('backend.workers.browser_worker.browser_pool') as worker_pool, \\
                 patch('frontend.widgets.activity_widget.CommentHistoryService') as history, \\
                 patch('frontend.pages.groups.QMessageBox.warning', side_effect=lambda *args: errors.append(args)):
                ui_service.return_value.get_all.side_effect = read_groups
                sync_service.return_value.sync_discovered_groups.return_value = {
                    'added': 0, 'count': 173, 'complete': True,
                }
                history.return_value.get_recent.return_value = []
                pool.get_all_sessions.return_value = list(sessions.values())
                pool.get_worker.side_effect = workers.get
                worker_pool.get_session.side_effect = sessions.get
                worker_pool.get.side_effect = manager
                page = GroupsPage()
                activity = ActivityWidget()
                logs = LogWidget()
                for profile in sessions:
                    worker = BrowserWorker()
                    worker.profile_name = profile
                    thread = BrowserThread()
                    worker.moveToThread(thread)
                    thread.finished.connect(worker.deleteLater)
                    workers[profile] = worker
                    threads.append(thread)
                    thread.start()

                timer = QTimer()
                timer.timeout.connect(lambda: app.quit() if scans and not page._pending_profiles else None)
                timer.start(20)
                QTimer.singleShot(0, page.toolbar.buttons[2].click)
                QTimer.singleShot(5000, app.quit)
                try:
                    app.exec()
                    app.processEvents()
                    assert len(scans) == 2 and all(on_owner for _, on_owner in scans), scans
                    assert not page._pending_profiles, page._pending_profiles
                    assert all(reads) and len(reads) == 2, reads
                    assert len(errors) == 1, errors
                    assert logs.count() > 1
                    assert page.toolbar.buttons[2].isEnabled()
                    for row in range(page.table.rowCount()):
                        number = int(page.table.item(row, 0).text().split()[-1])
                        assert page.table.item(row, 4).text() == f'status-{number}'
                    assert not any('different thread' in msg or 'Cannot create children' in msg for msg in messages), messages
                finally:
                    for thread in threads:
                        thread.quit()
                    for thread in threads:
                        assert thread.wait(3000)
            print('Qt group scan success and failure paths passed')
        """)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONIOENCODING="utf-8")
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
