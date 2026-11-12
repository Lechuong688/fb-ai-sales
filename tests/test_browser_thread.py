"""Regression for Playwright reuse across separate Qt event-loop callbacks."""

import os
import subprocess
import sys
import textwrap
import unittest


class BrowserThreadTests(unittest.TestCase):
    def test_real_playwright_survives_idle_and_subsequent_queued_operations(self):
        script = textwrap.dedent("""
            from pathlib import Path
            import traceback
            from PySide6.QtCore import QObject, QCoreApplication, QTimer, Signal, Slot
            from playwright.sync_api import sync_playwright
            from backend.workers.browser_thread import BrowserThread

            app = QCoreApplication([])

            class Probe(QObject):
                open_requested = Signal()
                scan_requested = Signal()
                close_requested = Signal()

                def __init__(self):
                    super().__init__()
                    self.opened = False
                    self.completed = 0
                    self.closed = False
                    self.missing_browser = False
                    self.errors = []
                    self.pw = None
                    self.browser = None
                    self.open_requested.connect(self.open)
                    self.scan_requested.connect(self.scan)
                    self.close_requested.connect(self.close)

                @Slot()
                def open(self):
                    try:
                        self.pw = sync_playwright().start()
                        if not Path(self.pw.chromium.executable_path).is_file():
                            self.missing_browser = True
                            self.close()
                            return
                        self.browser = self.pw.chromium.launch(headless=True)
                        self.page = self.browser.new_page()
                        self.page.goto('data:text/html,<h1>Profile ready</h1>')
                        self.opened = True
                    except Exception:
                        self.errors.append(traceback.format_exc())
                        self.close()

                @Slot()
                def scan(self):
                    try:
                        self.page.goto('data:text/html,<title>Groups</title><h1>Group list</h1>')
                        assert self.page.title() == 'Groups'
                        assert self.page.locator('h1').inner_text() == 'Group list'
                        self.page.evaluate('window.scrollTo(0, 100)')
                        self.completed += 1
                    except Exception:
                        self.errors.append(traceback.format_exc())
                        self.close()

                @Slot()
                def close(self):
                    try:
                        if self.browser is not None:
                            self.browser.close()
                        if self.pw is not None:
                            self.pw.stop()
                    except Exception:
                        self.errors.append(traceback.format_exc())
                    self.closed = True

            worker = Probe()
            thread = BrowserThread()
            worker.moveToThread(thread)
            thread.finished.connect(worker.deleteLater)
            thread.start()
            worker.open_requested.emit()
            requested = [0]
            close_requested = [False]

            def tick():
                if worker.closed:
                    app.quit()
                elif worker.opened and worker.completed == requested[0]:
                    if worker.completed < 3:
                        requested[0] += 1
                        worker.scan_requested.emit()
                    elif not close_requested[0]:
                        close_requested[0] = True
                        worker.close_requested.emit()

            timer = QTimer()
            timer.timeout.connect(tick)
            timer.start(50)
            QTimer.singleShot(20000, app.quit)
            app.exec()
            if not worker.closed:
                worker.close_requested.emit()
            thread.quit()
            assert thread.wait(5000), 'Browser thread did not stop'
            if worker.missing_browser:
                raise SystemExit(77)
            assert not worker.errors, '\\n'.join(worker.errors)
            assert worker.completed == 3, worker.completed
            assert worker.closed
            print('Browser opened, idled, handled 3 queued operations, and closed')
        """)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script],
            capture_output=True, text=True, encoding="utf-8", env=env, timeout=35,
        )
        if result.returncode == 77:
            self.skipTest("Playwright Chromium is not installed")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
